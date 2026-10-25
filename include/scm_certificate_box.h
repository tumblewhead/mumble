#ifndef SCM_CERTIFICATE_BOX_H
#define SCM_CERTIFICATE_BOX_H

#include "scm_certificate.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Stability004 adapts the stability003 conditional certificate provider.
 * At most one of the three static RC modes has a nondegenerate R/tau box;
 * all other modes are fixed. Actual R and tau may be real anywhere in their
 * closed boxes and remain fixed for the certified episode. Common RC state
 * intervals enclose every admitted parameter choice; parameter/state
 * correlations are discarded conservatively, without estimating a center.
 * The known R0/OCV, current/time, voltage-error, SOC/capacity, chronology,
 * initialized/trusted-storage and no-drift premises are inherited from003.
 * No floating point, libm, heap, sample history or lifetime counter is used.
 */
typedef struct {
    uint32_t r_lower_mOhm,r_upper_mOhm;
    uint32_t tau_lower_ticks,tau_upper_ticks;
} scm_certificate_box_mode;

/* R endpoints are ordered in [0,1000]mOhm; tau endpoints are positive and
 * ordered uint32 ticks. A mode is uncertain when either endpoint pair
 * differs. Zero uncertain modes is admitted for exact regression to003.
 * current_limit_uA*r_upper_mOhm must fit the corresponding RC state bound.
 * All capacity cells, common initial states and parameter boxes are immutable
 * for the episode; the complete live configuration belongs in memory counts.
 */
typedef struct {
    uint32_t cells,ocv_knots;
    int32_t initial_soc_lower,initial_soc_upper;
    int32_t current_limit_uA;
    uint32_t r0_mOhm;
    scm_certificate_box_mode mode[SCM_CERTIFICATE_RC];
    scm_stable_interval initial_rc[SCM_CERTIFICATE_RC];
    scm_certificate_capacity capacity[SCM_CERTIFICATE_MAX_CELLS];
    scm_certificate_ocv_knot ocv[SCM_CERTIFICATE_MAX_OCV];
} scm_certificate_box_config;

typedef struct {
    const scm_certificate_box_config *config;
    scm_stable_charge charge;
    scm_stable_mask evidence;
    scm_stable_interval rc[SCM_CERTIFICATE_RC];
    /* Active intervals only contract; excluded cells stay excluded and their
     * stored intervals freeze. No parameter-box or capacity-bin recentering.
     */
    scm_certificate_soc initial_soc[SCM_CERTIFICATE_MAX_CELLS];
} scm_certificate_box_bank;

typedef struct {
    scm_certificate_box_bank staged;
} scm_certificate_box_workspace;

typedef scm_certificate_sample scm_certificate_box_sample;
typedef scm_certificate_result scm_certificate_box_result;

/* Enclose exp(-ticks/tau) for every real tau in the closed supplied interval.
 * Monotonicity in tau permits the unchanged stable kernel's lower endpoint
 * at tau_lower and upper endpoint at tau_upper. Equal endpoints use it once;
 * zero ticks returns exact unity. Invalid tau ranges return ERR_RANGE, and
 * a null output returns ERR_ARGUMENT. Negative returns preserve all output
 * bytes. Output storage must be disjoint from every other live object.
 */
int scm_certificate_box_attenuation(uint32_t ticks,uint32_t tau_lower_ticks,
                                    uint32_t tau_upper_ticks,
                                    scm_stable_attenuation*);

/* Enclose x'=a*x+(1-a)*target for every supplied x,a,target. Both target
 * endpoints are integer state quanta in [-bound,bound]; actual forcing may
 * lie between them. Because 1-a>=0, the old exact-target kernel at the lower
 * target supplies the lower endpoint and at the upper target supplies the
 * upper endpoint. All inputs are validated before exact-unity identity.
 * Negative status leaves the complete state unchanged. State/coefficient
 * storage must be initialized/trusted and disjoint; no overlap is supported.
 */
int scm_certificate_box_interval_step(scm_stable_interval*,
                                      const scm_stable_attenuation*,
                                      int32_t target_lower,int32_t target_upper);

int scm_certificate_box_config_validate(const scm_certificate_box_config*);
/* Destination and configuration storage must be disjoint. The retained
 * configuration pointer remains alive and immutable throughout the episode.
 * Negative status leaves the complete destination bank unchanged.
 */
int scm_certificate_box_init(scm_certificate_box_bank*,
                             const scm_certificate_box_config*);

/* Each actual interval arrives exactly once in acquisition order. Current is
 * constant within the interval and voltage is measured at its endpoint.
 * Bank, configuration, observation and caller-owned workspace are disjoint.
 * A negative return preserves the entire bank and does not propagate the
 * observation; workspace may change. Positive INCONSISTENT commits charge,
 * RC state and sticky empty support. No concurrent mutation is supported.
 */
int scm_certificate_box_push(scm_certificate_box_bank*,
                             const scm_certificate_box_sample*,
                             scm_certificate_box_workspace*);

/* Outer current-SOC/capacity hull from persistent active per-cell intervals.
 * Nonempty support need not prove exact feasibility or useful precision.
 * On positive INCONSISTENT, has_support=0 and numeric fields are not estimates.
 * Negative status preserves output. Bank/configuration/output are disjoint.
 */
int scm_certificate_box_query(const scm_certificate_box_bank*,
                              scm_certificate_box_result*);

#ifdef __cplusplus
}
#endif
#endif
