typedef long int ptrdiff_t;
typedef long unsigned int size_t;
typedef int wchar_t;
typedef struct {
  long long __max_align_ll __attribute__((__aligned__(__alignof__(long long))));
  long double __max_align_ld __attribute__((__aligned__(__alignof__(long double))));
} max_align_t;
  typedef __typeof__(nullptr) nullptr_t;
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpedantic"
typedef unsigned char __u_char;
typedef unsigned short int __u_short;
typedef unsigned int __u_int;
typedef unsigned long int __u_long;
typedef signed char __int8_t;
typedef unsigned char __uint8_t;
typedef signed short int __int16_t;
typedef unsigned short int __uint16_t;
typedef signed int __int32_t;
typedef unsigned int __uint32_t;
typedef signed long int __int64_t;
typedef unsigned long int __uint64_t;
typedef __int8_t __int_least8_t;
typedef __uint8_t __uint_least8_t;
typedef __int16_t __int_least16_t;
typedef __uint16_t __uint_least16_t;
typedef __int32_t __int_least32_t;
typedef __uint32_t __uint_least32_t;
typedef __int64_t __int_least64_t;
typedef __uint64_t __uint_least64_t;
typedef long int __quad_t;
typedef unsigned long int __u_quad_t;
typedef long int __intmax_t;
typedef unsigned long int __uintmax_t;
typedef unsigned long int __dev_t;
typedef unsigned int __uid_t;
typedef unsigned int __gid_t;
typedef unsigned long int __ino_t;
typedef unsigned long int __ino64_t;
typedef unsigned int __mode_t;
typedef unsigned long int __nlink_t;
typedef long int __off_t;
typedef long int __off64_t;
typedef int __pid_t;
typedef struct { int __val[2]; } __fsid_t;
typedef long int __clock_t;
typedef unsigned long int __rlim_t;
typedef unsigned long int __rlim64_t;
typedef unsigned int __id_t;
typedef long int __time_t;
typedef unsigned int __useconds_t;
typedef long int __suseconds_t;
typedef long int __suseconds64_t;
typedef int __daddr_t;
typedef int __key_t;
typedef int __clockid_t;
typedef void * __timer_t;
typedef long int __blksize_t;
typedef long int __blkcnt_t;
typedef long int __blkcnt64_t;
typedef unsigned long int __fsblkcnt_t;
typedef unsigned long int __fsblkcnt64_t;
typedef unsigned long int __fsfilcnt_t;
typedef unsigned long int __fsfilcnt64_t;
typedef long int __fsword_t;
typedef long int __ssize_t;
typedef long int __syscall_slong_t;
typedef unsigned long int __syscall_ulong_t;
typedef __off64_t __loff_t;
typedef char *__caddr_t;
typedef long int __intptr_t;
typedef unsigned int __socklen_t;
typedef int __sig_atomic_t;
typedef __int8_t int8_t;
typedef __int16_t int16_t;
typedef __int32_t int32_t;
typedef __int64_t int64_t;
typedef __uint8_t uint8_t;
typedef __uint16_t uint16_t;
typedef __uint32_t uint32_t;
typedef __uint64_t uint64_t;
typedef __int_least8_t int_least8_t;
typedef __int_least16_t int_least16_t;
typedef __int_least32_t int_least32_t;
typedef __int_least64_t int_least64_t;
typedef __uint_least8_t uint_least8_t;
typedef __uint_least16_t uint_least16_t;
typedef __uint_least32_t uint_least32_t;
typedef __uint_least64_t uint_least64_t;
typedef signed char int_fast8_t;
typedef long int int_fast16_t;
typedef long int int_fast32_t;
typedef long int int_fast64_t;
typedef unsigned char uint_fast8_t;
typedef unsigned long int uint_fast16_t;
typedef unsigned long int uint_fast32_t;
typedef unsigned long int uint_fast64_t;
typedef long int intptr_t;
typedef unsigned long int uintptr_t;
typedef __intmax_t intmax_t;
typedef __uintmax_t uintmax_t;
#pragma GCC diagnostic pop
typedef enum {
    ADC12_OK = 0,
    ADC12_INVALID_ARGUMENT = -1,
    ADC12_INVALID_LENGTH = -2,
    ADC12_CODE_RANGE = -3,
    ADC12_NONCANONICAL_PADDING = -4,
    ADC12_ALIAS = -5,
    ADC12_SOURCE_MISMATCH = -6,
    ADC12_SEQUENCE_MISMATCH = -7,
    ADC12_QUEUE_FULL = -8,
    ADC12_QUEUE_EMPTY = -9,
    ADC12_SEQUENCE_EXHAUSTED = -10,
    ADC12_INVALID_STATE = -11,
    ADC12_INVALID_CALIBRATION = -12,
    ADC12_NONFINITE_RESULT = -13
} adc12_status;
typedef struct {
    uint16_t voltage;
    uint16_t current;
    uint16_t temperature;
} adc12_codes;
typedef struct {
    uint64_t interval_ticks;
    adc12_codes codes;
} adc12_raw_sample;
typedef struct {
    adc12_raw_sample samples[16u];
    unsigned char source_id[32u];
    uint64_t next_sequence;
    uint32_t head;
    uint32_t count;
} adc12_stream;
typedef struct {
    double offset;
    double units_per_code;
} adc12_affine;
typedef struct {
    adc12_affine voltage_V;
    adc12_affine current_A;
    adc12_affine temperature_C;
    double seconds_per_tick;
} adc12_calibration;
typedef struct {
    double dt_s;
    double voltage_V;
    double current_A;
    double temperature_C;
} adc12_reading;
adc12_status adc12_stream_init(adc12_stream *stream,
                               const unsigned char source_id[32u],
                               uint64_t next_sequence);
adc12_status adc12_stream_push(adc12_stream *stream,
                               const unsigned char source_id[32u],
                               uint64_t sequence,
                               const adc12_raw_sample *sample);
adc12_status adc12_stream_peek(const adc12_stream *stream,
                               adc12_raw_sample *sample, uint64_t *sequence);
adc12_status adc12_stream_pop(adc12_stream *stream,
                              adc12_raw_sample *sample, uint64_t *sequence);
adc12_status adc12_convert(const adc12_raw_sample *sample,
                           const adc12_calibration *calibration,
                           adc12_reading *reading);
adc12_status adc12_stream_take(adc12_stream *stream,
                               const adc12_calibration *calibration,
                               adc12_raw_sample *sample, uint64_t *sequence,
                               adc12_reading *reading);
adc12_status adc12_pack(const adc12_codes *codes,
                        unsigned char *packed, size_t packed_bytes);
adc12_status adc12_unpack(const unsigned char *packed, size_t packed_bytes,
                          adc12_codes *codes);
enum { SS_OK=0, SS_UNRESOLVED=1, SS_ERR_ARGUMENT=-1,
       SS_ERR_NONFINITE=-2, SS_ERR_DOMAIN=-3, SS_ERR_METRIC=-4,
       SS_ERR_ALIAS=-5 };
enum { SS_REASON_NONE=0, SS_REASON_NO_DIRECTION=1,
       SS_REASON_ROUNDING=2, SS_REASON_ARITHMETIC=3,
       SS_REASON_NONFINITE=4, SS_REASON_METRIC=5 };
typedef struct {
    double packed[136], gradient[16], point[16];
    double majorizer[16], direction[16];
} ss_workspace;
typedef struct {
    const double *anchor, *sd, *lower, *upper;
    double charge_min_Ah, charge_max_Ah;
} ss_input;
typedef struct {
    double original_slope, original_slope_allowance;
    double tangent_model_decrease, tangent_model_allowance;
    double diagonal_model_decrease, diagonal_model_allowance;
    double min_support_slack, min_step_slack, min_polygon_slack;
    double minimum_majorizer;
    int32_t status, reason;
    uint32_t edges_considered, plane_tests, candidates_considered;
    uint32_t selected_candidate, cholesky_entries, cholesky_products;
    uint32_t dot_products, quadratic_products;
} ss_result;
size_t ss_workspace_bytes(void);
size_t ss_input_bytes(void);
size_t ss_result_bytes(void);
int ss_propose(const ss_input *, ss_workspace *, ss_result *);
enum { SCM_OK=0, SCM_ERR_ARGUMENT=-1, SCM_ERR_DOMAIN=-2, SCM_ERR_NONFINITE=-3 };
typedef struct { double dt, current, voltage; } scm_sample;
typedef struct { size_t n; const double *z, *u; } scm_ocv;
typedef struct {
    int modes;
    double theta[7];
    double tau[3], gamma[2], Q, z0;
    double charge_Ah, elapsed;
    double f[3], a[3];
    double df[3], da[3];
    double hb, ha, dhb[2], dha[2];
} scm_model_state;
typedef struct {
    double ocv, z;
    double X[9];
    double docv[7];
    double dX[7][9];
} scm_model_row;
int scm_model_ntheta(int modes);
int scm_model_nalpha(int modes);
int scm_ocv_validate(const scm_ocv *curve);
int scm_ocv_eval(const scm_ocv *curve,double z,double *value,double *slope);
int scm_model_init(scm_model_state *state,int modes,const double *theta);
int scm_model_step(scm_model_state *state,const scm_ocv *curve,
                   double dt,double current,scm_model_row *row);
