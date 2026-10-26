#ifndef MUMBLE_BOUNDARY_TRANSACTION_CAPTURE_H
#define MUMBLE_BOUNDARY_TRANSACTION_CAPTURE_H

/* Host-fixture capture only. This object is caller-owned and does not change
 * the production state, workspace, query, or checkpoint ABI. */
#include "scm_online.h"

enum {
    BOUNDARY_STAGE_NONE=0,
    BOUNDARY_STAGE_OBSERVATION,
    BOUNDARY_STAGE_INNOVATION,
    BOUNDARY_STAGE_PROJECTION,
    BOUNDARY_STAGE_INNOVATION_SD,
    BOUNDARY_STAGE_OPTIMAL_ROTATION,
    BOUNDARY_STAGE_STANDARD,
    BOUNDARY_STAGE_RAW_CHANGE,
    BOUNDARY_STAGE_MEAN_DOMAIN,
    BOUNDARY_STAGE_JOSEPH_SD,
    BOUNDARY_STAGE_JOSEPH_ROTATION,
    BOUNDARY_STAGE_FINAL_OBSERVATION,
    BOUNDARY_STAGE_VALIDATION
};

typedef struct {
    int stage, coordinate, column;
    unsigned fallback_mask;
    int boundary_coordinate;
    double mean_before, raw_gain, standard, raw_change, scale;
    double selected_gain, proposed_mean;
} boundary_capture;

void fixture_capture_reset(boundary_capture *capture);
int fixture_ingest(scm_online *state,
    const unsigned char source_id[SCM_ONLINE_SOURCE_BYTES],
    uint64_t sample_index,const scm_sample *input,int voltage_present,
    scm_online_workspace *workspace,boundary_capture *capture);
int fixture_select(scm_online *state,scm_online_workspace *workspace,
    double standard,boundary_capture *capture);

#endif
