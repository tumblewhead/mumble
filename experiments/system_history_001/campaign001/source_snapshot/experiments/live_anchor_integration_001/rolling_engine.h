#ifndef MUMBLE_ROLLING_ENGINE_001_H
#define MUMBLE_ROLLING_ENGINE_001_H

#include "../live_anchor_bootstrap_001/live_layout.h"
#include "rolling_model.h"

/* Experimental causal engine. All sixteen coordinates retain the ORIGINAL
 * entering-state chart. The common prior is evaluated once, never merged as
 * an observation. No file, heap, archive, truth or saved-anchor interface.
 * Context internals are private for writes except workspace.query.point for
 * re_query. A host may read fields for bounded snapshots after an API returns.
 * Calibration is immutable after init; changing it requires a new generation.
 * Source ID must identify the input AND immutable calibration/model contract.
 * All operations require one externally serialized caller. This is not an ISR
 * driver. A hardware overrun must call re_invalidate, never skip input silently.
 */
/* Refinement and checkpoint work are mutually exclusive. The128B formerly
 * reserved for checkpoint coding is now an explicit phase union. Its live
 * pointers are temporary configuration views, never a serializable checkpoint.
 */
typedef union {
    unsigned char checkpoint_reserve[LAB_CODEC_RESERVE];
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

#define RE_SIGMA_V 0.001
#define RE_MAX_ROUNDS 16u
#define RE_FRACTIONS 8u
#define RE_TRIAL_ENDPOINT_OFFSET 0u /* first16 packed doubles, cost-only phase */

enum { RE_ERR_STATE=-20, RE_ERR_FULL=-21, RE_ERR_EMPTY=-22,
       RE_ERR_ALIAS=-23, RE_ERR_CALIBRATION=-24, RE_ERR_OVERRUN=-25 };
enum { RE_PHASE_READY=1u, RE_PHASE_COMMITTING=2u, RE_PHASE_FAILED=3u,
       RE_PHASE_MASK=15u, RE_FLAG_HISTORY_APPROXIMATE=256u,
       RE_FLAG_BOUNDARY_APPROXIMATE=512u, RE_FLAG_TEMPERATURE_UNMODELED=1024u };
enum { RE_STOP_ROUNDING=7u };

/* Init always uses the public mean, an empty factor and cursor zero. Inputs
 * must not alias ctx. Reject invalid calibration without changing ctx. */
int re_init(re_context *, const unsigned char source_id[32],
            const adc12_calibration *);

/* Offer owns only one delivered record in the eight-slot ingress FIFO.
 * Full/invalid/source/order rejection leaves the entire context unchanged.
 * The caller retains a rejected record. admit moves FIFO records to the
 * at-most-sixteen retained raw slots without counting likelihood evidence.
 */
int re_offer(re_context *, const unsigned char source_id[32], uint64_t sequence,
             const adc12_raw_sample *);
int re_admit(re_context *);
int re_invalidate(re_context *, int reason);

/* Point lives in core.workspace.query.point. derivatives=1 computes full
 * original-x gradient and GN+kernel-precision metric. include_prior is0 or1;
 * the cost/gradient always use the exact original supported mixture prior.
 * derivatives=0 leaves packed[136] AND gradient[16] bytewise unchanged. It
 * reuses only query.state+decoded (last256B), point, result and work counters.
 * Thus packed[0..15] can hold the full represented proposal endpoint during
 * line search. Rejected prevalidation leaves factor/state/evidence ownership
 * unchanged. Numerical query failure is explicit and never clipped.
 * Result endpoint contains current SOC,v[3],h at the end of the retained block.
 */
int re_query(re_context *, int derivatives, int include_prior);

/* Refine changes estimate only after finite guarded full-objective descent.
 * It never changes committed factor/jet/cursor or raw ownership. At most16
 * rounds, each with one proposal and eight fractions. Finite work exhaustion
 * or unresolved direction returns CH_UNRESOLVED, not stationarity.
 */
int re_refine(re_context *, unsigned max_rounds);

/* Commit prevalidates the chosen estimate, translates older polynomial,
 * transports its boundary jet approximately, appends every retained record
 * once, and only then retires the block. Any unexpected fault after mutation
 * starts latches unavailable. No query can observe a partial merge.
 */
int re_commit(re_context *);

/* One finite refinement followed by commit. Successful ingestion returns
 * CH_OK even when refinement was finite/unresolved. result.evidence.stop_reason
 * and fraction preserve the last search outcome for host tracing. */
int re_process(re_context *, unsigned max_rounds);

#endif
