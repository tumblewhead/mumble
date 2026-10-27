#include "adc12.h"

#include <limits.h>
#include <math.h>
#include <string.h>

#if CHAR_BIT != 8
#error "adc12 channel codec requires 8-bit bytes"
#endif

/* Bounded byte-pointer equality checks avoid relational comparisons or
 * integer-address assumptions for unrelated C objects. Callers still owe
 * correctly sized objects/buffers, as with any C object API. */
static int overlap(const void *a, size_t a_bytes,
                   const void *b, size_t b_bytes)
{
    const unsigned char *aa = (const unsigned char *)a;
    const unsigned char *bb = (const unsigned char *)b;
    size_t i;
    for (i = 0; i < a_bytes; ++i) {
        if (aa + i == bb) return 1;
    }
    for (i = 0; i < b_bytes; ++i) {
        if (bb + i == aa) return 1;
    }
    return 0;
}

static int codes_valid(const adc12_codes *codes)
{
    return codes->voltage <= ADC12_CODE_MAX &&
           codes->current <= ADC12_CODE_MAX &&
           codes->temperature <= ADC12_CODE_MAX;
}

static int state_valid(const adc12_stream *stream)
{
    return stream->head < ADC12_QUEUE_DEPTH &&
           stream->count <= ADC12_QUEUE_DEPTH &&
           stream->next_sequence >= (uint64_t)stream->count;
}

static void copy_sample(adc12_raw_sample *to, const adc12_raw_sample *from)
{
    to->interval_ticks = from->interval_ticks;
    to->codes.voltage = from->codes.voltage;
    to->codes.current = from->codes.current;
    to->codes.temperature = from->codes.temperature;
}

static adc12_status output_arguments(const adc12_stream *stream,
                                     const adc12_raw_sample *sample,
                                     const uint64_t *sequence)
{
    if (!stream || !sample || !sequence) return ADC12_INVALID_ARGUMENT;
    if (overlap(stream, sizeof(*stream), sample, sizeof(*sample)) ||
        overlap(stream, sizeof(*stream), sequence, sizeof(*sequence)) ||
        overlap(sample, sizeof(*sample), sequence, sizeof(*sequence)))
        return ADC12_ALIAS;
    if (!state_valid(stream)) return ADC12_INVALID_STATE;
    if (stream->count == 0u) return ADC12_QUEUE_EMPTY;
    if (!codes_valid(&stream->samples[stream->head].codes))
        return ADC12_CODE_RANGE;
    return ADC12_OK;
}

adc12_status adc12_stream_init(adc12_stream *stream,
                               const unsigned char source_id[ADC12_SOURCE_BYTES],
                               uint64_t next_sequence)
{
    if (!stream || !source_id) return ADC12_INVALID_ARGUMENT;
    if (overlap(stream, sizeof(*stream), source_id, ADC12_SOURCE_BYTES))
        return ADC12_ALIAS;
    memset(stream, 0, sizeof(*stream));
    memcpy(stream->source_id, source_id, ADC12_SOURCE_BYTES);
    stream->next_sequence = next_sequence;
    return ADC12_OK;
}

adc12_status adc12_stream_push(adc12_stream *stream,
                               const unsigned char source_id[ADC12_SOURCE_BYTES],
                               uint64_t sequence,
                               const adc12_raw_sample *sample)
{
    uint32_t tail;
    if (!stream || !source_id || !sample) return ADC12_INVALID_ARGUMENT;
    if (overlap(stream, sizeof(*stream), source_id, ADC12_SOURCE_BYTES) ||
        overlap(stream, sizeof(*stream), sample, sizeof(*sample)) ||
        overlap(source_id, ADC12_SOURCE_BYTES, sample, sizeof(*sample)))
        return ADC12_ALIAS;
    if (!state_valid(stream)) return ADC12_INVALID_STATE;
    if (memcmp(stream->source_id, source_id, ADC12_SOURCE_BYTES) != 0)
        return ADC12_SOURCE_MISMATCH;
    if (sequence != stream->next_sequence) return ADC12_SEQUENCE_MISMATCH;
    if (stream->count == ADC12_QUEUE_DEPTH) return ADC12_QUEUE_FULL;
    if (stream->next_sequence == UINT64_MAX) return ADC12_SEQUENCE_EXHAUSTED;
    if (!codes_valid(&sample->codes)) return ADC12_CODE_RANGE;
    tail = (stream->head + stream->count) % ADC12_QUEUE_DEPTH;
    copy_sample(&stream->samples[tail], sample);
    ++stream->count;
    ++stream->next_sequence;
    return ADC12_OK;
}

adc12_status adc12_stream_peek(const adc12_stream *stream,
                               adc12_raw_sample *sample, uint64_t *sequence)
{
    adc12_status status = output_arguments(stream, sample, sequence);
    if (status != ADC12_OK) return status;
    copy_sample(sample, &stream->samples[stream->head]);
    *sequence = stream->next_sequence - (uint64_t)stream->count;
    return ADC12_OK;
}

adc12_status adc12_stream_pop(adc12_stream *stream,
                              adc12_raw_sample *sample, uint64_t *sequence)
{
    adc12_status status = adc12_stream_peek(stream, sample, sequence);
    if (status != ADC12_OK) return status;
    stream->head = (stream->head + 1u) % ADC12_QUEUE_DEPTH;
    --stream->count;
    return ADC12_OK;
}

