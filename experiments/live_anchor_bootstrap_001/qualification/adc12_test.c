#include "../adc12.h"

#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned int checks;
static unsigned int failures;
static unsigned int current_case;
static unsigned int case_checks[8];
static unsigned int case_failures[8];
static const char *const case_names[8] = {
    "codec_roundtrip_and_rails", "codec_rejection_atomicity",
    "explicit_calibration", "calibration_rejection_atomicity",
    "source_order_range_atomicity", "fifo_capacity_wrap_and_sequence",
    "atomic_calibrated_take", "alias_state_and_counter_guards"
};

#define CHECK(expression) do { \
    ++checks; ++case_checks[current_case]; \
    if (!(expression)) { \
        ++failures; ++case_failures[current_case]; \
        fprintf(stderr, "%s:%d: %s\n", case_names[current_case], __LINE__, #expression); \
    } \
} while (0)

static int same_codes(const adc12_codes *a, const adc12_codes *b)
{
    return a->voltage == b->voltage && a->current == b->current &&
           a->temperature == b->temperature;
}

static int same_raw(const adc12_raw_sample *a, const adc12_raw_sample *b)
{
    return a->interval_ticks == b->interval_ticks && same_codes(&a->codes, &b->codes);
}

static adc12_raw_sample raw_at(unsigned int i)
{
    adc12_raw_sample raw;
    memset(&raw, 0, sizeof(raw));
    raw.interval_ticks = UINT64_C(100) + (uint64_t)i;
    raw.codes.voltage = (uint16_t)i;
    raw.codes.current = (uint16_t)(100u + i);
    raw.codes.temperature = (uint16_t)(200u + i);
    return raw;
}

static adc12_calibration fixture_calibration(void)
{
    adc12_calibration c;
    c.voltage_V.offset = 1.0;
    c.voltage_V.units_per_code = 0.5;
    c.current_A.offset = -2.0;
    c.current_A.units_per_code = -0.25;
    c.temperature_C.offset = 10.0;
    c.temperature_C.units_per_code = 2.0;
    c.seconds_per_tick = 0.125;
    return c;
}

static void source_fixture(unsigned char source[ADC12_SOURCE_BYTES])
{
    unsigned int i;
    for (i = 0; i < ADC12_SOURCE_BYTES; ++i) source[i] = (unsigned char)(3u * i + 1u);
}

static void codec_roundtrip(void)
{
    unsigned int k, byte;
    for (k = 0; k < 40u; ++k) {
        adc12_codes codes = {0, 0, 0}, decoded = {99, 99, 99};
        unsigned char packed[ADC12_PACKED_BYTES];
        uint64_t word;
        if (k < 12u) codes.voltage = (uint16_t)(1u << k);
        else if (k < 24u) codes.current = (uint16_t)(1u << (k - 12u));
        else if (k < 36u) codes.temperature = (uint16_t)(1u << (k - 24u));
        else if (k == 37u) codes.voltage = codes.current = codes.temperature = 4095;
        else if (k == 38u) {
            codes.voltage = 0x123; codes.current = 0x456; codes.temperature = 0x789;
        } else if (k == 39u) {
            codes.voltage = 0xaaa; codes.current = 0x555; codes.temperature = 0xa5a;
        }
        word = (uint64_t)codes.voltage + ((uint64_t)codes.current << 12) +
               ((uint64_t)codes.temperature << 24);
        memset(packed, 0xa5, sizeof(packed));
        CHECK(adc12_pack(&codes, packed, sizeof(packed)) == ADC12_OK);
        for (byte = 0; byte < ADC12_PACKED_BYTES; ++byte)
            CHECK(packed[byte] == (unsigned char)((word >> (8u * byte)) & UINT64_C(255)));
        CHECK((packed[4] & 0xf0u) == 0u);
        CHECK(adc12_unpack(packed, sizeof(packed), &decoded) == ADC12_OK);
        CHECK(same_codes(&codes, &decoded));
    }
}

