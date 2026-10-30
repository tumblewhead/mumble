#ifndef SCM_CERTIFICATE_H
#define SCM_CERTIFICATE_H

#include "scm_stable.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Conditional integer provider: known fixed three-RC model, no hysteresis,
 * known nondecreasing PWL OCV, static capacity and initial SOC. Observation
 * intervals must contain the exact terminal voltage under that model.
 * These are deterministic enclosure semantics, not Gaussian confidence.
 * No floating point, libm, heap, or lifetime counter is used.
 */
#define SCM_CERTIFICATE_MAX_CELLS 64
#define SCM_CERTIFICATE_MAX_OCV 17
#define SCM_CERTIFICATE_RC 3
#define SCM_CERTIFICATE_SOC_ONE INT32_C(65536)
#define SCM_CERTIFICATE_TICKS_HZ UINT32_C(35000)
#define SCM_CERTIFICATE_CHARGE_PER_UAH INT64_C(126000000)
#define SCM_CERTIFICATE_CHARGE_LIMIT INT64_C(17592186044416)
#define SCM_CERTIFICATE_VOLTAGE_LIMIT_NV INT64_C(8000000000)
#define SCM_CERTIFICATE_CURRENT_LIMIT_UA INT32_C(200000)
#define SCM_CERTIFICATE_RESISTANCE_LIMIT_MOHM UINT32_C(1000)

typedef struct {
    uint32_t lower_uAh,upper_uAh;
} scm_certificate_capacity;

typedef struct {
    int32_t lower,upper;
} scm_certificate_soc;

typedef struct {
    int32_t soc;
    int64_t voltage_nV;
} scm_certificate_ocv_knot;

/* The complete immutable backing configuration belongs in memory accounting.
 * Capacity cells are closed and may overlap. Their immutable meaning includes
 * the common initial-SOC interval and common initial-RC box. SOC coordinates
 * are divided by SOC_ONE; exact SOC and capacity may lie between grid points.
 * Known R in milliohms times current in microamperes gives exact nanovolts.
 */
typedef struct {
    uint32_t cells,ocv_knots;
    int32_t initial_soc_lower,initial_soc_upper;
    int32_t current_limit_uA;
    uint32_t r0_mOhm;
    uint32_t r_mOhm[SCM_CERTIFICATE_RC];
    uint32_t tau_ticks[SCM_CERTIFICATE_RC];
    scm_stable_interval initial_rc[SCM_CERTIFICATE_RC];
    scm_certificate_capacity capacity[SCM_CERTIFICATE_MAX_CELLS];
    scm_certificate_ocv_knot ocv[SCM_CERTIFICATE_MAX_OCV];
} scm_certificate_config;

typedef struct {
    const scm_certificate_config *config;
    scm_stable_charge charge;
    scm_stable_mask evidence;
    scm_stable_interval rc[SCM_CERTIFICATE_RC];
    /* Bounds contract while active and stay frozen after exclusion.
     * An inactive cell has no support regardless of its stored bounds.
     */
    scm_certificate_soc initial_soc[SCM_CERTIFICATE_MAX_CELLS];
} scm_certificate_bank;

typedef struct {
    scm_certificate_bank staged;
} scm_certificate_workspace;

typedef struct {
    int32_t current_uA;
    uint32_t ticks;
    int64_t voltage_lower_nV,voltage_upper_nV;
} scm_certificate_sample;

typedef struct {
    int32_t soc_lower,soc_upper;
    uint32_t capacity_lower_uAh,capacity_upper_uAh;
    uint64_t active_mask;
    uint32_t active_cells;
    /* Bounds have meaning only when has_support is nonzero. A nonempty
     * outer enclosure does not prove exact feasibility or useful precision.
     */
    int has_support;
} scm_certificate_result;

int scm_certificate_config_validate(const scm_certificate_config*);
/* Destination bank and backing config storage must be disjoint. The config
 * pointer is retained, so config stays alive and immutable for the episode.
 * Negative returns leave the destination bank unchanged.
 */
int scm_certificate_init(scm_certificate_bank*,const scm_certificate_config*);

/* Caller delivers actual intervals once, in acquisition order. Current is
 * constant within an interval; voltage is measured at its endpoint.
 * Config remains immutable and alive for the bank's entire certified episode.
 * Objects must be initialized/trusted and bank, config, sample and workspace
 * must have disjoint storage. No concurrent mutation is supported.
 * Negative returns preserve the entire bank byte-for-byte; workspace may
 * change. Positive INCONSISTENT commits propagated charge/RC and empty evidence.
 * Excluded cells never return; a rejected observation was not propagated.
 */
int scm_certificate_push(scm_certificate_bank*,const scm_certificate_sample*,
                         scm_certificate_workspace*);

/* Read-only outer hull across all active capacity bins and retained SOC0
 * intervals. No latest-only voltage constraint is used: query evidence comes
 * entirely from persistent per-cell bounds. On INCONSISTENT, has_support=0
 * and numeric bound fields are not estimates. Negative errors leave output
 * unchanged. Bank/config/output storage must be disjoint.
 */
int scm_certificate_query(const scm_certificate_bank*,scm_certificate_result*);

#ifdef __cplusplus
}
#endif
#endif
