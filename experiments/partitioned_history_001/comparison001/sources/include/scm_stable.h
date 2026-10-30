#ifndef SCM_STABLE_H
#define SCM_STABLE_H

/* Isolated integer proof kernels, not an integrated battery estimator.
 * No floating point, libm, heap, lifetime counter, or statistical likelihood.
 * The caller supplies observations in their actual order. Physical units,
 * calibration, missing samples and a durable source/restore protocol are
 * outside these kernels. Public objects must remain initialized and trusted.
 * Negative returns leave the destination byte-for-byte unchanged.
 */
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_STABLE_DEN UINT64_C(4294967296)
#define SCM_STABLE_STATE_MAX INT32_C(1073741824)

enum {
    SCM_STABLE_OK=0,
    SCM_STABLE_INCONSISTENT=1,
    SCM_STABLE_ERR_ARGUMENT=-50,
    SCM_STABLE_ERR_RANGE=-51,
    SCM_STABLE_ERR_OVERFLOW=-52
};

typedef struct {
    int64_t value,lower,upper;
} scm_stable_charge;

/* A finite, immutable interpretation of domain bits is supplied by the
 * caller. Each certificate must conservatively include every compatible
 * domain cell. The kernel only intersects masks; it cannot verify that
 * certificate premise, assign Gaussian coverage, or propagate changing cells.
 */
typedef struct {
    uint64_t domain,active;
} scm_stable_mask;

/* lower/D <= exact attenuation <= upper/D, D=SCM_STABLE_DEN.
 * D itself needs 33 unsigned bits and represents exact unity.
 */
typedef struct {
    uint64_t lower,upper;
} scm_stable_attenuation;

/* Integer endpoints and the exact forcing target use the same declared unit.
 * The enclosed exact state may lie between grid points. 0<=bound<=2^30.
 */
typedef struct {
    int32_t lower,upper,bound;
} scm_stable_interval;

int scm_stable_charge_init(scm_stable_charge*,int64_t lower,int64_t upper,
                          int64_t value);
/* Exact represented-input integral: value += current_code*ticks.
 * All int32/uint32 products fit int64. Accepted prefixes must stay within
 * [lower,upper]. Range/overflow rejection does not consume a sample; the
 * caller must not report a rejected observation as propagated state.
 */
int scm_stable_charge_push(scm_stable_charge*,int32_t current_code,
                          uint32_t ticks);

int scm_stable_mask_init(scm_stable_mask*,uint64_t domain);
/* allowed must be a subset of the nonempty immutable domain. An empty
 * intersection is COMMITTED and returns INCONSISTENT, not an argument error.
 * Uninformative and repeated certificates are exactly idempotent.
 */
int scm_stable_mask_apply(scm_stable_mask*,uint64_t allowed);

/* For exact q=num/den (den>0), encloses exp(-q) without libm. Uses integer
 * outward arithmetic, alternating Taylor bounds on [0,1/8], then at most
 * eight squarings. q=0 returns exact unity. q>=32 returns [0,1]/D.
 * This proves the encoded ratio, not how a continuous plant parameter or
 * sensor measurement should be converted to that ratio.
 */
int scm_stable_attenuation_ratio(uint32_t num,uint32_t den,
                                scm_stable_attenuation*);

int scm_stable_interval_init(scm_stable_interval*,int32_t lower,int32_t upper,
                            int32_t bound);
/* Enclose x'=a*x+(1-a)*target for every x and a in their supplied intervals.
 * The target is exact in the declared state quantum and lies in [-bound,bound].
 * Four bilinear corners are evaluated exactly in int64, then divided outward.
 * Output stays in the same domain. Exact unity attenuation is an identity.
 * Distinct coefficient/state objects are required; no overlap is supported.
 */
int scm_stable_interval_step(scm_stable_interval*,
                             const scm_stable_attenuation*,int32_t target);

#ifdef __cplusplus
}
#endif
#endif