static void codec_rejection(void)
{
    adc12_codes codes = {1, 2, 3}, decoded = {4, 5, 6}, before_codes;
    unsigned char packed[8], before[8];
    unsigned int channel, value, bit;
    size_t length;
    union { adc12_codes codes; unsigned char bytes[16]; } aliased, before_alias;
    memset(packed, 0xa5, sizeof(packed));
    memcpy(before, packed, sizeof(before));
    for (channel = 0; channel < 3u; ++channel) {
        for (value = 0; value < 2u; ++value) {
            uint16_t invalid = value == 0u ? 4096 : UINT16_MAX;
            codes.voltage = 1; codes.current = 2; codes.temperature = 3;
            if (channel == 0u) codes.voltage = invalid;
            else if (channel == 1u) codes.current = invalid;
            else codes.temperature = invalid;
            CHECK(adc12_pack(&codes, packed, ADC12_PACKED_BYTES) == ADC12_CODE_RANGE);
            CHECK(memcmp(packed, before, sizeof(packed)) == 0);
        }
    }
    codes.voltage = 1; codes.current = 2; codes.temperature = 3;
    for (length = 0; length <= 6u; ++length) {
        if (length == ADC12_PACKED_BYTES) continue;
        before_codes = decoded;
        CHECK(adc12_pack(&codes, packed, length) == ADC12_INVALID_LENGTH);
        CHECK(adc12_unpack(packed, length, &decoded) == ADC12_INVALID_LENGTH);
        CHECK(memcmp(packed, before, sizeof(packed)) == 0);
        CHECK(same_codes(&decoded, &before_codes));
    }
    memset(packed, 0, sizeof(packed));
    for (bit = 4; bit < 8u; ++bit) {
        packed[4] = (unsigned char)(1u << bit);
        before_codes = decoded;
        CHECK(adc12_unpack(packed, ADC12_PACKED_BYTES, &decoded) == ADC12_NONCANONICAL_PADDING);
        CHECK(same_codes(&decoded, &before_codes));
    }
    CHECK(adc12_pack(NULL, packed, ADC12_PACKED_BYTES) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_pack(&codes, NULL, ADC12_PACKED_BYTES) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_unpack(NULL, ADC12_PACKED_BYTES, &decoded) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_unpack(packed, ADC12_PACKED_BYTES, NULL) == ADC12_INVALID_ARGUMENT);
    memset(&aliased, 0x35, sizeof(aliased));
    memcpy(&before_alias, &aliased, sizeof(aliased));
    CHECK(adc12_pack(&aliased.codes, aliased.bytes + 1, ADC12_PACKED_BYTES) == ADC12_ALIAS);
    CHECK(memcmp(&aliased, &before_alias, sizeof(aliased)) == 0);
    CHECK(adc12_unpack(aliased.bytes + 1, ADC12_PACKED_BYTES, &aliased.codes) == ADC12_ALIAS);
    CHECK(memcmp(&aliased, &before_alias, sizeof(aliased)) == 0);
}

static void explicit_calibration(void)
{
    adc12_raw_sample raw = {UINT64_C(5), {3, 7, 11}}, before;
    adc12_calibration cal = fixture_calibration();
    adc12_reading reading;
    before = raw;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_OK);
    CHECK(reading.dt_s == 0.625);
    CHECK(reading.voltage_V == 2.5);
    CHECK(reading.current_A == -3.75);
    CHECK(reading.temperature_C == 32.0);
    CHECK(same_raw(&raw, &before));
    raw.interval_ticks = 0;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_OK);
    CHECK(reading.dt_s == 0.0);
    raw.interval_ticks = UINT64_C(9007199254740994);
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_OK);
    CHECK(reading.dt_s == 1125899906842624.25);
    CHECK(raw.interval_ticks == UINT64_C(9007199254740994));
    raw.codes.voltage = 0; raw.codes.current = 4095; raw.codes.temperature = 4095;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_OK);
    CHECK(reading.voltage_V == 1.0);
    CHECK(reading.current_A == -1025.75);
    CHECK(reading.temperature_C == 8200.0);
    CHECK(raw.codes.voltage == 0 && raw.codes.current == 4095 && raw.codes.temperature == 4095);
    cal.voltage_V.units_per_code = 0.0;
    cal.current_A.units_per_code = 0.0;
    cal.temperature_C.units_per_code = -0.5;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_OK);
    CHECK(reading.voltage_V == 1.0 && reading.current_A == -2.0);
    CHECK(reading.temperature_C == -2037.5);
}

