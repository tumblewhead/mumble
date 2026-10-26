/* Design-only storage probe for the proposed two-component learner.
 *
 * This file implements no filtering, checkpoint codec, acquisition, or math
 * kernel. It preserves the current component fields while packing the lower
 * factor. The serialized codec size and the target reserves below are design
 * requirements, not measured implementation or target costs.
 */
#include "scm_online.h"
#include <stdint.h>
#include <stdio.h>

enum {
    PROPOSED_COMPONENTS=2,
    PROPOSED_FACTOR_ENTRIES=SCM_ONLINE_DIM*(SCM_ONLINE_DIM+1)/2,
    PROPOSED_BANK_HEADER_BYTES=32,
    PROPOSED_CODEC_BUFFER_BYTES=128,
    PROPOSED_ACQUISITION_SAMPLES=16,
    PROPOSED_ACQUISITION_METADATA_BYTES=64,
    PROPOSED_STACK_RUNTIME_RESERVE_BYTES=2048,
    PROPOSED_CHECKPOINT_BYTES=3004,
    PROPOSED_SUBSYSTEM_CEILING_BYTES=10240
};

/* Same fields and order as scm_online; only factor[256] becomes factor[136].
 * Keeping duplicated component metadata/configuration is deliberate: no
 * unimplemented shared-field compaction is credited to this design. */
typedef struct {
    scm_online_config config;
    double mean[SCM_ONLINE_DIM];
    double factor[PROPOSED_FACTOR_ENTRIES];
    uint64_t epoch_begin, next_index, evidence_next_index;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, limited_gain_count, zero_gain_count;
    uint64_t cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double last_current_A, last_prediction_V, last_innovation_V;
    double last_innovation_variance_V2, last_gain_scale, minimum_gain_scale;
    double last_max_gain_scale;
    unsigned last_limited_mask, last_blocked_mask;
    double innovation_ewma;
    unsigned flags, excitation;
    int initialized, has_voltage, prediction_valid;
} proposed_packed_component;

typedef struct {
    uint64_t generation, bank_evidence_next_index;
    /* flags includes initialization mode and has_joint_voltage_evidence. */
    uint32_t flags, active_components;
    uint32_t last_rejection_stage, last_rejection_component;
} proposed_bank_header;

typedef struct {
    proposed_packed_component component[PROPOSED_COMPONENTS];
    double log_weight[PROPOSED_COMPONENTS];
    /* Physical chronology agrees across components; inherited conditional
     * evidence cursors can differ from each other and from this joint cursor. */
    proposed_bank_header header;
} proposed_bank;

typedef struct {
    double vector[4][SCM_ONLINE_DIM];
    double pre_correction_log_likelihood[PROPOSED_COMPONENTS];
} proposed_scratch;

/* An aggregate report has common input chronology, coordinate moments and
 * SOC/Q local moment diagnostics. Component gain diagnostics must be obtained
 * through a serialized component accessor, never averaged into this view. */
typedef struct {
    uint64_t epoch_begin, next_index, evidence_next_index;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double mean[SCM_ONLINE_DIM], coordinate_sd[SCM_ONLINE_DIM];
    double current_soc, capacity_Ah, predicted_voltage_V;
    double soc_local_lower, soc_local_upper;
    double capacity_local_lower_Ah, capacity_local_upper_Ah;
    int point_available, capacity_available, prediction_available, local_ranges_available;
    unsigned flags, excitation;
} proposed_aggregate_query_view;

typedef union {
    scm_online_query_result component;
    proposed_aggregate_query_view aggregate;
} proposed_query_view;

typedef struct {
    /* Consume this view before invoking the other accessor. A second
     * simultaneous component/aggregate report is not included in this budget. */
    proposed_query_view view;
    double log_weight[PROPOSED_COMPONENTS];
    uint32_t component_flags[PROPOSED_COMPONENTS];
    double all_component_soc_capacity_hull[4];
} proposed_query_arena;

typedef struct {
    proposed_bank live, staged;
    proposed_scratch scratch;
    proposed_query_arena query;
    scm_online_config external_config;
    scm_sample input;
} proposed_owned_objects;

typedef struct {
    scm_sample sample[PROPOSED_ACQUISITION_SAMPLES];
    unsigned char metadata[PROPOSED_ACQUISITION_METADATA_BYTES];
} proposed_acquisition_reserve;

typedef struct {
    proposed_owned_objects owned;
    unsigned char checkpoint_codec_buffer[PROPOSED_CODEC_BUFFER_BYTES];
    proposed_acquisition_reserve acquisition;
    /* Explicitly charge both support arrays to RAM in this design. */
    double lower_support[SCM_ONLINE_DIM], upper_support[SCM_ONLINE_DIM];
    /* This allocation is a combined requirement for own-source frames,
     * software math, callers, and interrupt nesting. It is not a measurement. */
    unsigned char all_stack_and_runtime_reserve[PROPOSED_STACK_RUNTIME_RESERVE_BYTES];
} proposed_subsystem_budget;

