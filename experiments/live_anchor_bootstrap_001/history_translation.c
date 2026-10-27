#include "history_translation.h"
#include <float.h>
#include <math.h>
#include <stdint.h>

typedef char ht_binary64[(sizeof(double)==8 && DBL_MANT_DIG==53 &&
                         DBL_MAX_EXP==1024) ? 1 : -1];

const unsigned char ht_pair[HT_PAIRS][2] = {
    {0,0},{0,7},{0,12}, {1,1},{1,8},{1,13}, {2,2},{2,9},{2,14},
    {3,3},{3,4},{4,4}, {3,10},{3,15},{4,10},{4,15}, {10,15},
    {11,11},{5,11},{5,5}
};

typedef struct { double value, correction; } ht_sum;

size_t ht_index(unsigned row, unsigned column)
{
    return (size_t)row*HT_FEATURES-(size_t)row*(row-1u)/2u+column-row;
}

static int disjoint(const void *a, size_t an, const void *b, size_t bn)
{
    uintptr_t ap=(uintptr_t)a,bp=(uintptr_t)b;
    if(ap>UINTPTR_MAX-an || bp>UINTPTR_MAX-bn)return 0;
    return ap+an<=bp || bp+bn<=ap;
}

static int add(ht_sum *s, double x)
{
    double n;
    if(!isfinite(x))return HT_NONFINITE;
    n=s->value+x;
    if(!isfinite(n))return HT_NONFINITE;
    s->correction+=fabs(s->value)>=fabs(x) ?
        (s->value-n)+x : (x-n)+s->value;
    s->value=n;
    return isfinite(s->correction) && isfinite(n+s->correction) ? HT_OK : HT_NONFINITE;
}

static int constant_value(const double *r, const double *s,
                          unsigned row, double *value)
{
    ht_sum sum={0.,0.};
    unsigned col;
    if(add(&sum,r[ht_index(row,36u)]))return HT_NONFINITE;
    for(col=row>20u?row:20u;col<36u;col++)
        if(add(&sum,r[ht_index(row,col)]*s[col-20u]))return HT_NONFINITE;
    for(col=row;col<20u;col++) {
        unsigned a=ht_pair[col][0],b=ht_pair[col][1];
        if(add(&sum,(r[ht_index(row,col)]*s[a])*s[b]))return HT_NONFINITE;
    }
    *value=sum.value+sum.correction;
    return HT_OK;
}

static int linear_value(const double *r, const double *s,
                        unsigned row, unsigned coordinate, double *value)
{
    ht_sum sum={0.,0.};
    unsigned col;
    if(add(&sum,r[ht_index(row,20u+coordinate)]))return HT_NONFINITE;
    for(col=row;col<20u;col++) {
        unsigned a=ht_pair[col][0],b=ht_pair[col][1];
        double coefficient=r[ht_index(row,col)];
        if(a==coordinate && add(&sum,coefficient*s[b]))return HT_NONFINITE;
        if(b==coordinate && add(&sum,coefficient*s[a]))return HT_NONFINITE;
    }
    *value=sum.value+sum.correction;
    return HT_OK;
}

static int pass(double *r, const double *s, int mutate)
{
    unsigned row,col;
    double value;
    for(row=0;row<HT_FEATURES;row++) {
        /* Constant first: it needs the OLD linear coefficients. */
        if(constant_value(r,s,row,&value))return HT_NONFINITE;
        if(mutate)r[ht_index(row,36u)]=value;
        for(col=row>20u?row:20u;col<36u;col++) {
            if(linear_value(r,s,row,col-20u,&value))return HT_NONFINITE;
            if(mutate)r[ht_index(row,col)]=value;
        }
    }
    return HT_OK;
}

int ht_translate(double upper[HT_PACKED], const double shift[HT_DIM])
{
    unsigned i;
    if(!upper || !shift)return HT_ARGUMENT;
    if(!disjoint(upper,HT_PACKED*sizeof(double),shift,HT_DIM*sizeof(double)))
        return HT_ALIAS;
    for(i=0;i<HT_PACKED;i++)if(!isfinite(upper[i]))return HT_NONFINITE;
    for(i=0;i<HT_DIM;i++)if(!isfinite(shift[i]))return HT_NONFINITE;
    if(pass(upper,shift,0))return HT_NONFINITE;
    return pass(upper,shift,1) ? HT_MUTATION_FAULT : HT_OK;
}