static void calibration_rejection(void)
{
    adc12_raw_sample raw = {UINT64_C(5), {3, 7, 11}}, before_raw;
    adc12_calibration cal = fixture_calibration();
    double *coefficients[7] = {
        &cal.voltage_V.offset, &cal.voltage_V.units_per_code,
        &cal.current_A.offset, &cal.current_A.units_per_code,
        &cal.temperature_C.offset, &cal.temperature_C.units_per_code,
        &cal.seconds_per_tick
    };
    adc12_reading reading, before_reading;
    unsigned int i, kind;
    union { adc12_raw_sample raw; adc12_calibration cal; adc12_reading reading; } alias, before_alias;
    memset(&reading, 0xa5, sizeof(reading));
    memcpy(&before_reading, &reading, sizeof(reading));
    before_raw = raw;
    for (i = 0; i < 7u; ++i) {
        for (kind = 0; kind < 2u; ++kind) {
            cal = fixture_calibration();
            *coefficients[i] = kind == 0u ? NAN : INFINITY;
            CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_INVALID_CALIBRATION);
            CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
            CHECK(same_raw(&raw, &before_raw));
        }
    }
    cal = fixture_calibration(); cal.seconds_per_tick = 0.0;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_INVALID_CALIBRATION);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
    cal.seconds_per_tick = -0.125;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_INVALID_CALIBRATION);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
    for (i = 0; i < 4u; ++i) {
        cal = fixture_calibration();
        if (i == 0u) cal.voltage_V.units_per_code = DBL_MAX;
        else if (i == 1u) cal.current_A.units_per_code = -DBL_MAX;
        else if (i == 2u) cal.temperature_C.units_per_code = DBL_MAX;
        else cal.seconds_per_tick = DBL_MAX;
        CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_NONFINITE_RESULT);
        CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
    }
    cal = fixture_calibration();
    raw.codes.voltage = 1;
    cal.voltage_V.offset = DBL_MAX; cal.voltage_V.units_per_code = DBL_MAX;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_NONFINITE_RESULT);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
    cal = fixture_calibration(); raw.codes.voltage = 4096;
    CHECK(adc12_convert(&raw, &cal, &reading) == ADC12_CODE_RANGE);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
    CHECK(adc12_convert(NULL, &cal, &reading) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_convert(&raw, NULL, &reading) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_convert(&raw, &cal, NULL) == ADC12_INVALID_ARGUMENT);
    memset(&alias, 0x3c, sizeof(alias)); memcpy(&before_alias, &alias, sizeof(alias));
    CHECK(adc12_convert(&alias.raw, &cal, &alias.reading) == ADC12_ALIAS);
    CHECK(memcmp(&alias, &before_alias, sizeof(alias)) == 0);
    CHECK(adc12_convert(&raw, &alias.cal, &alias.reading) == ADC12_ALIAS);
    CHECK(memcmp(&alias, &before_alias, sizeof(alias)) == 0);
    CHECK(adc12_convert(&alias.raw, &alias.cal, &reading) == ADC12_ALIAS);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0);
}

static void source_order_range(void)
{
    unsigned char source[ADC12_SOURCE_BYTES], wrong_source[ADC12_SOURCE_BYTES];
    adc12_stream stream, before;
    adc12_raw_sample raw = raw_at(1);
    source_fixture(source); memcpy(wrong_source, source, sizeof(source));
    wrong_source[31] ^= 1u;
    CHECK(adc12_stream_init(&stream, source, UINT64_C(100)) == ADC12_OK);
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, wrong_source, UINT64_C(100), &raw) == ADC12_SOURCE_MISMATCH);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_push(&stream, source, UINT64_C(99), &raw) == ADC12_SEQUENCE_MISMATCH);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_push(&stream, source, UINT64_C(101), &raw) == ADC12_SEQUENCE_MISMATCH);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    raw.codes.temperature = 4096;
    CHECK(adc12_stream_push(&stream, source, UINT64_C(100), &raw) == ADC12_CODE_RANGE);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    raw.codes.temperature = 201;
    CHECK(adc12_stream_push(&stream, source, UINT64_C(100), &raw) == ADC12_OK);
    CHECK(stream.count == 1u && stream.next_sequence == UINT64_C(101));
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, source, UINT64_C(100), &raw) == ADC12_SEQUENCE_MISMATCH);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    raw.interval_ticks = UINT64_MAX;
    CHECK(adc12_stream_push(&stream, source, UINT64_C(101), &raw) == ADC12_OK);
    CHECK(stream.samples[1].interval_ticks == UINT64_MAX);
}

