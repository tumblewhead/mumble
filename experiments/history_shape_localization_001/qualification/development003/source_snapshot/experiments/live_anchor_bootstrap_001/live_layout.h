#ifndef MUMBLE_LIVE_LAYOUT_H
#define MUMBLE_LIVE_LAYOUT_H

/* Concrete phase-liveness schema for the selected NEXT integration.
 * This header is sizeof-qualified; it is not an implemented rolling estimator.
 * Old compact_history functions cannot be called on it or on a quadratic-first
 * factor. The standalone adc12_stream is NOT additionally owned here.
 */
#include "adc12.h"
#include "support_step.h"
#include "../compact_nonlinear_history_001/compact_history.h"

#define LAB_BLOCK_DEPTH 16u
#define LAB_INGRESS_DEPTH 8u
#define LAB_CODEC_RESERVE 128u
#define LAB_OWN_STACK_CAP 768u
#define LAB_RUNTIME_IRQ_CALLER_CAP 768u
#define LAB_SRAM_LIMIT 10240u

/* First-order current-block query state. Initial values/derivatives come
 * from the carried boundary polynomial; future recurrence is nonlinear.
 * Individual Jacobian entries are generated on demand, not stored in a
 * second16-vector or scm_model_row. Query does not advance committed state.
 */
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
    /* Field-size reuse only; the new methods must use quadratic-first QR. */
    ch_bank bank;
    lab_workspace workspace;
    lab_result result;
} lab_core;

typedef struct {
    adc12_raw_sample retained[LAB_BLOCK_DEPTH];
    adc12_raw_sample ingress[LAB_INGRESS_DEPTH];
    uint64_t next_ingress_sequence;
    uint32_t ingress_head,ingress_count,block_count,phase_and_flags;
    /* Source ID and committed cursor are already owned by bank.
     * The retained block starts at bank.next_index; later sequences follow
     * from block_count and the serialized ingress cursor. */
} lab_input_store;

typedef struct {
    lab_core core;
    lab_input_store inputs;
    adc12_calibration calibration; /* Count all56 bytes even if flash is possible. */
    unsigned char checkpoint_codec_reserve[LAB_CODEC_RESERVE];
} lab_operational_layout;

#endif
