#ifndef MUMBLE_LIVE_ADC12_H
#define MUMBLE_LIVE_ADC12_H

#include <stddef.h>
#include <stdint.h>

/* Transport/calibration only: no physical model, history, heap or file API.
 * Requires C99 exact uint16_t/uint32_t/uint64_t and 8-bit bytes. */
#define ADC12_CODE_MAX 4095u
#define ADC12_PACKED_BYTES 5u
#define ADC12_SOURCE_BYTES 32u
#define ADC12_QUEUE_DEPTH 16u

typedef enum {
    ADC12_OK = 0,
    ADC12_INVALID_ARGUMENT = -1,
    ADC12_INVALID_LENGTH = -2,
    ADC12_CODE_RANGE = -3,
    ADC12_NONCANONICAL_PADDING = -4,
    ADC12_ALIAS = -5,
    ADC12_SOURCE_MISMATCH = -6,
    ADC12_SEQUENCE_MISMATCH = -7,
    ADC12_QUEUE_FULL = -8,
    ADC12_QUEUE_EMPTY = -9,
    ADC12_SEQUENCE_EXHAUSTED = -10,
    ADC12_INVALID_STATE = -11,
    ADC12_INVALID_CALIBRATION = -12,
    ADC12_NONFINITE_RESULT = -13
} adc12_status;

typedef struct {
    uint16_t voltage;
    uint16_t current;
    uint16_t temperature;
} adc12_codes;

typedef struct {
    /* Actual duration of this sample interval, not an absolute timestamp.
     * Zero is retained; the future model adapter decides its own dt policy. */
    uint64_t interval_ticks;
    adc12_codes codes;
} adc12_raw_sample;

typedef struct {
    adc12_raw_sample samples[ADC12_QUEUE_DEPTH];
    unsigned char source_id[ADC12_SOURCE_BYTES];
    uint64_t next_sequence;
    uint32_t head;
    uint32_t count;
} adc12_stream;

typedef struct {
    double offset;
    double units_per_code;
} adc12_affine;

typedef struct {
    adc12_affine voltage_V;
    adc12_affine current_A;
    adc12_affine temperature_C;
    double seconds_per_tick;
} adc12_calibration;

typedef struct {
    double dt_s;
    double voltage_V;
    double current_A;
    double temperature_C;
} adc12_reading;

/* Every object/buffer argument must be correctly sized/aligned and disjoint
 * from every other argument. Overlap is rejected before any write. Rejected
 * operations leave all stream/output bytes unchanged. Queue calls require a
 * previously initialized stream and one caller or external serialization;
 * this is not a lock-free or interrupt-safe queue by itself. Struct padding
 * is never serialized and is not part of sample identity. */
adc12_status adc12_stream_init(adc12_stream *stream,
                               const unsigned char source_id[ADC12_SOURCE_BYTES],
                               uint64_t next_sequence);
adc12_status adc12_stream_push(adc12_stream *stream,
                               const unsigned char source_id[ADC12_SOURCE_BYTES],
                               uint64_t sequence,
                               const adc12_raw_sample *sample);
adc12_status adc12_stream_peek(const adc12_stream *stream,
                               adc12_raw_sample *sample, uint64_t *sequence);
adc12_status adc12_stream_pop(adc12_stream *stream,
                              adc12_raw_sample *sample, uint64_t *sequence);

/* The source is matched at push. Sequence is implicit in the FIFO and is
 * returned separately. UINT64_MAX is an exhausted next-sequence cursor;
 * sequence UINT64_MAX cannot be accepted because advancing it would wrap. */

/* Engineering values are caller-calibrated, not physical validity claims.
 * All coefficients must be finite; seconds_per_tick must be positive.
 * Finite zero/negative channel gains are allowed as explicit caller choices.
 * uint64-to-double/affine conversion follows C double rounding. Raw codes0
 * and4095 remain rail codes; their noise/censoring meaning is not decided.
 * Temperature is preserved/converted, with no temperature compensation.
 * ADC code width does not prescribe residual/statistic precision. */
adc12_status adc12_convert(const adc12_raw_sample *sample,
                           const adc12_calibration *calibration,
                           adc12_reading *reading);

/* Converts before consuming. A conversion failure leaves both the queued
 * input and all outputs unchanged. Success returns raw temperature/ticks
 * together with the four engineering values and consumes exactly one row. */
adc12_status adc12_stream_take(adc12_stream *stream,
                               const adc12_calibration *calibration,
                               adc12_raw_sample *sample, uint64_t *sequence,
                               adc12_reading *reading);

/* Channel-only canonical little-endian codec: V bits0..11, I bits12..23,
 * T bits24..35; bits36..39 must be zero. Both lengths must equal5. Actual
 * ticks/source/sequence need their own explicit transport; no9-byte full
 * sample format or narrowed timer is implied by this optional codec. */
adc12_status adc12_pack(const adc12_codes *codes,
                        unsigned char *packed, size_t packed_bytes);
adc12_status adc12_unpack(const unsigned char *packed, size_t packed_bytes,
                          adc12_codes *codes);

#endif