static void fifo_wrap(void)
{
    unsigned char source[ADC12_SOURCE_BYTES];
    adc12_stream stream, before;
    adc12_raw_sample raw, got, expected, before_got;
    uint64_t sequence = 999, before_sequence;
    unsigned int i;
    source_fixture(source);
    CHECK(adc12_stream_init(&stream, source, UINT64_C(1000)) == ADC12_OK);
    for (i = 0; i < 16u; ++i) {
        raw = raw_at(i);
        CHECK(adc12_stream_push(&stream, source, UINT64_C(1000) + i, &raw) == ADC12_OK);
    }
    CHECK(stream.count == 16u && stream.next_sequence == UINT64_C(1016));
    memcpy(&before, &stream, sizeof(before)); raw = raw_at(16);
    CHECK(adc12_stream_push(&stream, source, UINT64_C(1016), &raw) == ADC12_QUEUE_FULL);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_peek(&stream, &got, &sequence) == ADC12_OK);
    expected = raw_at(0);
    CHECK(same_raw(&got, &expected) && sequence == UINT64_C(1000));
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    for (i = 0; i < 8u; ++i) {
        expected = raw_at(i);
        CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_OK);
        CHECK(same_raw(&got, &expected) && sequence == UINT64_C(1000) + i);
    }
    for (i = 16; i < 24u; ++i) {
        raw = raw_at(i);
        CHECK(adc12_stream_push(&stream, source, UINT64_C(1000) + i, &raw) == ADC12_OK);
    }
    for (i = 8; i < 24u; ++i) {
        expected = raw_at(i);
        CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_OK);
        CHECK(same_raw(&got, &expected) && sequence == UINT64_C(1000) + i);
    }
    CHECK(stream.count == 0u && stream.next_sequence == UINT64_C(1024) && stream.head == 8u);
    memcpy(&before, &stream, sizeof(before)); memcpy(&before_got, &got, sizeof(got));
    before_sequence = sequence;
    CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_QUEUE_EMPTY);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(memcmp(&got, &before_got, sizeof(got)) == 0 && sequence == before_sequence);
}

static void atomic_take(void)
{
    unsigned char source[ADC12_SOURCE_BYTES];
    adc12_stream stream, before;
    adc12_raw_sample raw = {UINT64_C(5), {3, 7, 11}}, got, before_got;
    adc12_calibration cal = fixture_calibration();
    adc12_reading reading, before_reading;
    uint64_t sequence = UINT64_C(12345);
    source_fixture(source);
    CHECK(adc12_stream_init(&stream, source, UINT64_C(7)) == ADC12_OK);
    CHECK(adc12_stream_push(&stream, source, UINT64_C(7), &raw) == ADC12_OK);
    memset(&got, 0x4a, sizeof(got)); memcpy(&before_got, &got, sizeof(got));
    memset(&reading, 0x5a, sizeof(reading)); memcpy(&before_reading, &reading, sizeof(reading));
    memcpy(&before, &stream, sizeof(before));
    cal.seconds_per_tick = 0.0;
    CHECK(adc12_stream_take(&stream, &cal, &got, &sequence, &reading) == ADC12_INVALID_CALIBRATION);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(memcmp(&got, &before_got, sizeof(got)) == 0);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0 && sequence == UINT64_C(12345));
    cal = fixture_calibration(); cal.temperature_C.units_per_code = DBL_MAX;
    CHECK(adc12_stream_take(&stream, &cal, &got, &sequence, &reading) == ADC12_NONFINITE_RESULT);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(memcmp(&got, &before_got, sizeof(got)) == 0);
    CHECK(memcmp(&reading, &before_reading, sizeof(reading)) == 0 && sequence == UINT64_C(12345));
    cal = fixture_calibration();
    CHECK(adc12_stream_take(&stream, &cal, &got, &sequence, &reading) == ADC12_OK);
    CHECK(same_raw(&got, &raw) && sequence == UINT64_C(7));
    CHECK(reading.dt_s == 0.625 && reading.voltage_V == 2.5 &&
          reading.current_A == -3.75 && reading.temperature_C == 32.0);
    CHECK(stream.count == 0u && stream.next_sequence == UINT64_C(8));
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_take(&stream, &cal, &got, &sequence, &reading) == ADC12_QUEUE_EMPTY);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
}