int scm_model_predict(const scm_model_row *row,int modes,const double *alpha,
                      double *mu,double *jac_theta);
typedef struct {
    int modes;
    double R0, R[3], tau[3];
    double H, gamma_plus, gamma_minus, Q;
} scm_physical;
typedef struct { double z, v[3], h; } scm_physical_state;
int scm_physical_step(const scm_physical *p,scm_physical_state *state,
                      const scm_ocv *curve,double dt,double current,
                      double *voltage);
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
typedef struct {
    scm_model_state model;
    double ddf[3], dda[3], ddhb[3], ddha[3];
} ch_jet;
typedef struct {
    double upper[703];
    ch_jet jet;
    double origin[16], estimate[16];
    unsigned char source_id[32];
    uint64_t next_index;
    double charge_min_Ah, charge_max_Ah;
    uint64_t model_steps, qr_rows, query_evaluations, prior_evaluations;
    uint64_t proposal_rounds, accepted_steps;
    uint32_t available;
    int32_t last_error;
} ch_bank;
typedef union {
    struct { ch_jet prospective; double row[37]; } ingest;
    struct {
        double packed[136];
        double delta[16], row_gradient[16];
        double gradient[16], point[16];
    } query;
} ch_workspace;
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
    scm_sample sample;
} ch_context;
typedef struct {
    ch_context core;
    unsigned char adc_reserve[448];
    unsigned char checkpoint_codec_reserve[128];
} ch_operational_layout;
typedef void (*ch_trace_callback)(const ch_context *, void *);
extern const double ch_public_mean[16];
extern const double ch_public_sd[16];
extern const double ch_lower[16], ch_upper[16];
extern const unsigned char ch_pair[20][2];
size_t ch_qr_index(unsigned row, unsigned column);
size_t ch_packed_index(unsigned row, unsigned column);
int ch_init(ch_context *, const unsigned char source_id[32], const double origin[16]);
int ch_prepare(ch_context *, const unsigned char source_id[32], uint64_t index);
int ch_push(ch_context *, const unsigned char source_id[32], uint64_t index);
int ch_query(ch_context *, int affine_or_quartic, int curvature, int prior);
int ch_endpoint(ch_context *);
int ch_refine(ch_context *, unsigned max_rounds, ch_trace_callback, void *);
typedef struct {
    double f[3],a[3],df[3],da[3];
    double hb,ha,dhb[2],dha[2];
    double charge_Ah,inverse_Q;
    double tau[3],gamma[2];
    double z,slope,mu;
} lab_query_state;
typedef union {
    struct {
        double packed[136],gradient[16],point[16];
        lab_query_state state;
        adc12_reading decoded;
    } query;
    ss_workspace proposal;
    struct {
        ch_jet prospective;
        double row[37];
        adc12_reading decoded;
        scm_sample model_sample;
    } merge;
} lab_workspace;
typedef union { ch_result evidence; ss_result proposal; } lab_result;
typedef struct {
    ch_bank bank;
    lab_workspace workspace;
    lab_result result;
} lab_core;
typedef struct {
    adc12_raw_sample retained[16u];
    adc12_raw_sample ingress[8u];
    uint64_t next_ingress_sequence;
    uint32_t ingress_head,ingress_count,block_count,phase_and_flags;
} lab_input_store;
typedef struct {
    lab_core core;
    lab_input_store inputs;
    adc12_calibration calibration;
    unsigned char checkpoint_codec_reserve[128u];
} lab_operational_layout;
size_t sh_index(unsigned row,unsigned column);
double sh_feature(const double *origin,const double *point,unsigned feature);
double sh_feature_derivative(const double *origin,const double *point,unsigned feature,unsigned coordinate);
int sh_shift(const double *old_origin,const double *point,double shift[7]);
int sh_translate(double upper[703],const double shift[7]);
int rm_init_jet(ch_jet *out, const double x[16]);
int rm_transport(const ch_jet *boundary, const double old_origin[16],
                 const double point[16], ch_jet *out);
int rm_query_init(lab_query_state *out, const ch_jet *boundary,
                  const double old_origin[16], const double point[16]);
int rm_query_step(lab_query_state *state, const double point[16],
                  const adc12_reading *reading);
double rm_query_derivative(const lab_query_state *state,
                           const double point[16],
                           const adc12_reading *reading, unsigned coordinate);
int rm_merge_step(ch_jet *state, const double origin[16],
                  const scm_sample *sample, double sigma_V, double row[37]);
typedef union {
    unsigned char checkpoint_reserve[128u];
    struct {
        ss_input input;
        double base_cost,base_prior,base_abs,slope,slope_allowance;
    } refine;
} re_aux_workspace;
typedef struct {
    lab_core core;
    lab_input_store inputs;
    adc12_calibration calibration;
    re_aux_workspace auxiliary;
} re_context;
enum { RE_ERR_STATE=-20, RE_ERR_FULL=-21, RE_ERR_EMPTY=-22,
       RE_ERR_ALIAS=-23, RE_ERR_CALIBRATION=-24, RE_ERR_OVERRUN=-25 };
enum { RE_PHASE_READY=1u, RE_PHASE_COMMITTING=2u, RE_PHASE_FAILED=3u,
       RE_PHASE_MASK=15u, RE_FLAG_HISTORY_APPROXIMATE=256u,
       RE_FLAG_BOUNDARY_APPROXIMATE=512u, RE_FLAG_TEMPERATURE_UNMODELED=1024u };
enum { RE_STOP_ROUNDING=7u };
int re_init(re_context *, const unsigned char source_id[32],
            const adc12_calibration *);
int re_offer(re_context *, const unsigned char source_id[32], uint64_t sequence,
             const adc12_raw_sample *);
int re_admit(re_context *);
int re_invalidate(re_context *, int reason);
int re_query(re_context *, int derivatives, int include_prior);
int re_refine(re_context *, unsigned max_rounds);
int re_commit(re_context *);
int re_process(re_context *, unsigned max_rounds);

typedef float float_t;
typedef double double_t;
enum
  {
    FP_INT_UPWARD =
      0,
    FP_INT_DOWNWARD =
      1,
    FP_INT_TOWARDZERO =
      2,
    FP_INT_TONEARESTFROMZERO =
      3,
    FP_INT_TONEAREST =
      4,
  };
