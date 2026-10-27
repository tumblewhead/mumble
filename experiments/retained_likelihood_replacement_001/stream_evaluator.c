/* One retained-prefix evaluation, not an estimator or an optimizer.
 *
 * x = (logtau[3], loggamma_plus, loggamma_minus, logQ,
 *      R0, R[3], H, z0, v0[3], h0).
 * The original model API owns all forward recurrence and theta derivatives.
 * Only the chart map, streamed accumulation and endpoint transport are new.
 * No observation-sized object is allocated. See emitted storage limitations.
 */
#include "scm_model.h"
#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define DIM 16
#define PACKED 136
#define RECORD_BYTES 32
#define BUFFER_BYTES 4096
#define MAX_PREFIX UINT64_C(252000)
#define SIGMA_V 0.001
#define SCHEMA "mumble_retained_likelihood_stream_evaluator_v1"

/* The original entering support, not the wider online propagated-state box.
 * Log limits are the published binary64 constants in scm_hypothesis.c.
 */
static const double lower[DIM] = {
    -4.199705077879927, -1.8971199848858813, .40546510810816438,
    1.6094379124341003, 1.6094379124341003, -3.5065578973199818,
    0., 0., 0., 0., 0., .2, -.08, -.08, -.08, -1.
};
static const double upper[DIM] = {
    -1.8971199848858813, .40546510810816438, 3.4011973816621555,
    7.0900768357760917, 7.0900768357760917, -2.3025850929940455,
    1., 1., 1., 1., .1, .95, .08, .08, .08, 1.
};
static const char *const coordinate_names[DIM] = {
    "logtau1", "logtau2", "logtau3", "loggamma_plus", "loggamma_minus",
    "logQ", "R0", "R1", "R2", "R3", "H", "z", "v1", "v2", "v3", "h"
};
static const char *const physical_names[DIM] = {
    "tau1_s", "tau2_s", "tau3_s", "gamma_plus", "gamma_minus", "Q_Ah",
    "R0_ohm", "R1_ohm", "R2_ohm", "R3_ohm", "H_V", "SOC",
    "v1_V", "v2_V", "v3_V", "h"
};

typedef struct {
    double sum, correction, absolute_sum, absolute_correction;
} accumulator;

typedef struct {
    double x[DIM], theta[SCM_MAX_THETA], alpha[SCM_MAX_ALPHA];
    double theta_jacobian[SCM_MAX_THETA], jacobian[DIM], endpoint_x[DIM];
    scm_model_state model;
    scm_model_row row;
    accumulator cost, gradient[DIM], gram[PACKED];
    accumulator absolute_voltage, absolute_residual;
    double naive_cost, charge_min_Ah, charge_max_Ah;
    double last_voltage, last_observed, last_current, last_dt;
    double max_abs_voltage, max_abs_residual;
    uint64_t prefix, records_read, records_accumulated, input_bytes_read;
    uint64_t model_init_calls, model_step_calls, model_predict_calls;
    unsigned char buffer[BUFFER_BYTES];
} workspace;

static int packed_index(int i, int j)
{
    return i * (i + 1) / 2 + j;
}

static int neumaier(double *sum, double *correction, double value)
{
    double next, error;
    if (!isfinite(value)) return -1;
    next = *sum + value;
    if (!isfinite(next)) return -1;
    error = fabs(*sum) >= fabs(value) ? (*sum - next) + value :
                                      (value - next) + *sum;
    *correction += error;
    *sum = next;
    return isfinite(*correction) && isfinite(*sum + *correction) ? 0 : -1;
}

static int accumulate(accumulator *a, double value)
{
    if (neumaier(&a->sum, &a->correction, value)) return -1;
    return neumaier(&a->absolute_sum, &a->absolute_correction, fabs(value));
}

static double total(const accumulator *a)
{
    return a->sum + a->correction;
}

static double absolute_total(const accumulator *a)
{
    return a->absolute_sum + a->absolute_correction;
}

static uint64_t little_u64(const unsigned char *p)
{
    uint64_t value = 0;
    unsigned int j;
    for (j = 0; j < 8; ++j) value |= (uint64_t)p[j] << (8 * j);
    return value;
}

