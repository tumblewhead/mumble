#ifndef MUMBLE_COMPACT_NONLINEAR_HISTORY_001_H
#define MUMBLE_COMPACT_NONLINEAR_HISTORY_001_H

/* Experimental fixed-origin nonlinear evidence, not calibrated uncertainty.
 * Original entering chart:
 * logtau[3], loggamma[2], logQ, R0, R[3], H, z0, v0[3], h0.
 * One bank replaces (does not accompany) the old learner. No heap, raw history,
 * moving approximation origin, posterior re-assimilation or noise adaptation.
 * The illustrative smooth OCV and sigma=0.001 V are fixed by this experiment.
 */
#include "scm_model.h"
#include <stddef.h>
#include <stdint.h>

#define CH_DIM 16
#define CH_PAIRS 20
#define CH_AUG 37
#define CH_PACKED 136
#define CH_QR 703
#define CH_MAX_ROUNDS 16
#define CH_FRACTIONS 8
#define CH_SIGMA 0.001
#define CH_ADC_RESERVE_BYTES 448
#define CH_CODEC_RESERVE_BYTES 128
#define CH_OWN_STACK_CAP_BYTES 768
#define CH_RUNTIME_IRQ_CALLER_RESERVE_BYTES 768

enum { CH_OK=0, CH_UNRESOLVED=1, CH_ERR_ARGUMENT=-1, CH_ERR_SOURCE=-2,
       CH_ERR_ORDER=-3, CH_ERR_DOMAIN=-4, CH_ERR_NONFINITE=-5,
       CH_ERR_UNAVAILABLE=-6, CH_ERR_OVERFLOW=-7 };
enum { CH_AFFINE=1, CH_QUARTIC=2 };
enum { CH_NO_CURVATURE=0, CH_GN=1, CH_TRUE_HESSIAN=2 };
enum { CH_NO_PRIOR=0, CH_EXACT_PRIOR=1, CH_PRIOR_MAJORIZER=2 };
enum { CH_STOP_NONE=0, CH_STOP_ROUND_LIMIT=1, CH_STOP_DIRECTION=2,
       CH_STOP_NO_TRIAL=3, CH_STOP_METRIC=4, CH_STOP_QUERY=5,
       CH_STOP_COUNTER=6 };
enum { CH_FLAG_ENDPOINT_APPROXIMATE=1u, CH_FLAG_ENDPOINT_INVALID=2u,
       CH_FLAG_PRIOR_INCLUDED=4u, CH_FLAG_PRIOR_MAJORIZER=8u,
       CH_FLAG_ACCEPTED=16u, CH_FLAG_FEASIBLE=32u,
       CH_FLAG_COST_AVAILABLE=64u, CH_FLAG_DIRECTION_ADMITTED=128u };

/* Signed second derivatives: RC with respect to its logtau; hysteresis
 * entries (plus,plus),(plus,minus),(minus,minus). Model state is at the fixed
 * origin. The estimate never replaces this carried state or derivative jet.
 */
typedef struct {
    scm_model_state model;
    double ddf[3], dda[3], ddhb[3], ddha[3];
} ch_jet;

typedef struct {
    double upper[CH_QR];
    ch_jet jet;
    double origin[CH_DIM], estimate[CH_DIM];
    unsigned char source_id[32];
    uint64_t next_index;
    double charge_min_Ah, charge_max_Ah;
    uint64_t model_steps, qr_rows, query_evaluations, prior_evaluations;
    uint64_t proposal_rounds, accepted_steps;
    uint32_t available;
    int32_t last_error;
} ch_bank;

typedef union {
    struct { ch_jet prospective; double row[CH_AUG]; } ingest;
    struct {
        double packed[CH_PACKED]; /* lower triangular, row-major */
        double delta[CH_DIM], row_gradient[CH_DIM];
        double gradient[CH_DIM], point[CH_DIM];
    } query;
} ch_workspace;

/* Query and proposal diagnostics are mutually exclusive views. A trace
 * callback must consume/copy its record before returning. No retained trace
 * or second factor is owned by this component.
 */
typedef struct {
    double likelihood_cost, prior_cost, total_cost, cost_absolute_scale;
    uint32_t flags, stop_reason;
    union {
        struct { double SOC, v[3], h, min_support_slack, min_endpoint_slack; } endpoint;
        struct {
            double slope, slope_allowance, model_decrease, model_allowance;
            double cost_decrease, cost_allowance, armijo_required;
            double combine_allowance, alpha;
        } step;
    } detail;
    uint32_t round, fraction;
} ch_result;

typedef struct {
    ch_bank bank;
    ch_workspace workspace;
    ch_result result;
    scm_sample sample; /* caller fills one actual ADC interval/current/voltage */
} ch_context;

/* Explicit byte reservations, not an implemented ADC/flash driver. The ADC
 * reserve can hold sixteen 24-byte decoded samples plus 64 metadata bytes.
 * Target ISR/libm/caller and stack caps are planning caps, not measurements.
 */
typedef struct {
    ch_context core;
    unsigned char adc_reserve[CH_ADC_RESERVE_BYTES];
    unsigned char checkpoint_codec_reserve[CH_CODEC_RESERVE_BYTES];
} ch_operational_layout;

typedef void (*ch_trace_callback)(const ch_context *, void *);

extern const double ch_public_mean[CH_DIM];
extern const double ch_public_sd[CH_DIM];
extern const double ch_lower[CH_DIM], ch_upper[CH_DIM];
extern const unsigned char ch_pair[CH_PAIRS][2];

size_t ch_qr_index(unsigned row, unsigned column);
size_t ch_packed_index(unsigned row, unsigned column);
int ch_init(ch_context *, const unsigned char source_id[32], const double origin[CH_DIM]);

/* Read-only operational-bank helper for independent row/jet qualification.
 * Validates source/index and ctx->sample, then writes workspace.ingest only.
 * It is not ingestion and changes no operational counters. Canonical runtime
 * calls push, which performs exactly one preparation and records its work.
 */
int ch_prepare(ch_context *, const unsigned char source_id[32], uint64_t index);

/* Prevalidation errors leave the bank unchanged. After prevalidation, any
 * internal model/QR numerical fault latches available=0; partially mutated QR
 * storage is then forbidden for every subsequent query/push/refinement.
 */
int ch_push(ch_context *, const unsigned char source_id[32], uint64_t index);

/* The requested point lives in workspace.query.point: no uncounted caller
 * point vector is needed. All derivatives are in unscaled original x units.
 * Prior is the exact public whole-mixture kernel (one common support law).
 * Its unknown support normalizer is omitted only from costs/contrasts; no
 * normalized posterior probability is returned. MAJORIZER changes curvature
 * to P^-1 only; cost and gradient still use the exact mixture.
 */
int ch_query(ch_context *, int affine_or_quartic, int curvature, int prior);

/* Uses workspace.query.point. Exact SOC, second-order RC/h state approximation;
 * writes result.detail.endpoint/flags without a model/prior/query evaluation.
 * It does not advance or replace the carried model state.
 */
int ch_endpoint(ch_context *);

/* Fixed finite optimization of the sketch plus the common prior, not exact
 * archived-history descent. At most 16 rounds and eight fractions per round.
 * Positive-definite metric is required without clipping/repair. A finite
 * unresolved stop is explicit and is not nonlinear stationarity. Full-step
 * trial uses the represented candidate exactly. Origin/support never move.
 * Callback observes a proposal (fraction=UINT32_MAX) and each evaluated trial.
 */
int ch_refine(ch_context *, unsigned max_rounds, ch_trace_callback, void *);

#endif