static void alias_state_counter(void)
{
    unsigned char source[ADC12_SOURCE_BYTES];
    adc12_stream stream, before;
    adc12_raw_sample raw = raw_at(1), got;
    adc12_calibration cal = fixture_calibration();
    adc12_reading reading;
    uint64_t sequence = 77;
    union { adc12_raw_sample raw; uint64_t sequence; adc12_reading reading; } output, before_output;
    source_fixture(source);
    CHECK(adc12_stream_init(&stream, source, UINT64_C(0)) == ADC12_OK);
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_init(&stream, stream.source_id, 0) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_push(&stream, stream.source_id, 0, &raw) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_push(&stream, source, 0, &stream.samples[0]) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_push(&stream, source, 0, &raw) == ADC12_OK);
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_pop(&stream, &stream.samples[0], &sequence) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_pop(&stream, &got, &stream.next_sequence) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    memset(&output, 0xa3, sizeof(output)); memcpy(&before_output, &output, sizeof(output));
    CHECK(adc12_stream_pop(&stream, &output.raw, &output.sequence) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(memcmp(&output, &before_output, sizeof(output)) == 0);
    CHECK(adc12_stream_take(&stream, &cal, &output.raw, &sequence, &output.reading) == ADC12_ALIAS);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(memcmp(&output, &before_output, sizeof(output)) == 0);
    CHECK(adc12_stream_init(NULL, source, 0) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_init(&stream, NULL, 0) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_push(NULL, source, 0, &raw) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_push(&stream, NULL, 1, &raw) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_push(&stream, source, 1, NULL) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_pop(NULL, &got, &sequence) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_pop(&stream, NULL, &sequence) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_pop(&stream, &got, NULL) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_take(&stream, NULL, &got, &sequence, &reading) == ADC12_INVALID_ARGUMENT);
    CHECK(adc12_stream_take(&stream, &cal, &got, &sequence, NULL) == ADC12_INVALID_ARGUMENT);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    stream.head = ADC12_QUEUE_DEPTH;
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, source, 1, &raw) == ADC12_INVALID_STATE);
    CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_INVALID_STATE);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    stream.head = 0; stream.count = ADC12_QUEUE_DEPTH + 1u;
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, source, 1, &raw) == ADC12_INVALID_STATE);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    stream.count = 2; stream.next_sequence = 1;
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_INVALID_STATE);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_init(&stream, source, UINT64_MAX - UINT64_C(1)) == ADC12_OK);
    CHECK(adc12_stream_push(&stream, source, UINT64_MAX - UINT64_C(1), &raw) == ADC12_OK);
    CHECK(stream.next_sequence == UINT64_MAX);
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, source, UINT64_MAX, &raw) == ADC12_SEQUENCE_EXHAUSTED);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
    CHECK(adc12_stream_pop(&stream, &got, &sequence) == ADC12_OK);
    CHECK(same_raw(&got, &raw) && sequence == UINT64_MAX - UINT64_C(1));
    memcpy(&before, &stream, sizeof(before));
    CHECK(adc12_stream_push(&stream, source, UINT64_MAX, &raw) == ADC12_SEQUENCE_EXHAUSTED);
    CHECK(memcmp(&stream, &before, sizeof(stream)) == 0);
}

int main(void)
{
    unsigned int i;
    current_case = 0; codec_roundtrip();
    current_case = 1; codec_rejection();
    current_case = 2; explicit_calibration();
    current_case = 3; calibration_rejection();
    current_case = 4; source_order_range();
    current_case = 5; fifo_wrap();
    current_case = 6; atomic_take();
    current_case = 7; alias_state_counter();
    printf("{\"schema\":\"mumble_adc12_fabricated_test_v1\",\"status\":\"%s\",", failures ? "failed" : "passed");
    printf("\"cases\":%u,\"assertions\":%u,\"failures\":%u,\"case_results\":[", 8u, checks, failures);
    for (i = 0; i < 8u; ++i) {
        printf("%s{\"name\":\"%s\",\"assertions\":%u,\"failures\":%u}",
               i ? "," : "", case_names[i], case_checks[i], case_failures[i]);
    }
    printf("],\"sizeof\":{\"codes\":%zu,\"raw_sample\":%zu,\"queue\":%zu,",
           sizeof(adc12_codes), sizeof(adc12_raw_sample), sizeof(adc12_stream));
    printf("\"queue_samples\":%zu,\"queue_metadata_and_padding\":%zu,\"calibration\":%zu,",
           sizeof(((adc12_stream *)0)->samples),
           sizeof(adc12_stream) - sizeof(((adc12_stream *)0)->samples), sizeof(adc12_calibration));
    printf("\"decoded_reading\":%zu,\"sequence_output\":%zu,\"optional_packed_channels\":%u},",
           sizeof(adc12_reading), sizeof(uint64_t), ADC12_PACKED_BYTES);
    printf("\"platform\":{\"char_bits\":%d,\"double_bytes\":%zu,\"double_mantissa_bits\":%d,",
           CHAR_BIT, sizeof(double), DBL_MANT_DIG);
    printf("\"compiler_version\":\"%s\"},", __VERSION__);
    printf("\"codec_vectors\":40,\"model_calls\":0,\"prior_calls\":0,\"optimizer_calls\":0,");
    printf("\"observation_reads\":0,\"truth_reads\":0,\"hardware_performance_claim\":false}\n");
    return failures ? 1 : 0;
}
