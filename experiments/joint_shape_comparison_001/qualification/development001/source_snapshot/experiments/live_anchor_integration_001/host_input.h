#ifndef MUMBLE_LIVE_HOST_INPUT_001_H
#define MUMBLE_LIVE_HOST_INPUT_001_H

#include "../live_anchor_bootstrap_001/adc12.h"

#define HP_RECORD_BYTES 32u
#define HP_CANONICAL_RECORDS UINT64_C(504000)

enum { HP_OK=0, HP_ERR_ARGUMENT=-100, HP_ERR_ALIAS=-101,
       HP_ERR_ORDER=-102, HP_ERR_NONFINITE=-103, HP_ERR_DOMAIN=-104,
       HP_ERR_SPAN=-105, HP_ERR_CONVERSION=-106 };

typedef struct {
    uint64_t index;
    double dt_s, current_A, voltage_V;
} hp_observation;

typedef struct {
    /* Signed decoded-minus-original differences, not uncertainty estimates. */
    double dt_s, current_A, voltage_V;
    uint32_t half_ties; /* V=bit0,I=bit1,T=bit2,interval=bit3. */
    uint32_t rails;     /* low V/I/T=bits0/1/2; high V/I/T=bits4/5/6. */
} hp_quantization_error;

/* Synthetic study fixture only. These are not hardware specifications and
 * do not model uncertain gain/offset, saturation or temperature dependence.
 * V map was selected from declared physical support before archive outcomes.
 */
extern const adc12_calibration hp_fixture_calibration;
extern const double hp_fixture_temperature_C;

/* Pure producer helpers shared with the finite independent qualification.
 * All pointer arguments must name complete disjoint objects. Failure leaves
 * outputs unchanged. No file, model, prior or estimator call occurs here.
 */
int hp_decode_record(const unsigned char bytes[HP_RECORD_BYTES],
                     hp_observation *observation);
int hp_encode(uint64_t expected_index, const hp_observation *observation,
              adc12_raw_sample *raw, hp_quantization_error *error);

/* Exactly nonnegative round-nearest with half ties toward the higher code.
 * Engineering values outside the calibrated span reject BEFORE rounding;
 * no clipping. Model input scope additionally requires0<=dt<=1 s and
 * |I|<=0.25 A. Time remains an explicitly quantized actual interval.
 * The archive supplies no T, so every record gets synthetic25 C/code1040.
 */

#endif
