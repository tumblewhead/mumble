typedef long int ptrdiff_t;
typedef long unsigned int size_t;
typedef int wchar_t;
typedef struct {
  long long __max_align_ll __attribute__((__aligned__(__alignof__(long long))));
  long double __max_align_ld __attribute__((__aligned__(__alignof__(long double))));
} max_align_t;
  typedef __typeof__(nullptr) nullptr_t;
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
const double ch_public_mean[16] = {
    -3.0484125313829042, -.7458274383888583, 1.90333124488516,
    5.0106352940962555, 5.703782474656201, -2.8134107167600364,
    .1, .1, .1, .1, .024, .68, 0., 0., 0., 0.
};
const double ch_public_sd[16] = {
    .664699061636066, .664699061636066, .8647934172782233,
    1.5821241788613198, 1.5821241788613198, .347557011337284,
    .2886751345948129, .2886751345948129, .2886751345948129,
    .2886751345948129, .02886751345948129, .21650635094610968,
    .046188021535170064, .046188021535170064, .046188021535170064,
    .5773502691896258
};
const double ch_lower[16] = {
    -4.199705077879927, -1.8971199848858813, .40546510810816438,
    1.6094379124341003, 1.6094379124341003, -3.5065578973199818,
    0., 0., 0., 0., 0., .2, -.08, -.08, -.08, -1.
};
const double ch_upper[16] = {
    -1.8971199848858813, .40546510810816438, 3.4011973816621555,
    7.0900768357760917, 7.0900768357760917, -2.3025850929940455,
    1., 1., 1., 1., .1, .95, .08, .08, .08, 1.
};
const unsigned char ch_pair[20][2] = {
    {0,0},{0,7},{0,12}, {1,1},{1,8},{1,13}, {2,2},{2,9},{2,14},
    {3,3},{3,4},{4,4}, {3,10},{3,15},{4,10},{4,15}, {10,15},
    {11,11},{5,11},{5,5}
};
