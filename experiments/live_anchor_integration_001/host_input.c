#include "host_input.h"

#include <float.h>
#include <limits.h>
#include <math.h>
#include <string.h>

typedef char hp_binary64[(CHAR_BIT==8 && sizeof(double)==8 &&
                         DBL_MANT_DIG==53 && DBL_MAX_EXP==1024) ? 1 : -1];

const adc12_calibration hp_fixture_calibration = {
    {1.5, 1.0/1024.0}, {-0.256, 0.000125}, {-40.0, 0.0625},
    1.0/7000000.0
};
const double hp_fixture_temperature_C = 25.0;

static int overlaps(const void *a,size_t na,const void *b,size_t nb)
{
    const unsigned char *aa=(const unsigned char *)a,*bb=(const unsigned char *)b;
    size_t i;
    for(i=0;i<na;i++)if(aa+i==bb)return 1;
    for(i=0;i<nb;i++)if(bb+i==aa)return 1;
    return 0;
}

static uint64_t little_u64(const unsigned char *p)
{
    uint64_t n=0;unsigned i;
    for(i=0;i<8u;i++)n|=(uint64_t)p[i]<<(8u*i);
    return n;
}

static double little_double(const unsigned char *p)
{
    uint64_t bits=little_u64(p);double value;
    memcpy(&value,&bits,sizeof(value));return value;
}

int hp_decode_record(const unsigned char bytes[HP_RECORD_BYTES],
                     hp_observation *observation)
{
    hp_observation value;
    if(!bytes || !observation)return HP_ERR_ARGUMENT;
    if(overlaps(bytes,HP_RECORD_BYTES,observation,sizeof(*observation)))return HP_ERR_ALIAS;
    value.index=little_u64(bytes);
    value.dt_s=little_double(bytes+8);
    value.current_A=little_double(bytes+16);
    value.voltage_V=little_double(bytes+24);
    if(!isfinite(value.dt_s) || !isfinite(value.current_A) || !isfinite(value.voltage_V))
        return HP_ERR_NONFINITE;
    *observation=value;return HP_OK;
}

static int channel(double value,const adc12_affine *cal,unsigned channel_index,
                   uint16_t *code,uint32_t *ties,uint32_t *rails)
{
    double q,r,high=cal->offset+4095.0*cal->units_per_code;
    if(!isfinite(value))return HP_ERR_NONFINITE;
    if(value<cal->offset || value>high)return HP_ERR_SPAN;
    q=(value-cal->offset)/cal->units_per_code;
    if(!isfinite(q))return HP_ERR_NONFINITE;
    r=floor(q+0.5);
    if(r<0.0 || r>4095.0)return HP_ERR_CONVERSION;
    if(q-floor(q)==0.5)*ties|=UINT32_C(1)<<channel_index;
    *code=(uint16_t)r;
    if(*code==0u)*rails|=UINT32_C(1)<<channel_index;
    if(*code==4095u)*rails|=UINT32_C(1)<<(channel_index+4u);
    return HP_OK;
}

int hp_encode(uint64_t expected_index,const hp_observation *observation,
              adc12_raw_sample *raw,hp_quantization_error *error)
{
    adc12_raw_sample encoded;
    hp_quantization_error measured;
    adc12_reading decoded;
    double q,r;
    int status;
    if(!observation || !raw || !error)return HP_ERR_ARGUMENT;
    if(overlaps(observation,sizeof(*observation),raw,sizeof(*raw)) ||
       overlaps(observation,sizeof(*observation),error,sizeof(*error)) ||
       overlaps(raw,sizeof(*raw),error,sizeof(*error)))return HP_ERR_ALIAS;
    if(observation->index!=expected_index)return HP_ERR_ORDER;
    if(!isfinite(observation->dt_s) || !isfinite(observation->current_A) ||
       !isfinite(observation->voltage_V))return HP_ERR_NONFINITE;
    if(observation->dt_s<0.0 || observation->dt_s>1.0 ||
       fabs(observation->current_A)>0.25)return HP_ERR_DOMAIN;
    memset(&encoded,0,sizeof(encoded));memset(&measured,0,sizeof(measured));
    status=channel(observation->voltage_V,&hp_fixture_calibration.voltage_V,0,
                   &encoded.codes.voltage,&measured.half_ties,&measured.rails);
    if(status)return status;
    status=channel(observation->current_A,&hp_fixture_calibration.current_A,1,
                   &encoded.codes.current,&measured.half_ties,&measured.rails);
    if(status)return status;
    status=channel(hp_fixture_temperature_C,&hp_fixture_calibration.temperature_C,2,
                   &encoded.codes.temperature,&measured.half_ties,&measured.rails);
    if(status)return status;
    q=observation->dt_s/hp_fixture_calibration.seconds_per_tick;
    r=floor(q+0.5);
    /* The explicit<=1 s input guard bounds this conversion to7,000,000. */
    if(!isfinite(r) || r<0.0 || r>7000000.0)return HP_ERR_CONVERSION;
    if(q-floor(q)==0.5)measured.half_ties|=UINT32_C(8);
    encoded.interval_ticks=(uint64_t)r;
    status=adc12_convert(&encoded,&hp_fixture_calibration,&decoded);
    if(status!=ADC12_OK || decoded.dt_s<0.0 || decoded.dt_s>1.0 ||
       fabs(decoded.current_A)>0.25 || decoded.temperature_C!=25.0)
        return HP_ERR_CONVERSION;
    measured.dt_s=decoded.dt_s-observation->dt_s;
    measured.current_A=decoded.current_A-observation->current_A;
    measured.voltage_V=decoded.voltage_V-observation->voltage_V;
    if(!isfinite(measured.dt_s) || !isfinite(measured.current_A) ||
       !isfinite(measured.voltage_V))return HP_ERR_NONFINITE;
    raw->interval_ticks=encoded.interval_ticks;
    raw->codes.voltage=encoded.codes.voltage;
    raw->codes.current=encoded.codes.current;
    raw->codes.temperature=encoded.codes.temperature;
    *error=measured;
    return HP_OK;
}