extern int __fpclassify (double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __signbit (double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __isinf (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __finite (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __isnan (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __iseqsig (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern int __issignaling (double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
 extern double acos (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __acos (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double asin (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __asin (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double atan (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atan (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double atan2 (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atan2 (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double cos (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __cos (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double sin (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __sin (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double tan (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __tan (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double acospi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __acospi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double acospi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __acospi (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double asinpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __asinpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double asinpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __asinpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double atanpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atanpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double atanpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atanpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double atan2pi (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atan2pi (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double atan2pi (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atan2pi (double __y, double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double cospi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __cospi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double sinpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __sinpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double tanpi (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __tanpi (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double cosh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __cosh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double sinh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __sinh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double tanh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __tanh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double acosh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __acosh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double asinh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __asinh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double atanh (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __atanh (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double exp (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __exp (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double frexp (double __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__)); extern double __frexp (double __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__));
extern double ldexp (double __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__)); extern double __ldexp (double __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__));
 extern double log (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double log10 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log10 (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double modf (double __x, double *__iptr) __attribute__ ((__nothrow__ , __leaf__)); extern double __modf (double __x, double *__iptr) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2)));
 extern double exp10 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __exp10 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double exp2m1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __exp2m1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double exp10m1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __exp10m1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double log2p1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log2p1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double log10p1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log10p1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double logp1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __logp1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double expm1 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __expm1 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double log1p (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log1p (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double logb (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __logb (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double exp2 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __exp2 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double log2 (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __log2 (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double pow (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __pow (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double sqrt (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __sqrt (double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern double hypot (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __hypot (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
 extern double cbrt (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __cbrt (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double compoundn (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __compoundn (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
extern double pown (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __pown (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern double powr (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __powr (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double powr (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __powr (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double rootn (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __rootn (double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern double rsqrt (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __rsqrt (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double ceil (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fabs (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double floor (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fmod (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __fmod (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern int isinf (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int finite (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern double drem (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __drem (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double significand (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __significand (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double copysign (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double nan (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__)); extern double __nan (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__));
extern int isnan (double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern double j0 (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __j0 (double) __attribute__ ((__nothrow__ , __leaf__));
extern double j1 (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __j1 (double) __attribute__ ((__nothrow__ , __leaf__));
extern double jn (int, double) __attribute__ ((__nothrow__ , __leaf__)); extern double __jn (int, double) __attribute__ ((__nothrow__ , __leaf__));
extern double y0 (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __y0 (double) __attribute__ ((__nothrow__ , __leaf__));
extern double y1 (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __y1 (double) __attribute__ ((__nothrow__ , __leaf__));
extern double yn (int, double) __attribute__ ((__nothrow__ , __leaf__)); extern double __yn (int, double) __attribute__ ((__nothrow__ , __leaf__));
 extern double erf (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __erf (double) __attribute__ ((__nothrow__ , __leaf__));
 extern double erfc (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __erfc (double) __attribute__ ((__nothrow__ , __leaf__));
extern double lgamma (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __lgamma (double) __attribute__ ((__nothrow__ , __leaf__));
extern double tgamma (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __tgamma (double) __attribute__ ((__nothrow__ , __leaf__));
extern double gamma (double) __attribute__ ((__nothrow__ , __leaf__)); extern double __gamma (double) __attribute__ ((__nothrow__ , __leaf__));
extern double lgamma_r (double, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__)); extern double __lgamma_r (double, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__));
extern double rint (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __rint (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double nextafter (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __nextafter (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double nexttoward (double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __nexttoward (double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double nextdown (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __nextdown (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double nextup (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __nextup (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double remainder (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __remainder (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double scalbn (double __x, int __n) __attribute__ ((__nothrow__ , __leaf__)); extern double __scalbn (double __x, int __n) __attribute__ ((__nothrow__ , __leaf__));
extern int ilogb (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern int __ilogb (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int llogb (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __llogb (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double scalbln (double __x, long int __n) __attribute__ ((__nothrow__ , __leaf__)); extern double __scalbln (double __x, long int __n) __attribute__ ((__nothrow__ , __leaf__));
extern double nearbyint (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern double __nearbyint (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double round (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double trunc (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double remquo (double __x, double __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__)); extern double __remquo (double __x, double __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__));
extern long int lrint (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lrint (double __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llrint (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llrint (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int lround (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lround (double __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llround (double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llround (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double fdim (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)); extern double __fdim (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double fmax (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fmin (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fma (double __x, double __y, double __z) __attribute__ ((__nothrow__ , __leaf__)); extern double __fma (double __x, double __y, double __z) __attribute__ ((__nothrow__ , __leaf__));
extern double roundeven (double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fromfp (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern double __fromfp (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern double ufromfp (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern double __ufromfp (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern double fromfpx (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern double __fromfpx (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern double ufromfpx (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern double __ufromfpx (double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern int canonicalize (double *__cx, const double *__x) __attribute__ ((__nothrow__ , __leaf__));
extern double fmaximum (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fminimum (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fmaximum_num (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fminimum_num (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fmaximum_mag (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fminimum_mag (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fmaximum_mag_num (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double fminimum_mag_num (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern double scalb (double __x, double __n) __attribute__ ((__nothrow__ , __leaf__)); extern double __scalb (double __x, double __n) __attribute__ ((__nothrow__ , __leaf__));
extern int __fpclassifyf (float __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __signbitf (float __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __isinff (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __finitef (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __isnanf (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __iseqsigf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern int __issignalingf (float __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
 extern float acosf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __acosf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float asinf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __asinf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float atanf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atanf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float atan2f (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atan2f (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float cosf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __cosf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float sinf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __sinf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float tanf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __tanf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float acospif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __acospif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float acospif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __acospif (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float asinpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __asinpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float asinpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __asinpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float atanpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atanpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float atanpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atanpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float atan2pif (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atan2pif (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float atan2pif (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atan2pif (float __y, float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float cospif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __cospif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float sinpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __sinpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float tanpif (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __tanpif (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float coshf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __coshf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float sinhf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __sinhf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float tanhf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __tanhf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float acoshf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __acoshf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float asinhf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __asinhf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float atanhf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __atanhf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float expf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __expf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float frexpf (float __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__)); extern float __frexpf (float __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__));
extern float ldexpf (float __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__)); extern float __ldexpf (float __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__));
 extern float logf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __logf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float log10f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __log10f (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float modff (float __x, float *__iptr) __attribute__ ((__nothrow__ , __leaf__)); extern float __modff (float __x, float *__iptr) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2)));
 extern float exp10f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __exp10f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float exp2m1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __exp2m1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float exp10m1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __exp10m1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float log2p1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __log2p1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float log10p1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __log10p1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float logp1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __logp1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float expm1f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __expm1f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float log1pf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __log1pf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float logbf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __logbf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float exp2f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __exp2f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float log2f (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __log2f (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float powf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __powf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float sqrtf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __sqrtf (float __x) __attribute__ ((__nothrow__ , __leaf__));
 extern float hypotf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __hypotf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
 extern float cbrtf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __cbrtf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float compoundnf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __compoundnf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
extern float pownf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __pownf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern float powrf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __powrf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float powrf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __powrf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float rootnf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __rootnf (float __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern float rsqrtf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __rsqrtf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float ceilf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fabsf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float floorf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fmodf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __fmodf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern int isinff (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int finitef (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern float dremf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __dremf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float significandf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __significandf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float copysignf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float nanf (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__)); extern float __nanf (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__));
extern int isnanf (float __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern float j0f (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __j0f (float) __attribute__ ((__nothrow__ , __leaf__));
extern float j1f (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __j1f (float) __attribute__ ((__nothrow__ , __leaf__));
extern float jnf (int, float) __attribute__ ((__nothrow__ , __leaf__)); extern float __jnf (int, float) __attribute__ ((__nothrow__ , __leaf__));
extern float y0f (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __y0f (float) __attribute__ ((__nothrow__ , __leaf__));
extern float y1f (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __y1f (float) __attribute__ ((__nothrow__ , __leaf__));
extern float ynf (int, float) __attribute__ ((__nothrow__ , __leaf__)); extern float __ynf (int, float) __attribute__ ((__nothrow__ , __leaf__));
 extern float erff (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __erff (float) __attribute__ ((__nothrow__ , __leaf__));
 extern float erfcf (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __erfcf (float) __attribute__ ((__nothrow__ , __leaf__));
extern float lgammaf (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __lgammaf (float) __attribute__ ((__nothrow__ , __leaf__));
extern float tgammaf (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __tgammaf (float) __attribute__ ((__nothrow__ , __leaf__));
extern float gammaf (float) __attribute__ ((__nothrow__ , __leaf__)); extern float __gammaf (float) __attribute__ ((__nothrow__ , __leaf__));
extern float lgammaf_r (float, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__)); extern float __lgammaf_r (float, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__));
extern float rintf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __rintf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float nextafterf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __nextafterf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float nexttowardf (float __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __nexttowardf (float __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float nextdownf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __nextdownf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float nextupf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __nextupf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float remainderf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __remainderf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float scalbnf (float __x, int __n) __attribute__ ((__nothrow__ , __leaf__)); extern float __scalbnf (float __x, int __n) __attribute__ ((__nothrow__ , __leaf__));
extern int ilogbf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern int __ilogbf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int llogbf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __llogbf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float scalblnf (float __x, long int __n) __attribute__ ((__nothrow__ , __leaf__)); extern float __scalblnf (float __x, long int __n) __attribute__ ((__nothrow__ , __leaf__));
extern float nearbyintf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern float __nearbyintf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float roundf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float truncf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float remquof (float __x, float __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__)); extern float __remquof (float __x, float __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__));
extern long int lrintf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lrintf (float __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llrintf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llrintf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int lroundf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lroundf (float __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llroundf (float __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llroundf (float __x) __attribute__ ((__nothrow__ , __leaf__));
extern float fdimf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)); extern float __fdimf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__));
extern float fmaxf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fminf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fmaf (float __x, float __y, float __z) __attribute__ ((__nothrow__ , __leaf__)); extern float __fmaf (float __x, float __y, float __z) __attribute__ ((__nothrow__ , __leaf__));
extern float roundevenf (float __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fromfpf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern float __fromfpf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern float ufromfpf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern float __ufromfpf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern float fromfpxf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern float __fromfpxf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern float ufromfpxf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern float __ufromfpxf (float __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern int canonicalizef (float *__cx, const float *__x) __attribute__ ((__nothrow__ , __leaf__));
extern float fmaximumf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fminimumf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fmaximum_numf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fminimum_numf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fmaximum_magf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fminimum_magf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fmaximum_mag_numf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float fminimum_mag_numf (float __x, float __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern float scalbf (float __x, float __n) __attribute__ ((__nothrow__ , __leaf__)); extern float __scalbf (float __x, float __n) __attribute__ ((__nothrow__ , __leaf__));
extern int __fpclassifyl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __signbitl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __isinfl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __finitel (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __isnanl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __iseqsigl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern int __issignalingl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
 extern long double acosl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __acosl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double asinl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __asinl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double atanl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atanl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double atan2l (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atan2l (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double cosl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __cosl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double sinl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __sinl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double tanl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __tanl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double acospil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __acospil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double acospil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __acospil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double asinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __asinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double asinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __asinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double atanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double atanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double atan2pil (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atan2pil (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double atan2pil (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atan2pil (long double __y, long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double cospil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __cospil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double sinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __sinpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double tanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __tanpil (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double coshl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __coshl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double sinhl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __sinhl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double tanhl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __tanhl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double acoshl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __acoshl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double asinhl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __asinhl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double atanhl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __atanhl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double expl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __expl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double frexpl (long double __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__)); extern long double __frexpl (long double __x, int *__exponent) __attribute__ ((__nothrow__ , __leaf__));
extern long double ldexpl (long double __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__)); extern long double __ldexpl (long double __x, int __exponent) __attribute__ ((__nothrow__ , __leaf__));
 extern long double logl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __logl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double log10l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __log10l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double modfl (long double __x, long double *__iptr) __attribute__ ((__nothrow__ , __leaf__)); extern long double __modfl (long double __x, long double *__iptr) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2)));
 extern long double exp10l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __exp10l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double exp2m1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __exp2m1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double exp10m1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __exp10m1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double log2p1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __log2p1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double log10p1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __log10p1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double logp1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __logp1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double expm1l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __expm1l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double log1pl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __log1pl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double logbl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __logbl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double exp2l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __exp2l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double log2l (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __log2l (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double powl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __powl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double sqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __sqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
 extern long double hypotl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __hypotl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
 extern long double cbrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __cbrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double compoundnl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __compoundnl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double pownl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __pownl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern long double powrl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __powrl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double powrl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __powrl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double rootnl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __rootnl (long double __x, long long int __y) __attribute__ ((__nothrow__ , __leaf__));
 extern long double rsqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __rsqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double ceill (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fabsl (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double floorl (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fmodl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __fmodl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern int isinfl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int finitel (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern long double dreml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __dreml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double significandl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __significandl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double copysignl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double nanl (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nanl (const char *__tagb) __attribute__ ((__nothrow__ , __leaf__));
extern int isnanl (long double __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern long double j0l (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __j0l (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double j1l (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __j1l (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double jnl (int, long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __jnl (int, long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double y0l (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __y0l (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double y1l (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __y1l (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double ynl (int, long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __ynl (int, long double) __attribute__ ((__nothrow__ , __leaf__));
 extern long double erfl (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __erfl (long double) __attribute__ ((__nothrow__ , __leaf__));
 extern long double erfcl (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __erfcl (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double lgammal (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __lgammal (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double tgammal (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __tgammal (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double gammal (long double) __attribute__ ((__nothrow__ , __leaf__)); extern long double __gammal (long double) __attribute__ ((__nothrow__ , __leaf__));
extern long double lgammal_r (long double, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__)); extern long double __lgammal_r (long double, int *__signgamp) __attribute__ ((__nothrow__ , __leaf__));
extern long double rintl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __rintl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double nextafterl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nextafterl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double nexttowardl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nexttowardl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double nextdownl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nextdownl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double nextupl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nextupl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double remainderl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __remainderl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double scalbnl (long double __x, int __n) __attribute__ ((__nothrow__ , __leaf__)); extern long double __scalbnl (long double __x, int __n) __attribute__ ((__nothrow__ , __leaf__));
extern int ilogbl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern int __ilogbl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int llogbl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __llogbl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double scalblnl (long double __x, long int __n) __attribute__ ((__nothrow__ , __leaf__)); extern long double __scalblnl (long double __x, long int __n) __attribute__ ((__nothrow__ , __leaf__));
extern long double nearbyintl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long double __nearbyintl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double roundl (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double truncl (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double remquol (long double __x, long double __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__)); extern long double __remquol (long double __x, long double __y, int *__quo) __attribute__ ((__nothrow__ , __leaf__));
extern long int lrintl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lrintl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llrintl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llrintl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long int lroundl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long int __lroundl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
__extension__
extern long long int llroundl (long double __x) __attribute__ ((__nothrow__ , __leaf__)); extern long long int __llroundl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern long double fdiml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)); extern long double __fdiml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern long double fmaxl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fminl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fmal (long double __x, long double __y, long double __z) __attribute__ ((__nothrow__ , __leaf__)); extern long double __fmal (long double __x, long double __y, long double __z) __attribute__ ((__nothrow__ , __leaf__));
extern long double roundevenl (long double __x) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fromfpl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern long double __fromfpl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern long double ufromfpl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern long double __ufromfpl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern long double fromfpxl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern long double __fromfpxl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern long double ufromfpxl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__)); extern long double __ufromfpxl (long double __x, int __round, unsigned int __width) __attribute__ ((__nothrow__ , __leaf__));
extern int canonicalizel (long double *__cx, const long double *__x) __attribute__ ((__nothrow__ , __leaf__));
extern long double fmaximuml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fminimuml (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fmaximum_numl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fminimum_numl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fmaximum_magl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fminimum_magl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fmaximum_mag_numl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double fminimum_mag_numl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern long double scalbl (long double __x, long double __n) __attribute__ ((__nothrow__ , __leaf__)); extern long double __scalbl (long double __x, long double __n) __attribute__ ((__nothrow__ , __leaf__));
extern int __fpclassifyf128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __signbitf128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern int __isinff128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __finitef128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __isnanf128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
  __attribute__ ((__const__));
extern int __iseqsigf128 (_Float128 __x, _Float128 __y) __attribute__ ((__nothrow__ , __leaf__));
extern int __issignalingf128 (_Float128 __value) __attribute__ ((__nothrow__ , __leaf__))
     __attribute__ ((__const__));
extern float fadd (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float fdiv (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float ffma (double __x, double __y, double __z) __attribute__ ((__nothrow__ , __leaf__));
extern float fmul (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float fsqrt (double __x) __attribute__ ((__nothrow__ , __leaf__));
extern float fsub (double __x, double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float faddl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float fdivl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float ffmal (long double __x, long double __y, long double __z) __attribute__ ((__nothrow__ , __leaf__));
extern float fmull (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern float fsqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern float fsubl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double daddl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double ddivl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double dfmal (long double __x, long double __y, long double __z) __attribute__ ((__nothrow__ , __leaf__));
extern double dmull (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern double dsqrtl (long double __x) __attribute__ ((__nothrow__ , __leaf__));
extern double dsubl (long double __x, long double __y) __attribute__ ((__nothrow__ , __leaf__));
extern int signgam;
enum
  {
    FP_NAN =
      0,
    FP_INFINITE =
      1,
    FP_ZERO =
      2,
    FP_SUBNORMAL =
      3,
    FP_NORMAL =
      4
  };
extern int __iscanonicall (long double __x)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));


extern void *memcpy (void *__restrict __dest, const void *__restrict __src,
       size_t __n) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern void *memmove (void *__dest, const void *__src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern void *memccpy (void *__restrict __dest, const void *__restrict __src,
        int __c, size_t __n)
    __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2))) __attribute__ ((__access__ (__write_only__, 1, 4)));
extern void *memset (void *__s, int __c, size_t __n) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1)));
extern void *memset_explicit (void *__s, int __c, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1))) __attribute__ ((__access__ (__write_only__, 1, 3)));
extern int memcmp (const void *__s1, const void *__s2, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern int __memcmpeq (const void *__s1, const void *__s2, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern void *memchr (const void *__s, int __c, size_t __n)
      __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern char *strcpy (char *__restrict __dest, const char *__restrict __src)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strncpy (char *__restrict __dest,
        const char *__restrict __src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strcat (char *__restrict __dest, const char *__restrict __src)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strncat (char *__restrict __dest, const char *__restrict __src,
        size_t __n) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern int strcmp (const char *__s1, const char *__s2)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern int strncmp (const char *__s1, const char *__s2, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern int strcoll (const char *__s1, const char *__s2)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern size_t strxfrm (char *__restrict __dest,
         const char *__restrict __src, size_t __n)
    __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2))) __attribute__ ((__access__ (__write_only__, 1, 3)));
struct __locale_struct
{
  struct __locale_data *__locales[13];
  const unsigned short int *__ctype_b;
  const int *__ctype_tolower;
  const int *__ctype_toupper;
  const char *__names[13];
};
typedef struct __locale_struct *__locale_t;
typedef __locale_t locale_t;
extern int strcoll_l (const char *__s1, const char *__s2, locale_t __l)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2, 3)));
extern size_t strxfrm_l (char *__dest, const char *__src, size_t __n,
    locale_t __l) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2, 4)))
     __attribute__ ((__access__ (__write_only__, 1, 3)));
extern char *strdup (const char *__s)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__malloc__)) __attribute__ ((__nonnull__ (1)));
extern char *strndup (const char *__string, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__malloc__)) __attribute__ ((__nonnull__ (1)));
extern char *strchr (const char *__s, int __c)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern char *strrchr (const char *__s, int __c)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern char *strchrnul (const char *__s, int __c)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern size_t strcspn (const char *__s, const char *__reject)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern size_t strspn (const char *__s, const char *__accept)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strpbrk (const char *__s, const char *__accept)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strstr (const char *__haystack, const char *__needle)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strtok (char *__restrict __s, const char *__restrict __delim)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2)));
extern char *__strtok_r (char *__restrict __s,
    const char *__restrict __delim,
    char **__restrict __save_ptr)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2, 3)));
extern char *strtok_r (char *__restrict __s, const char *__restrict __delim,
         char **__restrict __save_ptr)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2, 3)));
extern char *strcasestr (const char *__haystack, const char *__needle)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern void *memmem (const void *__haystack, size_t __haystacklen,
       const void *__needle, size_t __needlelen)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 3)))
    __attribute__ ((__access__ (__read_only__, 1, 2)))
    __attribute__ ((__access__ (__read_only__, 3, 4)));
extern void *__mempcpy (void *__restrict __dest,
   const void *__restrict __src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern void *mempcpy (void *__restrict __dest,
        const void *__restrict __src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern size_t strlen (const char *__s)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern size_t strnlen (const char *__string, size_t __maxlen)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern char *strerror (int __errnum) __attribute__ ((__nothrow__ , __leaf__));
extern int strerror_r (int __errnum, char *__buf, size_t __buflen) __asm__ ("" "__xpg_strerror_r") __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (2)))
    __attribute__ ((__access__ (__write_only__, 2, 3)));
extern char *strerror_l (int __errnum, locale_t __l) __attribute__ ((__nothrow__ , __leaf__));

extern int bcmp (const void *__s1, const void *__s2, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern void bcopy (const void *__src, void *__dest, size_t __n)
  __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern void bzero (void *__s, size_t __n) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1)));
extern char *index (const char *__s, int __c)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern char *rindex (const char *__s, int __c)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1)));
extern int ffs (int __i) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern int ffsl (long int __l) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
__extension__ extern int ffsll (long long int __ll)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__const__));
extern int strcasecmp (const char *__s1, const char *__s2)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern int strncasecmp (const char *__s1, const char *__s2, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2)));
extern int strcasecmp_l (const char *__s1, const char *__s2, locale_t __loc)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2, 3)));
extern int strncasecmp_l (const char *__s1, const char *__s2,
     size_t __n, locale_t __loc)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__pure__)) __attribute__ ((__nonnull__ (1, 2, 4)));

extern void explicit_bzero (void *__s, size_t __n) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1)))
    __attribute__ ((__access__ (__write_only__, 1, 2)));
extern char *strsep (char **__restrict __stringp,
       const char *__restrict __delim)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *strsignal (int __sig) __attribute__ ((__nothrow__ , __leaf__));
extern char *__stpcpy (char *__restrict __dest, const char *__restrict __src)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *stpcpy (char *__restrict __dest, const char *__restrict __src)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *__stpncpy (char *__restrict __dest,
   const char *__restrict __src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern char *stpncpy (char *__restrict __dest,
        const char *__restrict __src, size_t __n)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2)));
extern size_t strlcpy (char *__restrict __dest,
         const char *__restrict __src, size_t __n)
  __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2))) __attribute__ ((__access__ (__write_only__, 1, 3)));
extern size_t strlcat (char *__restrict __dest,
         const char *__restrict __src, size_t __n)
  __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__nonnull__ (1, 2))) __attribute__ ((__access__ (__read_write__, 1, 3)));

typedef char re_objects_fit[(sizeof(re_context)==8680) ? 1 : -1];
typedef char re_planning_fit[(sizeof(re_context)+768u +
                             768u<=10240u) ? 1 : -1];
typedef struct { double sum,correction; } re_sum;
static size_t packed(unsigned i,unsigned j)
{
    unsigned k;if(j>i){k=i;i=j;j=k;}
    return (size_t)i*(i+1u)/2u+j;
}
static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=y ? y-x<na : x-y<nb;
}
static int add(re_sum *s,double x)
{
    double n;
    if(!__builtin_isfinite (x))return CH_ERR_NONFINITE;
    n=s->sum+x;if(!__builtin_isfinite (n))return CH_ERR_NONFINITE;
    s->correction+=fabs(s->sum)>=fabs(x)?(s->sum-n)+x:(x-n)+s->sum;
    s->sum=n;
    return __builtin_isfinite (s->correction) && __builtin_isfinite (n+s->correction)?CH_OK:CH_ERR_NONFINITE;
}
static double total(const re_sum *s) { return s->sum+s->correction; }
static double up(double x) { return nextafter(x,(__builtin_inff ())); }
static double add_up(double x,double y) { return up(x+y); }
static double mul_up(double x,double y) { return up(x*y); }
static double allowance(unsigned n,double scale)
{
    double nu=(double)n*0x1p-53,g=up(nu/nextafter(1.-nu,-(__builtin_inff ())));
    return add_up(mul_up(g,scale),mul_up((double)n,0x0.0000000000001p-1022));
}
static int ready(const re_context *c)
{
    uint64_t pending;
    if(!c)return CH_ERR_ARGUMENT;
    if(!c->core.bank.available)return CH_ERR_UNAVAILABLE;
    if((c->inputs.phase_and_flags&RE_PHASE_MASK)!=RE_PHASE_READY)return RE_ERR_STATE;
    if(c->inputs.block_count>16u || c->inputs.ingress_count>8u ||
       c->inputs.ingress_head>=8u)return RE_ERR_STATE;
    pending=(uint64_t)c->inputs.block_count+c->inputs.ingress_count;
    if(c->core.bank.next_index>(18446744073709551615UL)-pending ||
       c->core.bank.next_index+pending!=c->inputs.next_ingress_sequence)return RE_ERR_STATE;
    return CH_OK;
}
static int input_domain(const adc12_reading *r)
{
    if(!__builtin_isfinite (r->dt_s) || !__builtin_isfinite (r->current_A) || !__builtin_isfinite (r->voltage_V) ||
       !__builtin_isfinite (r->temperature_C) || !__builtin_isfinite (r->voltage_V/0.001))return CH_ERR_NONFINITE;
    return r->dt_s>=0. && r->dt_s<=1. && fabs(r->current_A)<=.25 ? CH_OK:CH_ERR_DOMAIN;
}
int re_invalidate(re_context *c,int reason)
{
    if(!c)return CH_ERR_ARGUMENT;
    c->core.bank.available=0;c->core.bank.last_error=reason;
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_FAILED;
    return reason;
}
int re_init(re_context *c,const unsigned char id[32],const adc12_calibration *cal)
{
    adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;int status;
    if(!c || !id || !cal)return CH_ERR_ARGUMENT;
    if(overlap(c,sizeof(*c),id,32) || overlap(c,sizeof(*c),cal,sizeof(*cal)))return RE_ERR_ALIAS;
    if(adc12_convert(&raw,cal,&decoded)!=ADC12_OK)return RE_ERR_CALIBRATION;
    memset(c,0,sizeof(*c));
    memcpy(c->core.bank.source_id,id,32);c->calibration=*cal;
    memcpy(c->core.bank.origin,ch_public_mean,sizeof(c->core.bank.origin));
    memcpy(c->core.bank.estimate,ch_public_mean,sizeof(c->core.bank.estimate));
    status=rm_init_jet(&c->core.bank.jet,ch_public_mean);
    if(status)return re_invalidate(c,status);
    c->core.bank.available=1;
    c->inputs.phase_and_flags=RE_PHASE_READY|RE_FLAG_TEMPERATURE_UNMODELED;
    return CH_OK;
}
int re_offer(re_context *c,const unsigned char id[32],uint64_t sequence,
             const adc12_raw_sample *raw)
{
    adc12_reading decoded;unsigned tail;int status=ready(c);
    if(status)return status;
    if(!id || !raw)return CH_ERR_ARGUMENT;
    if(overlap(c,sizeof(*c),id,32) || overlap(c,sizeof(*c),raw,sizeof(*raw)))return RE_ERR_ALIAS;
    if(memcmp(id,c->core.bank.source_id,32))return CH_ERR_SOURCE;
    if(sequence!=c->inputs.next_ingress_sequence)return CH_ERR_ORDER;
    if(sequence==(18446744073709551615UL))return CH_ERR_OVERFLOW;
    if(c->inputs.ingress_count==8u)return RE_ERR_FULL;
    if(adc12_convert(raw,&c->calibration,&decoded)!=ADC12_OK)return CH_ERR_DOMAIN;
    status=input_domain(&decoded);if(status)return status;
    tail=(c->inputs.ingress_head+c->inputs.ingress_count)%8u;
    c->inputs.ingress[tail]=*raw;++c->inputs.ingress_count;
    ++c->inputs.next_ingress_sequence;return CH_OK;
}
int re_admit(re_context *c)
{
    int status=ready(c);if(status)return status;
    while(c->inputs.block_count<16u && c->inputs.ingress_count) {
        c->inputs.retained[c->inputs.block_count++]=c->inputs.ingress[c->inputs.ingress_head];
        c->inputs.ingress_head=(c->inputs.ingress_head+1u)%8u;
        --c->inputs.ingress_count;
    }
    return CH_OK;
}
static int charge_extrema(re_context *c,double *lo,double *hi)
{
    double charge=c->core.bank.jet.model.charge_Ah;unsigned k;int status;
    *lo=c->core.bank.charge_min_Ah;*hi=c->core.bank.charge_max_Ah;
    for(k=0;k<c->inputs.block_count;k++) {
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,
                         &c->core.workspace.query.decoded)!=ADC12_OK)return CH_ERR_DOMAIN;
        status=input_domain(&c->core.workspace.query.decoded);if(status)return status;
        charge+=c->core.workspace.query.decoded.current_A*
                c->core.workspace.query.decoded.dt_s/3600.;
        if(!__builtin_isfinite (charge))return CH_ERR_NONFINITE;
        *lo=fmin(*lo,charge);*hi=fmax(*hi,charge);
    }
    return CH_OK;
}
static int point_support(const double *x,double cmin,double cmax,double *slack)
{
    double s=((double)1.79769313486231570814527423731704357e+308L),Q,zlo,zhi;unsigned i;
    for(i=0;i<16;i++) {
        if(!__builtin_isfinite (x[i]))return CH_ERR_NONFINITE;
        s=fmin(s,fmin(x[i]-ch_lower[i],ch_upper[i]-x[i]));
    }
    Q=exp(x[5]);if(!__builtin_isfinite (Q) || !(Q>0.))return CH_ERR_NONFINITE;
    zlo=x[11]-cmax/Q;zhi=x[11]-cmin/Q;
    if(!__builtin_isfinite (zlo) || !__builtin_isfinite (zhi))return CH_ERR_NONFINITE;
    s=fmin(s,fmin(zlo,1.-zhi));if(slack)*slack=s;
    return s>=0.?CH_OK:CH_ERR_DOMAIN;
}
static double qr(const ch_bank *b,unsigned row,unsigned col)
{
    return col<row?0.:b->upper[sh_index(row,col)];
}
static int polynomial_row(const ch_bank *b,const double *x,unsigned row,
                           double *residual,double *absolute)
{
    re_sum s={0,0},a={0,0};unsigned k;
    for(k=row;k<37;k++) {
        double term=qr(b,row,k)*sh_feature(b->origin,x,k);
        if(add(&s,term) || add(&a,fabs(term)))return CH_ERR_NONFINITE;
    }
    *residual=total(&s);*absolute=total(&a);return CH_OK;
}
static double polynomial_derivative(const ch_bank *b,const double *x,
                                     unsigned row,unsigned coordinate)
{
    re_sum s={0,0};unsigned k;
    for(k=row;k<37;k++)
        if(add(&s,qr(b,row,k)*sh_feature_derivative(b->origin,x,k,coordinate)))return (__builtin_nanf (""));
    return total(&s);
}
static double precision(unsigned i)
{
    double sd=i==5?.20951093757861336:ch_public_sd[i];return 1./(sd*sd);
}
static int prior(re_context *c,int derivatives)
{
    const double *x=c->core.workspace.query.point;
    re_sum common={0,0},normal={0,0};unsigned i;
    double q0,q1,l0,l1,m,ls,w1,dp,cost;
    if(c->core.bank.prior_evaluations==(18446744073709551615UL))return CH_ERR_OVERFLOW;
    ++c->core.bank.prior_evaluations;
    for(i=0;i<16;i++) {
        double sd=i==5?.20951093757861336:ch_public_sd[i];
        if(add(&normal,log(sd*sd)))return CH_ERR_NONFINITE;
        if(i!=5 && add(&common,(x[i]-ch_public_mean[i])*(x[i]-ch_public_mean[i])*precision(i)))
            return CH_ERR_NONFINITE;
    }
    q0=x[5]-(-3.0907210901048416);q1=x[5]-(-2.536100343415231);
    l0=-.5*q0*q0*precision(5);l1=-.5*q1*q1*precision(5);
    m=fmax(l0,l1);ls=m+log(exp(l0-m)+exp(l1-m));w1=exp(l1-ls);
    cost=.5*total(&common)+.5*total(&normal)+
         8.*log(2.*3.141592653589793238462643383279502884)+log(2.)-ls;
    if(!__builtin_isfinite (cost) || !__builtin_isfinite (w1))return CH_ERR_NONFINITE;
    c->core.result.evidence.prior_cost=cost;
    c->core.result.evidence.total_cost=c->core.result.evidence.likelihood_cost+cost;
    c->core.result.evidence.flags|=CH_FLAG_PRIOR_INCLUDED;
    if(derivatives) {
        c->core.result.evidence.flags|=CH_FLAG_PRIOR_MAJORIZER;
        for(i=0;i<16;i++) {
            double g=(x[i]-ch_public_mean[i])*precision(i);
            if(i==5){dp=(-3.0907210901048416+2.536100343415231)*precision(i);g=q0*precision(i)+w1*dp;}
            c->core.workspace.query.gradient[i]+=g;
            c->core.workspace.query.packed[packed(i,i)]+=precision(i);
            if(!__builtin_isfinite (c->core.workspace.query.gradient[i]) ||
               !__builtin_isfinite (c->core.workspace.query.packed[packed(i,i)]))return CH_ERR_NONFINITE;
        }
    }
    return __builtin_isfinite (c->core.result.evidence.total_cost)?CH_OK:CH_ERR_NONFINITE;
}
static int endpoint(re_context *c,double support)
{
    const lab_query_state *s=&c->core.workspace.query.state;
    const double *x=c->core.workspace.query.point;
    ch_result *r=&c->core.result.evidence;double minimum;unsigned i;
    r->detail.endpoint.SOC=s->z;r->detail.endpoint.min_support_slack=support;
    minimum=fmin(s->z,1.-s->z);
    for(i=0;i<3;i++) {
        r->detail.endpoint.v[i]=s->f[i]*x[7+i]+s->a[i]*x[12+i];
        if(!__builtin_isfinite (r->detail.endpoint.v[i]))return CH_ERR_NONFINITE;
        minimum=fmin(minimum,.25-fabs(r->detail.endpoint.v[i]));
    }
    r->detail.endpoint.h=s->hb+s->ha*x[15];
    if(!__builtin_isfinite (r->detail.endpoint.h) || !__builtin_isfinite (s->z))return CH_ERR_NONFINITE;
    minimum=fmin(minimum,1.-fabs(r->detail.endpoint.h));
    r->detail.endpoint.min_endpoint_slack=minimum;
    if(minimum<0.)r->flags|=CH_FLAG_ENDPOINT_INVALID;
    if(c->inputs.phase_and_flags&RE_FLAG_BOUNDARY_APPROXIMATE)r->flags|=CH_FLAG_ENDPOINT_APPROXIMATE;
    for(i=0;i<16;i++)if(x[i]!=c->core.bank.origin[i])r->flags|=CH_FLAG_ENDPOINT_APPROXIMATE;
    return CH_OK;
}
int re_query(re_context *c,int derivatives,int include_prior)
{
    re_sum cost={0,0},absolute={0,0};double cmin,cmax,slack;unsigned row,i,j,k;
    const double *x;int status=ready(c);
    if(status)return status;
    if((derivatives!=0 && derivatives!=1) || (include_prior!=0 && include_prior!=1))return CH_ERR_ARGUMENT;
    x=c->core.workspace.query.point;
    status=charge_extrema(c,&cmin,&cmax);if(status)return status;
    status=point_support(x,cmin,cmax,&slack);if(status)return status;
    if(c->core.bank.query_evaluations==(18446744073709551615UL))return CH_ERR_OVERFLOW;
    ++c->core.bank.query_evaluations;memset(&c->core.result,0,sizeof(c->core.result));
    if(derivatives) {
        memset(c->core.workspace.query.gradient,0,sizeof(c->core.workspace.query.gradient));
        memset(c->core.workspace.query.packed,0,sizeof(c->core.workspace.query.packed));
    }
    for(row=0;row<37;row++) {
        double r,a;
        status=polynomial_row(&c->core.bank,x,row,&r,&a);if(status)return status;
        if(add(&cost,.5*r*r) || add(&absolute,.5*a*a))return CH_ERR_NONFINITE;
        if(derivatives) {
            for(i=0;i<16;i++) {
                double di=polynomial_derivative(&c->core.bank,x,row,i);
                c->core.workspace.proposal.majorizer[i]=di;
                c->core.workspace.query.gradient[i]+=r*di;
                if(!__builtin_isfinite (di) || !__builtin_isfinite (c->core.workspace.query.gradient[i]))return CH_ERR_NONFINITE;
            }
            for(i=0;i<16;i++)for(j=0;j<=i;j++)
                c->core.workspace.query.packed[packed(i,j)]+=
                    c->core.workspace.proposal.majorizer[i]*c->core.workspace.proposal.majorizer[j];
        }
    }
    status=rm_query_init(&c->core.workspace.query.state,&c->core.bank.jet,c->core.bank.origin,x);
    if(status)return status;
    for(k=0;k<c->inputs.block_count;k++) {
        double r,a;
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,&c->core.workspace.query.decoded)!=ADC12_OK)
            return CH_ERR_DOMAIN;
        if(c->core.bank.model_steps==(18446744073709551615UL))return CH_ERR_OVERFLOW;
        ++c->core.bank.model_steps;
        status=rm_query_step(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded);
        if(status)return status;
        r=(c->core.workspace.query.state.mu-c->core.workspace.query.decoded.voltage_V)/0.001;
        a=(fabs(c->core.workspace.query.state.mu)+fabs(c->core.workspace.query.decoded.voltage_V))/0.001;
        if(add(&cost,.5*r*r) || add(&absolute,.5*a*a))return CH_ERR_NONFINITE;
        if(derivatives)for(i=0;i<16;i++) {
            double di=rm_query_derivative(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded,i)/0.001;
            c->core.workspace.query.gradient[i]+=r*di;
            if(!__builtin_isfinite (di) || !__builtin_isfinite (c->core.workspace.query.gradient[i]))return CH_ERR_NONFINITE;
            for(j=0;j<=i;j++) {
                double dj=rm_query_derivative(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded,j)/0.001;
                c->core.workspace.query.packed[packed(i,j)]+=di*dj;
            }
        }
    }
    if(derivatives)for(i=0;i<136;i++)if(!__builtin_isfinite (c->core.workspace.query.packed[i]))return CH_ERR_NONFINITE;
    c->core.result.evidence.likelihood_cost=total(&cost);
    c->core.result.evidence.total_cost=total(&cost);
    c->core.result.evidence.cost_absolute_scale=total(&absolute);
    c->core.result.evidence.flags=CH_FLAG_FEASIBLE|CH_FLAG_COST_AVAILABLE;
    if(include_prior){status=prior(c,derivatives);if(status)return status;}
    return endpoint(c,slack);
}
static int search_stop(re_context *c,unsigned round,unsigned fraction,
                        unsigned reason,int status)
{
    c->core.result.evidence.round=round;c->core.result.evidence.fraction=fraction;
    c->core.result.evidence.stop_reason=reason;return status;
}
int re_refine(re_context *c,unsigned max_rounds)
{
    unsigned round,i,f;int status=ready(c);
    if(status)return status;
    if(!max_rounds || max_rounds>16u)return CH_ERR_ARGUMENT;
    if(!c->inputs.block_count)return RE_ERR_EMPTY;
    for(round=0;round<max_rounds;round++) {
        int accepted=0;
        if(c->core.bank.proposal_rounds==(18446744073709551615UL))return CH_ERR_OVERFLOW;
        ++c->core.bank.proposal_rounds;
        memcpy(c->core.workspace.query.point,c->core.bank.estimate,sizeof(c->core.bank.estimate));
        status=re_query(c,1,1);
        if(status)return search_stop(c,round,(4294967295U),CH_STOP_QUERY,status);
        if(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID)
            return search_stop(c,round,(4294967295U),CH_STOP_QUERY,CH_UNRESOLVED);
        c->auxiliary.refine.base_cost=c->core.result.evidence.total_cost;
        c->auxiliary.refine.base_prior=c->core.result.evidence.prior_cost;
        c->auxiliary.refine.base_abs=c->core.result.evidence.cost_absolute_scale;
        c->auxiliary.refine.input.anchor=c->core.bank.estimate;
        c->auxiliary.refine.input.sd=ch_public_sd;
        c->auxiliary.refine.input.lower=ch_lower;
        c->auxiliary.refine.input.upper=ch_upper;
        status=charge_extrema(c,&c->auxiliary.refine.input.charge_min_Ah,
                               &c->auxiliary.refine.input.charge_max_Ah);
        if(status)return search_stop(c,round,(4294967295U),CH_STOP_QUERY,status);
        status=ss_propose(&c->auxiliary.refine.input,&c->core.workspace.proposal,&c->core.result.proposal);
        if(status) {
            unsigned reason=CH_STOP_METRIC;
            if(status==SS_UNRESOLVED) {
                reason=c->core.result.proposal.reason==SS_REASON_ROUNDING ? RE_STOP_ROUNDING:CH_STOP_DIRECTION;
                status=CH_UNRESOLVED;
            } else if(status==SS_ERR_METRIC)status=CH_UNRESOLVED;
            else if(status==SS_ERR_NONFINITE)status=CH_ERR_NONFINITE;
            else if(status==SS_ERR_DOMAIN)status=CH_ERR_DOMAIN;
            else status=CH_ERR_ARGUMENT;
            memset(&c->core.result,0,sizeof(c->core.result));
            return search_stop(c,round,(4294967295U),reason,status);
        }
        c->auxiliary.refine.slope=c->core.result.proposal.original_slope;
        c->auxiliary.refine.slope_allowance=c->core.result.proposal.original_slope_allowance;
        memset(&c->core.result,0,sizeof(c->core.result));
        for(i=0;i<16;i++)c->core.workspace.query.packed[i]=c->core.workspace.query.point[i];
        for(f=0;f<8u;f++) {
            double alpha=ldexp(1.,-(int)f),delta,guard,required,combine;
            for(i=0;i<16;i++)c->core.workspace.query.point[i]=f==0?
                c->core.workspace.query.packed[i]:c->core.bank.estimate[i]+
                alpha*(c->core.workspace.query.packed[i]-c->core.bank.estimate[i]);
            status=re_query(c,0,1);
            if(status==CH_ERR_DOMAIN) {
                memset(&c->core.result,0,sizeof(c->core.result));
                continue;
            }
            if(status)return search_stop(c,round,f,CH_STOP_QUERY,status);
            delta=c->auxiliary.refine.base_cost-c->core.result.evidence.total_cost;
            guard=add_up(allowance(65536,add_up(c->auxiliary.refine.base_abs,c->core.result.evidence.cost_absolute_scale)),
                         allowance(256,add_up(fabs(c->auxiliary.refine.base_prior),fabs(c->core.result.evidence.prior_cost))));
            guard=add_up(guard,allowance(16,add_up(fabs(c->auxiliary.refine.base_cost),fabs(c->core.result.evidence.total_cost))));
            required=mul_up(.25,mul_up(alpha,add_up(c->auxiliary.refine.slope,c->auxiliary.refine.slope_allowance)));
            combine=allowance(32,add_up(add_up(fabs(delta),guard),required));
            if(!__builtin_isfinite (delta) || !__builtin_isfinite (guard) || !__builtin_isfinite (required) || !__builtin_isfinite (combine))
                return search_stop(c,round,f,CH_STOP_QUERY,CH_ERR_NONFINITE);
            c->core.result.evidence.detail.step.slope=c->auxiliary.refine.slope;
            c->core.result.evidence.detail.step.slope_allowance=c->auxiliary.refine.slope_allowance;
            c->core.result.evidence.detail.step.cost_decrease=delta;
            c->core.result.evidence.detail.step.cost_allowance=guard;
            c->core.result.evidence.detail.step.armijo_required=required;
            c->core.result.evidence.detail.step.combine_allowance=combine;
            c->core.result.evidence.detail.step.alpha=alpha;
            if(!(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID) &&
               delta>guard && delta-guard>required+combine) {
                if(c->core.bank.accepted_steps==(18446744073709551615UL))return CH_ERR_OVERFLOW;
                memcpy(c->core.bank.estimate,c->core.workspace.query.point,sizeof(c->core.bank.estimate));
                ++c->core.bank.accepted_steps;
                c->core.result.evidence.flags|=CH_FLAG_ACCEPTED;accepted=1;break;
            }
        }
        if(!accepted)return search_stop(c,round,8u -1u,CH_STOP_NO_TRIAL,CH_UNRESOLVED);
        search_stop(c,round,f,CH_STOP_ROUND_LIMIT,CH_UNRESOLVED);
    }
    return CH_UNRESOLVED;
}
static int qr_append(ch_bank *b,double *row)
{
    unsigned i,k;
    for(i=0;i<37;i++)if(!__builtin_isfinite (row[i]))return CH_ERR_NONFINITE;
    for(i=0;i<37;i++) {
        size_t ii=sh_index(i,i);double a=b->upper[ii],v=row[i],scale,aa,bb,h,cs,sn,r;
        if(!__builtin_isfinite (a))return CH_ERR_NONFINITE;
        if(v==0.)continue;
        scale=fmax(fabs(a),fabs(v));aa=a/scale;bb=v/scale;h=hypot(aa,bb);
        cs=aa/h;sn=bb/h;r=scale*h;
        if(!__builtin_isfinite (r) || !(r>0.))return CH_ERR_NONFINITE;
        b->upper[ii]=r;row[i]=0.;
        for(k=i+1;k<37;k++) {
            size_t ik=sh_index(i,k);double old=b->upper[ik],tail=row[k];
            b->upper[ik]=cs*old+sn*tail;row[k]=-sn*old+cs*tail;
            if(!__builtin_isfinite (b->upper[ik]) || !__builtin_isfinite (row[k]))return CH_ERR_NONFINITE;
        }
    }
    return CH_OK;
}
int re_commit(re_context *c)
{
    unsigned i,k,count;int changed=0,status=ready(c);
    if(status)return status;
    count=c->inputs.block_count;if(!count)return RE_ERR_EMPTY;
    if(c->core.bank.qr_rows>(18446744073709551615UL)-count || c->core.bank.model_steps>(18446744073709551615UL)-2u*count ||
       c->core.bank.next_index>(18446744073709551615UL)-count)return CH_ERR_OVERFLOW;
    memcpy(c->core.workspace.query.point,c->core.bank.estimate,sizeof(c->core.bank.estimate));
    status=re_query(c,0,0);if(status)return status;
    if(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID)return CH_ERR_DOMAIN;
    status=rm_transport(&c->core.bank.jet,c->core.bank.origin,c->core.bank.estimate,
                         &c->core.workspace.merge.prospective);
    if(status)return status;
    status=sh_shift(c->core.bank.origin,c->core.bank.estimate,c->core.workspace.merge.row);
    if(status)return status;
    for(i=0;i<16;i++)if(c->core.bank.estimate[i]!=c->core.bank.origin[i])changed=1;
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_COMMITTING;
    status=sh_translate(c->core.bank.upper,c->core.workspace.merge.row);
    if(status)return re_invalidate(c,CH_ERR_NONFINITE);
    c->core.bank.jet=c->core.workspace.merge.prospective;
    if(changed && c->core.bank.next_index)c->inputs.phase_and_flags|=RE_FLAG_BOUNDARY_APPROXIMATE;
    memcpy(c->core.bank.origin,c->core.bank.estimate,sizeof(c->core.bank.origin));
    for(k=0;k<count;k++) {
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,&c->core.workspace.merge.decoded)!=ADC12_OK)
            return re_invalidate(c,CH_ERR_DOMAIN);
        c->core.workspace.merge.model_sample.dt=c->core.workspace.merge.decoded.dt_s;
        c->core.workspace.merge.model_sample.current=c->core.workspace.merge.decoded.current_A;
        c->core.workspace.merge.model_sample.voltage=c->core.workspace.merge.decoded.voltage_V;
        c->core.workspace.merge.prospective=c->core.bank.jet;
        if(c->core.bank.model_steps==(18446744073709551615UL))return re_invalidate(c,CH_ERR_OVERFLOW);
        ++c->core.bank.model_steps;
        status=rm_merge_step(&c->core.workspace.merge.prospective,c->core.bank.origin,
                             &c->core.workspace.merge.model_sample,0.001,c->core.workspace.merge.row);
        if(status)return re_invalidate(c,status);
        status=qr_append(&c->core.bank,c->core.workspace.merge.row);
        if(status)return re_invalidate(c,status);
        c->core.bank.jet=c->core.workspace.merge.prospective;
        c->core.bank.charge_min_Ah=fmin(c->core.bank.charge_min_Ah,c->core.bank.jet.model.charge_Ah);
        c->core.bank.charge_max_Ah=fmax(c->core.bank.charge_max_Ah,c->core.bank.jet.model.charge_Ah);
    }
    c->core.bank.next_index+=count;c->core.bank.qr_rows+=count;
    memset(c->inputs.retained,0,count*sizeof(c->inputs.retained[0]));
    c->inputs.block_count=0;
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_READY|RE_FLAG_HISTORY_APPROXIMATE;
    return CH_OK;
}
int re_process(re_context *c,unsigned max_rounds)
{
    uint32_t reason,round,fraction;int status=ready(c);
    if(status)return status;
    if(!max_rounds || max_rounds>16u)return CH_ERR_ARGUMENT;
    if(!c->inputs.block_count)return RE_ERR_EMPTY;
    status=re_refine(c,max_rounds);
    if(status<0)return re_invalidate(c,status);
    reason=c->core.result.evidence.stop_reason;round=c->core.result.evidence.round;
    fraction=c->core.result.evidence.fraction;
    status=re_commit(c);
    if(status)return re_invalidate(c,status);
    c->core.result.evidence.stop_reason=reason;c->core.result.evidence.round=round;
    c->core.result.evidence.fraction=fraction;return CH_OK;
}