static int affine_valid(const adc12_affine *affine)
{
    return isfinite(affine->offset) && isfinite(affine->units_per_code);
}

adc12_status adc12_convert(const adc12_raw_sample *sample,
                           const adc12_calibration *calibration,
                           adc12_reading *reading)
{
    double dt, voltage, current, temperature;
    if (!sample || !calibration || !reading) return ADC12_INVALID_ARGUMENT;
    if (overlap(sample, sizeof(*sample), calibration, sizeof(*calibration)) ||
        overlap(sample, sizeof(*sample), reading, sizeof(*reading)) ||
        overlap(calibration, sizeof(*calibration), reading, sizeof(*reading)))
        return ADC12_ALIAS;
    if (!codes_valid(&sample->codes)) return ADC12_CODE_RANGE;
    if (!affine_valid(&calibration->voltage_V) ||
        !affine_valid(&calibration->current_A) ||
        !affine_valid(&calibration->temperature_C) ||
        !isfinite(calibration->seconds_per_tick) ||
        calibration->seconds_per_tick <= 0.0)
        return ADC12_INVALID_CALIBRATION;
    dt = (double)sample->interval_ticks * calibration->seconds_per_tick;
    voltage = calibration->voltage_V.offset +
              (double)sample->codes.voltage * calibration->voltage_V.units_per_code;
    current = calibration->current_A.offset +
              (double)sample->codes.current * calibration->current_A.units_per_code;
    temperature = calibration->temperature_C.offset +
                  (double)sample->codes.temperature * calibration->temperature_C.units_per_code;
    if (!isfinite(dt) || !isfinite(voltage) || !isfinite(current) ||
        !isfinite(temperature)) return ADC12_NONFINITE_RESULT;
    reading->dt_s = dt;
    reading->voltage_V = voltage;
    reading->current_A = current;
    reading->temperature_C = temperature;
    return ADC12_OK;
}

adc12_status adc12_stream_take(adc12_stream *stream,
                               const adc12_calibration *calibration,
                               adc12_raw_sample *sample, uint64_t *sequence,
                               adc12_reading *reading)
{
    adc12_status status;
    if (!calibration || !reading) return ADC12_INVALID_ARGUMENT;
    status = output_arguments(stream, sample, sequence);
    if (status != ADC12_OK) return status;
    if (overlap(stream, sizeof(*stream), calibration, sizeof(*calibration)) ||
        overlap(stream, sizeof(*stream), reading, sizeof(*reading)) ||
        overlap(sample, sizeof(*sample), calibration, sizeof(*calibration)) ||
        overlap(sample, sizeof(*sample), reading, sizeof(*reading)) ||
        overlap(sequence, sizeof(*sequence), calibration, sizeof(*calibration)) ||
        overlap(sequence, sizeof(*sequence), reading, sizeof(*reading)) ||
        overlap(calibration, sizeof(*calibration), reading, sizeof(*reading)))
        return ADC12_ALIAS;
    status = adc12_convert(&stream->samples[stream->head], calibration, reading);
    if (status != ADC12_OK) return status;
    copy_sample(sample, &stream->samples[stream->head]);
    *sequence = stream->next_sequence - (uint64_t)stream->count;
    stream->head = (stream->head + 1u) % ADC12_QUEUE_DEPTH;
    --stream->count;
    return ADC12_OK;
}

adc12_status adc12_pack(const adc12_codes *codes,
                        unsigned char *packed, size_t packed_bytes)
{
    if (!codes || !packed) return ADC12_INVALID_ARGUMENT;
    if (packed_bytes != ADC12_PACKED_BYTES) return ADC12_INVALID_LENGTH;
    if (overlap(codes, sizeof(*codes), packed, ADC12_PACKED_BYTES))
        return ADC12_ALIAS;
    if (!codes_valid(codes)) return ADC12_CODE_RANGE;
    packed[0] = (unsigned char)(codes->voltage & 255u);
    packed[1] = (unsigned char)((codes->voltage >> 8) |
                               ((codes->current & 15u) << 4));
    packed[2] = (unsigned char)(codes->current >> 4);
    packed[3] = (unsigned char)(codes->temperature & 255u);
    packed[4] = (unsigned char)(codes->temperature >> 8);
    return ADC12_OK;
}

adc12_status adc12_unpack(const unsigned char *packed, size_t packed_bytes,
                          adc12_codes *codes)
{
    if (!codes || !packed) return ADC12_INVALID_ARGUMENT;
    if (packed_bytes != ADC12_PACKED_BYTES) return ADC12_INVALID_LENGTH;
    if (overlap(codes, sizeof(*codes), packed, ADC12_PACKED_BYTES))
        return ADC12_ALIAS;
    if ((packed[4] & 240u) != 0u) return ADC12_NONCANONICAL_PADDING;
    codes->voltage = (uint16_t)((uint16_t)packed[0] |
                              ((uint16_t)(packed[1] & 15u) << 8));
    codes->current = (uint16_t)((uint16_t)(packed[1] >> 4) |
                              ((uint16_t)packed[2] << 4));
    codes->temperature = (uint16_t)((uint16_t)packed[3] |
                                  ((uint16_t)packed[4] << 8));
    return ADC12_OK;
}
