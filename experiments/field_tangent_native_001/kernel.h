#ifndef FIELD_TANGENT_NATIVE_H
#define FIELD_TANGENT_NATIVE_H
#include <stdint.h>
#include <stddef.h>
/* RC degree5. Hysteresis degree is a build-time ABI choice. */
#ifndef FT_HDEG
#define FT_HDEG 5
#endif
#if FT_HDEG != 5 && FT_HDEG != 7
#error "supported hysteresis degrees: 5 and 7"
#endif
#define FT_M (FT_HDEG+1)
#define FT_B (FT_M*(FT_M+1)/2)
#define FT_WIDTH (40+2*FT_B)
#define FT_STATE (39+2*FT_M*FT_M)
typedef struct {
    double factor[153],anchor[16];
    uint64_t source,count,magic;
} FTContext;
typedef struct { double T[5][FT_M],D[5][FT_M],p[11],gaps[3],h,dh; } FTBasis;
typedef struct {
    FTBasis basis;
    double row[FT_WIDTH],gx[16],bw[17],delta[16],x[16];
    union { double trial[153]; struct { double inverse[256],origin[256]; } query; } phase;
} FTWork;
/* Caller-owned fused window scratch. No16x82 response matrix is retained.
 * query_status is separate: a committed update may require domain recovery. */
typedef struct {
    double state[FT_STATE],out[307];
    uint64_t ticks;
    int query_status;
} FTStepWork;
int ft_width(void);
int ft_state_count(void);
int ft_hysteresis_degree(void);
size_t ft_context_bytes(void);
size_t ft_work_bytes(void);
size_t ft_step_work_bytes(void);
int ft_info(const FTContext *,uint64_t *,uint64_t *);
int ft_init(FTContext *,FTWork *,uint64_t,uint64_t,const double *,const double *,const double *,const double *,const double *,const double *);
int ft_update(FTContext *,FTWork *,uint64_t,uint64_t,const double *,size_t,const double *,const double *,const double *,const double *);
/* output = w16, initial_chart16, endpoint16, endpoint_root256, cost/logdet/displacement3. */
int ft_query(const FTContext *,FTWork *,uint64_t,const double *,const double *,const double *,const double *,const double *,const double *,const double *,double *);
int ft_projection(FTWork *,const double *,const double *,const double *,const double *,double *);
int ft_step(FTContext *,FTWork *,FTStepWork *,uint64_t,uint64_t,
            const double *,size_t,uint64_t,int,const double *,const double *,
            const double *,const double *,const double *,const double *,
            const double *,const double *,double *);
#endif