static double little_double(const unsigned char *p)
{
    uint64_t bits = little_u64(p);
    double value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

/* Whitespace-only, bounded tokens: exactly sixteen finite C-locale decimal
 * values; trailing non-whitespace is rejected. No source state is restored.
 */
static int read_x(FILE *input, double x[DIM])
{
    char token[128], *end;
    int i, c;
    size_t count;
    for (i = 0; i < DIM; ++i) {
        do { c = fgetc(input); } while (c != EOF && isspace((unsigned char)c));
        if (c == EOF) return -1;
        count = 0;
        do {
            if (count + 1 >= sizeof(token)) return -1;
            if (!(isdigit((unsigned char)c) || c == '+' || c == '-' ||
                  c == '.' || c == 'e' || c == 'E')) return -1;
            token[count++] = (char)c;
            c = fgetc(input);
        } while (c != EOF && !isspace((unsigned char)c));
        token[count] = '\0';
        x[i] = strtod(token, &end);
        if (end == token || *end || !isfinite(x[i])) return -1;
    }
    do { c = fgetc(input); } while (c != EOF && isspace((unsigned char)c));
    return c == EOF && !ferror(input) ? 0 : -1;
}

static int parse_prefix(const char *text, uint64_t *value)
{
    uint64_t result = 0;
    const unsigned char *p = (const unsigned char *)text;
    if (!*p) return -1;
    while (*p) {
        if (!isdigit(*p)) return -1;
        result = result * 10 + (uint64_t)(*p - '0');
        if (result > MAX_PREFIX) return -1;
        ++p;
    }
    *value = result;
    return 0;
}

static int fail(const workspace *w, const char *reason, int model_status)
{
    fprintf(stderr, "%s at record %" PRIu64 " (model status %d)\n",
            reason, w->records_accumulated, model_status);
    printf("{\"schema\":\"%s\",\"status\":\"error\",\"error\":\"%s\","
           "\"model_status\":%d,\"prefix_requested\":%" PRIu64 ","
           "\"records_read\":%" PRIu64 ",\"records_accumulated\":%" PRIu64 ","
           "\"input_bytes_read\":%" PRIu64 ",\"model_init_calls\":%" PRIu64 ","
           "\"model_step_calls\":%" PRIu64 ",\"model_predict_calls\":%" PRIu64 ","
           "\"source_generations\":0,\"learner_ingests\":0,\"fit_calls\":0,"
           "\"truth_reads\":0}\n", SCHEMA, reason, model_status, w->prefix,
           w->records_read, w->records_accumulated, w->input_bytes_read,
           w->model_init_calls, w->model_step_calls, w->model_predict_calls);
    return 1;
}

static int initialize(workspace *w)
{
    int i;
    for (i = 0; i < DIM; ++i)
        if (!isfinite(w->x[i]) || w->x[i] < lower[i] || w->x[i] > upper[i])
            return SCM_ERR_DOMAIN;
    for (i = 0; i < 5; ++i) w->theta[i] = w->x[i];
    w->theta[5] = w->x[11];
    w->theta[6] = w->x[5];
    for (i = 0; i < 5; ++i) w->alpha[i] = w->x[6 + i];
    for (i = 0; i < 3; ++i) w->alpha[5 + i] = w->x[12 + i];
    w->alpha[8] = w->x[10] * w->x[15];
    ++w->model_init_calls;
    return scm_model_init(&w->model, 3, w->theta);
}

static void map_jacobian(workspace *w)
{
    int i;
    for (i = 0; i < 5; ++i) w->jacobian[i] = w->theta_jacobian[i];
    w->jacobian[5] = w->theta_jacobian[6];
    for (i = 0; i < 4; ++i) w->jacobian[6 + i] = w->row.X[i];
    w->jacobian[10] = w->row.X[4] + w->x[15] * w->row.X[8];
    w->jacobian[11] = w->theta_jacobian[5];
    for (i = 0; i < 3; ++i) w->jacobian[12 + i] = w->row.X[5 + i];
    w->jacobian[15] = w->x[10] * w->row.X[8];
}

static int add_record(workspace *w, const unsigned char *record, const char **reason)
{
    uint64_t index = little_u64(record);
    double dt = little_double(record + 8), current = little_double(record + 16);
    double observed = little_double(record + 24), prediction, residual, term, h;
    int i, j, status;
    ++w->records_read;
    if (index != w->records_accumulated) { *reason = "unordered_record_index"; return -1; }
    if (!isfinite(dt) || !isfinite(current) || !isfinite(observed)) {
        *reason = "nonfinite_record"; return -1;
    }
    if (dt < 0.) { *reason = "negative_dt"; return -1; }
    ++w->model_step_calls;
    status = scm_model_step(&w->model, NULL, dt, current, &w->row);
    if (status) { *reason = "model_step_failed"; return status; }
    h = w->model.hb + w->model.ha * w->x[15];
    if (!isfinite(h) || h < -1. || h > 1.) {
        *reason = "propagated_h_outside_domain"; return SCM_ERR_DOMAIN;
    }
    ++w->model_predict_calls;
    status = scm_model_predict(&w->row, 3, w->alpha, &prediction, w->theta_jacobian);
    if (status) { *reason = "model_predict_failed"; return status; }
    map_jacobian(w);
    residual = (prediction - observed) / SIGMA_V;
    term = .5 * residual * residual;
    if (accumulate(&w->cost, term)) { *reason = "nonfinite_cost_accumulation"; return -1; }
    w->naive_cost += term;
    if (!isfinite(w->naive_cost)) { *reason = "nonfinite_naive_cost"; return -1; }
    for (i = 0; i < DIM; ++i) {
        w->jacobian[i] /= SIGMA_V;
        if (!isfinite(w->jacobian[i]) || accumulate(&w->gradient[i], residual * w->jacobian[i])) {
            *reason = "nonfinite_gradient_accumulation"; return -1;
        }
    }
    for (i = 0; i < DIM; ++i)
        for (j = 0; j <= i; ++j)
            if (accumulate(&w->gram[packed_index(i, j)], w->jacobian[i] * w->jacobian[j])) {
                *reason = "nonfinite_gram_accumulation"; return -1;
            }
    if (accumulate(&w->absolute_voltage, fabs(prediction)) ||
        accumulate(&w->absolute_residual, fabs(prediction - observed))) {
        *reason = "nonfinite_diagnostic_accumulation"; return -1;
    }
    w->charge_min_Ah = fmin(w->charge_min_Ah, w->model.charge_Ah);
    w->charge_max_Ah = fmax(w->charge_max_Ah, w->model.charge_Ah);
    w->max_abs_voltage = fmax(w->max_abs_voltage, fabs(prediction));
    w->max_abs_residual = fmax(w->max_abs_residual, fabs(prediction - observed));
    w->last_voltage = prediction;
    w->last_observed = observed;
    w->last_current = current;
    w->last_dt = dt;
    ++w->records_accumulated;
    return 0;
}

static int endpoint(workspace *w)
{
    int i;
    memcpy(w->endpoint_x, w->x, sizeof(w->x));
    w->endpoint_x[11] = w->model.z0 - w->model.charge_Ah / w->model.Q;
    for (i = 0; i < 3; ++i)
        w->endpoint_x[12 + i] = w->x[7 + i] * w->model.f[i] + w->x[12 + i] * w->model.a[i];
    w->endpoint_x[15] = w->model.hb + w->x[15] * w->model.ha;
    for (i = 0; i < DIM; ++i) if (!isfinite(w->endpoint_x[i])) return -1;
    return w->endpoint_x[11] >= 0. && w->endpoint_x[11] <= 1. &&
           w->endpoint_x[15] >= -1. && w->endpoint_x[15] <= 1. ? 0 : -1;
}

/* Full derivative d(endpoint_x)/d(entering_x), without another model pass or
 * an additional stored 16-by-16 matrix. The static chart rows are identity.
 */
static double endpoint_derivative(const workspace *w, int row, int column)
{
    int i;
    if (row < 11) return row == column ? 1. : 0.;
    if (row == 11) {
        if (column == 11) return 1.;
        return column == 5 ? w->model.charge_Ah / w->model.Q : 0.;
    }
    if (row < 15) {
        i = row - 12;
        if (column == i) return w->x[7 + i] * w->model.df[i] + w->x[12 + i] * w->model.da[i];
        if (column == 7 + i) return w->model.f[i];
        return column == 12 + i ? w->model.a[i] : 0.;
    }
    if (column == 3 || column == 4) {
        i = column - 3;
        return w->model.dhb[i] + w->x[15] * w->model.dha[i];
    }
    return column == 15 ? w->model.ha : 0.;
}

static int finite_endpoint_derivatives(const workspace *w)
{
    int i, j;
    for (i = 0; i < DIM; ++i)
        for (j = 0; j < DIM; ++j)
            if (!isfinite(endpoint_derivative(w, i, j))) return -1;
    return 0;
}

static void print_array(const double *values, int count)
{
    int i;
    putchar('[');
    for (i = 0; i < count; ++i) { if (i) putchar(','); printf("%.17g", values[i]); }
    putchar(']');
}

static void print_accumulators(const accumulator *a, int count, int absolute)
{
    int i;
    putchar('[');
    for (i = 0; i < count; ++i) {
        if (i) putchar(',');
        printf("%.17g", absolute ? absolute_total(&a[i]) : total(&a[i]));
    }
    putchar(']');
}

static void print_names(const char *const *names)
{
    int i;
    putchar('[');
    for (i = 0; i < DIM; ++i) { if (i) putchar(','); printf("\"%s\"", names[i]); }
    putchar(']');
}

static void print_endpoint_map(const workspace *w, int physical)
{
    int i, j;
    double scale;
    putchar('[');
    for (i = 0; i < DIM; ++i) {
        scale = physical && i < 6 ? exp(w->x[i]) : 1.;
        for (j = 0; j < DIM; ++j) {
            if (i || j) putchar(',');
            printf("%.17g", scale * endpoint_derivative(w, i, j));
        }
    }
    putchar(']');
}

static int emit(const workspace *w, double cpu_s)
{
    int i;
    printf("{\"schema\":\"%s\",\"status\":\"ok\",\"dimension\":16,", SCHEMA);
    fputs("\"coordinate_names\":", stdout); print_names(coordinate_names);
    fputs(",\"x\":", stdout); print_array(w->x, DIM);
    fputs(",\"legacy_theta\":", stdout); print_array(w->theta, SCM_MAX_THETA);
    fputs(",\"legacy_alpha\":", stdout); print_array(w->alpha, SCM_MAX_ALPHA);
    printf(",\"sigma_V\":%.17g,\"cost\":%.17g,\"cost_naive\":%.17g,"
           "\"cost_naive_minus_compensated\":%.17g,\"gradient\":",
           SIGMA_V, total(&w->cost), w->naive_cost, w->naive_cost - total(&w->cost));
    print_accumulators(w->gradient, DIM, 0);
    fputs(",\"gram\":", stdout); print_accumulators(w->gram, PACKED, 0);
    fputs(",\"gram_layout\":\"lower-packed-row-major: i*(i+1)/2+j for j<=i\","
          "\"gradient_and_gram_coordinates\":\"unscaled entering x; residual=prediction-observed; sigma whitening once\","
          "\"curvature_semantics\":\"undamped full Gauss-Newton Gram, not the exact likelihood Hessian or a posterior\","
          "\"absolute_summand_scales\":{\"cost\":", stdout);
    printf("%.17g,\"gradient\":", absolute_total(&w->cost)); print_accumulators(w->gradient, DIM, 1);
    fputs(",\"gram\":", stdout); print_accumulators(w->gram, PACKED, 1);
    printf("},\"roundoff\":{\"binary64_epsilon\":%.17g,\"unit_roundoff\":%.17g,"
           "\"method\":\"Neumaier compensated sum and compensated absolute summand sum\","
           "\"scope\":\"Absolute scales describe computed binary64 residual/Jacobian summands. They do not bound libm, recurrence, derivative, subtraction, whitening or product error against a real-model evaluation. No full-model error certificate is claimed.\"}",
           DBL_EPSILON, .5 * DBL_EPSILON);
    printf(",\"charge_Ah\":%.17g,\"charge_min_Ah\":%.17g,\"charge_max_Ah\":%.17g,"
           "\"charge_extrema_include_initial_zero\":true,\"elapsed_physical_s\":%.17g,"
           "\"elapsed_cpu_s\":%.17g,\"endpoint_x\":", w->model.charge_Ah,
           w->charge_min_Ah, w->charge_max_Ah, w->model.elapsed, cpu_s);
    print_array(w->endpoint_x, DIM);
    fputs(",\"endpoint_state_names\":", stdout); print_names(physical_names);
    fputs(",\"endpoint_state\":[", stdout);
    for (i = 0; i < DIM; ++i) { if (i) putchar(','); printf("%.17g", i < 6 ? exp(w->x[i]) : w->endpoint_x[i]); }
    fputs("],\"endpoint_derivative\":", stdout); print_endpoint_map(w, 0);
    fputs(",\"endpoint_physical_derivative\":", stdout); print_endpoint_map(w, 1);
    fputs(",\"endpoint_derivative_layout\":\"full-row-major 16x16; rows endpoint_x, columns entering x\","
          "\"endpoint_physical_derivative_layout\":\"full-row-major 16x16; rows endpoint_state, columns entering x\","
          "\"last_record\":", stdout);
    if (!w->prefix) fputs("null", stdout);
    else {
        printf("{\"index\":%" PRIu64 ",\"dt_s\":%.17g,\"current_A\":%.17g,"
               "\"observed_voltage_V\":%.17g,\"predicted_voltage_V\":%.17g,"
               "\"whitened_prediction_jacobian\":", w->prefix - 1, w->last_dt,
               w->last_current, w->last_observed, w->last_voltage);
        print_array(w->jacobian, DIM); putchar('}');
    }
    printf(",\"voltage_diagnostics\":{\"sum_abs_prediction_V\":%.17g,"
           "\"sum_abs_residual_V\":%.17g,\"max_abs_prediction_V\":%.17g,"
           "\"max_abs_residual_V\":%.17g},\"prefix_requested\":%" PRIu64 ","
           "\"records_read\":%" PRIu64 ",\"records_accumulated\":%" PRIu64 ","
           "\"input_bytes_read\":%" PRIu64 ",\"model_init_calls\":%" PRIu64 ","
           "\"model_step_calls\":%" PRIu64 ",\"model_predict_calls\":%" PRIu64 ","
           "\"source_generations\":0,\"learner_ingests\":0,\"fit_calls\":0,\"truth_reads\":0,",
           total(&w->absolute_voltage), total(&w->absolute_residual), w->max_abs_voltage,
           w->max_abs_residual, w->prefix, w->records_read, w->records_accumulated,
           w->input_bytes_read, w->model_init_calls, w->model_step_calls, w->model_predict_calls);
    printf("\"storage\":{\"workspace_sizeof_bytes\":%zu,\"read_buffer_bytes\":%zu,"
           "\"model_state_sizeof_bytes\":%zu,\"model_row_sizeof_bytes\":%zu,"
           "\"accumulator_sizeof_bytes\":%zu,\"likelihood_accumulators_bytes\":%zu,"
           "\"diagnostic_accumulators_bytes\":%zu,\"chart_and_jacobian_arrays_bytes\":%zu,"
           "\"readonly_bound_arrays_bytes\":%zu,\"x_token_buffer_bytes\":128,"
           "\"observation_sized_arrays\":0,\"explicit_heap_allocations\":0,"
           "\"additional_stored_endpoint_matrices\":0,"
           "\"limitations\":\"Workspace is fixed automatic storage. This sizeof accounting excludes other scalar/pointer stack frames, unchanged model function stack, compiler spills, FILE/libc/libm storage, executable code, process/runtime and externally retained observations. It is not complete target SRAM or a measured stack peak.\"}}\n",
           sizeof(*w), sizeof(w->buffer), sizeof(w->model), sizeof(w->row), sizeof(accumulator),
           sizeof(w->cost) + sizeof(w->gradient) + sizeof(w->gram),
           sizeof(w->absolute_voltage) + sizeof(w->absolute_residual),
           sizeof(w->x) + sizeof(w->theta) + sizeof(w->alpha) + sizeof(w->theta_jacobian) +
           sizeof(w->jacobian) + sizeof(w->endpoint_x), sizeof(lower) + sizeof(upper));
    return fflush(stdout) == 0 && !ferror(stdout) ? 0 : 1;
}

int main(int argc, char **argv)
{
    workspace w;
    const char *x_path = NULL, *observation_path = NULL, *reason = NULL;
    FILE *x_file, *observations;
    int i, status, seen_prefix = 0, seen_sigma = 0;
    size_t wanted, got, offset;
    char *end;
    double sigma;
    clock_t start = clock();
    memset(&w, 0, sizeof(w));
    w.prefix = MAX_PREFIX;
    if (CHAR_BIT != 8 || sizeof(double) != 8 || DBL_MANT_DIG != 53 || DBL_MAX_EXP != 1024)
        return fail(&w, "unsupported_binary64_platform", 0);
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--help") && argc == 2) {
            fputs("stream_evaluator --x FILE --sigma 0.001 [--observations FILE] [--prefix 0..252000]\n"
                  "x: exactly sixteen whitespace-separated finite entering-chart decimal values.\n"
                  "Observations: little-endian <Qddd> (index,dt,current,voltage), stdin when omitted.\n", stdout);
            return 0;
        }
        if (i + 1 >= argc) return fail(&w, "missing_option_value", 0);
        if (!strcmp(argv[i], "--x") && !x_path) x_path = argv[++i];
        else if (!strcmp(argv[i], "--observations") && !observation_path) observation_path = argv[++i];
        else if (!strcmp(argv[i], "--prefix") && !seen_prefix) {
            seen_prefix = 1;
            if (parse_prefix(argv[++i], &w.prefix)) return fail(&w, "invalid_prefix", 0);
        } else if (!strcmp(argv[i], "--sigma") && !seen_sigma) {
            seen_sigma = 1;
            sigma = strtod(argv[++i], &end);
            if (end == argv[i] || *end || !isfinite(sigma) || sigma != SIGMA_V)
                return fail(&w, "sigma_must_equal_0_001", 0);
        } else return fail(&w, "unknown_or_repeated_option", 0);
    }
    if (!x_path || !seen_sigma) return fail(&w, "x_and_sigma_required", 0);
    x_file = fopen(x_path, "r");
    if (!x_file) return fail(&w, "x_open_failed", 0);
    status = read_x(x_file, w.x);
    if (fclose(x_file) != 0) status = -1;
    if (status) return fail(&w, "invalid_x_file", 0);
    status = initialize(&w);
    if (status) return fail(&w, "entering_support_or_init_failed", status);
    observations = observation_path ? fopen(observation_path, "rb") : stdin;
    if (!observations) return fail(&w, "observations_open_failed", 0);
    if (setvbuf(observations, NULL, _IONBF, 0) != 0) {
        if (observation_path) fclose(observations);
        return fail(&w, "unbuffered_stream_setup_failed", 0);
    }
    while (w.records_accumulated < w.prefix) {
        uint64_t remaining = w.prefix - w.records_accumulated;
        wanted = remaining < BUFFER_BYTES / RECORD_BYTES ? (size_t)remaining * RECORD_BYTES : BUFFER_BYTES;
        got = fread(w.buffer, 1, wanted, observations);
        w.input_bytes_read += got;
        if (got != wanted) {
            reason = ferror(observations) ? "observations_read_failed" : "truncated_prefix";
            if (observation_path) fclose(observations);
            return fail(&w, reason, 0);
        }
        for (offset = 0; offset < got; offset += RECORD_BYTES) {
            status = add_record(&w, w.buffer + offset, &reason);
            if (status) {
                if (observation_path) fclose(observations);
                return fail(&w, reason, status);
            }
        }
    }
    if (observation_path && fclose(observations) != 0) return fail(&w, "observations_close_failed", 0);
    if (endpoint(&w) || finite_endpoint_derivatives(&w)) return fail(&w, "invalid_endpoint_or_derivative", 0);
    return emit(&w, (double)(clock() - start) / CLOCKS_PER_SEC);
}
