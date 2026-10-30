#ifndef MUMBLE_HISTORY_PROVIDER_001_H
#define MUMBLE_HISTORY_PROVIDER_001_H

#include <stddef.h>
#include <stdint.h>

/* Desktop comparison boundary, not an additional firmware allocation.
 * Original16-coordinate entering chart; likelihood only, original prior
 * belongs to the solver exactly once. Queries never mutate owned history.
 * GN is an optimization metric, NOT a Hessian or posterior precision.
 * endpoint = current SOC, v1, v2, v3, h.
 * represented_rows + retained_rows counts owned observations once.
 * No endpoint Jacobian, approximation bound or uncertainty certificate is
 * supplied by these legacy adapters. Numeric success is not fidelity success.
 */
enum { HP_REPLAY=1, HP_LEGACY_COMPACT=2, HP_ERR_BLOCK_FULL=-100 };
typedef struct {
    double likelihood, gradient[16], gn_packed[136], endpoint[5];
    uint64_t represented_rows, retained_rows;
    int status;
    unsigned provider_kind, legacy_flags;
} hp_query_result;

int hp_exact_query(const double *decoded_dt_I_V, size_t count,
                   const double x[16], hp_query_result *out);
int hp_compact_query(const void *context, const double x[16], hp_query_result *out);

/* Fixture/adapter operations only; opaque context is the unchanged re_context.
 * Must be suitably aligned and sized by hp_context_bytes(). Caller serializes
 * all operations and supplies disjoint buffers. Calibration is the frozen host
 * study fixture, not a device default. No optimizer is run by these functions.
 */
size_t hp_context_bytes(void);
int hp_context_init(void *context, const unsigned char source[32]);
int hp_append(void *context, const unsigned char source[32], uint64_t index,
              uint64_t ticks, unsigned voltage, unsigned current, unsigned temperature);
int hp_commit_at(void *context, const double x[16]);
int hp_decode(uint64_t ticks, unsigned voltage, unsigned current,
              unsigned temperature, double decoded_dt_I_V[3]);
#endif