int main(void)
{
    int checks=0, failed_checks=0;
    size_t total=sizeof(proposed_subsystem_budget);
#define EXPECT_SIZE(type,expected) do { checks++;if(sizeof(type)!=(expected))failed_checks++; } while(0)
    EXPECT_SIZE(double,8u);
    EXPECT_SIZE(proposed_packed_component,1464u);
    EXPECT_SIZE(proposed_bank_header,PROPOSED_BANK_HEADER_BYTES);
    EXPECT_SIZE(proposed_bank,2976u);
    EXPECT_SIZE(proposed_scratch,528u);
    EXPECT_SIZE(scm_online_query_result,536u);
    EXPECT_SIZE(proposed_query_view,536u);
    EXPECT_SIZE(proposed_query_arena,592u);
    EXPECT_SIZE(scm_online_config,56u);
    EXPECT_SIZE(scm_sample,24u);
    EXPECT_SIZE(proposed_owned_objects,7152u);
    EXPECT_SIZE(proposed_acquisition_reserve,448u);
    EXPECT_SIZE(proposed_subsystem_budget,10032u);
#undef EXPECT_SIZE
    checks++;if(sizeof(proposed_aggregate_query_view)>sizeof(scm_online_query_result))failed_checks++;
    checks++;if(total>PROPOSED_SUBSYSTEM_CEILING_BYTES)failed_checks++;
    printf("{\"schema\":\"mumble_nonlinear_evidence_layout_probe_v1\","
        "\"scope\":\"proposed host ABI object layout plus unmeasured target reserves; no filtering or target qualification\","
        "\"sizeof_bytes\":{"
        "\"double\":%zu,\"current_unpacked_component\":%zu,\"packed_component\":%zu,"
        "\"bank_header\":%zu,\"bank\":%zu,\"live_and_staged_banks\":%zu,\"scratch\":%zu,"
        "\"legacy_component_query\":%zu,\"aggregate_query_view\":%zu,\"query_union\":%zu,\"query_arena\":%zu,"
        "\"external_config\":%zu,\"input\":%zu,\"owned_objects\":%zu,"
        "\"checkpoint_codec_buffer\":%u,\"acquisition_samples\":%zu,\"acquisition_metadata\":%u,"
        "\"acquisition_reserve\":%zu,\"RAM_support_arrays\":%zu,\"all_stack_and_runtime_reserve\":%u,"
        "\"total_design_budget\":%zu},"
        "\"expected_total_design_budget\":10032,\"subsystem_ceiling\":10240,"
        "\"headroom_bytes\":%zu,\"over_budget_bytes\":%zu,"
        "\"planned_checkpoint_bytes\":%u,\"planned_two_NVM_slots_bytes\":%u,"
        "\"checks\":%d,\"failed_checks\":%d,"
        "\"result\":\"%s\",\"filtering_calls\":0,\"target_measurement\":false}\n",
        sizeof(double),sizeof(scm_online),sizeof(proposed_packed_component),
        sizeof(proposed_bank_header),sizeof(proposed_bank),2*sizeof(proposed_bank),sizeof(proposed_scratch),
        sizeof(scm_online_query_result),sizeof(proposed_aggregate_query_view),sizeof(proposed_query_view),sizeof(proposed_query_arena),
        sizeof(scm_online_config),sizeof(scm_sample),sizeof(proposed_owned_objects),
        (unsigned)PROPOSED_CODEC_BUFFER_BYTES,(size_t)PROPOSED_ACQUISITION_SAMPLES*sizeof(scm_sample),
        (unsigned)PROPOSED_ACQUISITION_METADATA_BYTES,sizeof(proposed_acquisition_reserve),
        (size_t)2*SCM_ONLINE_DIM*sizeof(double),(unsigned)PROPOSED_STACK_RUNTIME_RESERVE_BYTES,total,
        total<=PROPOSED_SUBSYSTEM_CEILING_BYTES?PROPOSED_SUBSYSTEM_CEILING_BYTES-total:0,
        total>PROPOSED_SUBSYSTEM_CEILING_BYTES?total-PROPOSED_SUBSYSTEM_CEILING_BYTES:0,
        (unsigned)PROPOSED_CHECKPOINT_BYTES,(unsigned)(2*PROPOSED_CHECKPOINT_BYTES),checks,failed_checks,
        failed_checks?"layout_discrepancy":"layout_matches_design");
    return failed_checks?1:0;
}
