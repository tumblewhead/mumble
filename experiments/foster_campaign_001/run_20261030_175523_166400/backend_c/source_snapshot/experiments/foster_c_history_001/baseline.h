#ifndef FOSTER_BASELINE_H
#define FOSTER_BASELINE_H
#include <stddef.h>
#include <stdint.h>
#ifndef FB_MODEL_STAGE
#define FB_MODEL_STAGE 2
#endif
#ifndef FB_HISTORY_STAGE
#define FB_HISTORY_STAGE 2
#endif
#define FB_D 16
#define FB_BLOCK 16
#define FB_TOKEN_MAX 3537
/* Fixed dense double baseline. No allocation, global mutable state or truth input.
 * A context belongs to one immutable caller-bound source/configuration session.
 * Serialized, synchronous API: caller must not mutate context or call concurrently.
 * No reboot persistence, externally supplied tokens, or interrupt atomicity. */
enum { FB_OK=0, FB_RETIRED=1, FB_ORDER=-1, FB_INPUT=-2, FB_FULL=-3,
       FB_MODEL=-4, FB_NUMERIC=-5, FB_FORMAT=-6 };
enum { FB_ROUND_LIMIT=0, FB_GRADIENT=1, FB_STEP=2, FB_NO_DESCENT=3 };
typedef struct { double mean[16], root[256], logZ; } FBMessage;
typedef struct {
    double cal[14]; int rounds, fractions, encoding;
    double gradient_tol, step_tol;
} FBConfig;
typedef struct { double v[16], J[256], end[16], F[256]; } FBPhysical;
typedef struct {
    uint64_t model_calls, model_success, fit_evaluations, rounds, trials, tokens;
    uint64_t stops[4];
    /* Host profiling only; zero when built without FB_PROFILE. */
    double model_s, before_s, fit_s, token_s, history_s, domain_s;
} FBProfile;
/* History scratch has explicit ownership; never aliases input/output/token. */
typedef struct {
    double B[256], C[256], r[17], w[16], delta[16], end[16], row[16];
} FBHistoryWork;
typedef struct {
    FBConfig config;
    FBMessage message, candidate;
    uint64_t source_id, next_index, retired_index, ticks, retired_ticks, generation;
    int pending, stop, rounds, evaluations, token_bytes;
    double cost, initial_rms, fitted_rms;
    double obs[80], w[16], residual[16], anchor[16];
#if FB_HISTORY_STAGE >= 2
    union {
        struct {
            double thermal[FB_BLOCK*11];
            FBPhysical current;
            union {
                FBPhysical trial;
                struct { double B[256], P[256]; } matrices;
            } transient;
        } fit;
        FBHistoryWork history;
    } phase;
#else
#if FB_MODEL_STAGE >= 2
    /* Replaces the redundant initial-prediction output set. Rebuilt per flush. */
    double thermal[FB_BLOCK*11];
#else
    FBPhysical before;
#endif
    FBPhysical current, trial;
#endif
    unsigned char token[FB_TOKEN_MAX];
    FBProfile profile;
} FBContext;
int foster_predict(const double *,const double *,int,const double *,double *,double *,double *,double *);
int foster_thermal(const double *,int,const double *,double *);
int foster_predict_cached(const double *,const double *,int,const double *,const double *,double *,double *,double *,double *);
int fb_init(FBContext *, const FBConfig *, const FBMessage *, uint64_t source_id);
int fb_offer(FBContext *, uint64_t index, const double observation[5]);
/* Empty flush is a no-op. Failure preserves committed message AND pending input.
 * Retry with fb_flush; never reoffer an accepted sample after retirement failure. */
int fb_flush(FBContext *);
/* Pure generic history operation; no model/observations/test-rig dependency. */
int fb_history(const FBMessage *, const unsigned char *, size_t, FBMessage *);
int fb_history_work(const FBMessage *, const unsigned char *, size_t, FBMessage *, FBHistoryWork *);
int fb_token(const double anchor[16],const FBPhysical *,const double *,int,int,unsigned char *);
/* General partial-pivot LU, Cholesky, and Householder QR; matrices overwritten. */
int fb_solve(double a[256],double b[16]);
int fb_cholesky(double a[256]);
int fb_qr(double a[289]);
double fb_now(void);
size_t fb_context_bytes(void);
size_t fb_profile_bytes(void);
void fb_get_message(const FBContext *, double out[273]);
void fb_get_profile(const FBContext *, FBProfile *);
/* Host/test adapter, output row=mean16, marginalSD16, logZ, index, stop, calls.
 * Output capacity is explicit; no ownership release if capacity is insufficient. */
int fb_replay(FBContext *, const double *, size_t, double *, size_t, size_t *);
#endif
