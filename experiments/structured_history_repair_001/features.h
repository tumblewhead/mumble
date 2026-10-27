#ifndef MUMBLE_STRUCTURED_FEATURES_H
#define MUMBLE_STRUCTURED_FEATURES_H
#include "../compact_nonlinear_history_001/compact_history.h"
#ifndef SH_ANALYTIC_ATTENUATION
#define SH_ANALYTIC_ATTENUATION 1
#endif
#if SH_ANALYTIC_ATTENUATION
#define SH_BANK_MAGIC "SHF0001"
#else
#define SH_BANK_MAGIC "SHC0001"
#endif
#define SH_INVERSE_Q_SD 5.7926168556214002
#define SH_U_SD (ch_public_sd[10]*ch_public_sd[15])
/* Full arm reclaims dda[0:2] for the two nonnegative charge integrals.
 * RC attenuation second derivatives are computed analytically on demand.
 * The control arm retains the inherited dda semantics. Both are new schemas. */
#define SH_POSITIVE_CHARGE(j) ((j)->dda[0])
#define SH_NEGATIVE_CHARGE(j) ((j)->dda[1])
size_t sh_index(unsigned row,unsigned column);
double sh_feature(const double *origin,const double *point,unsigned feature);
double sh_feature_derivative(const double *origin,const double *point,unsigned feature,unsigned coordinate);
int sh_shift(const double *old_origin,const double *point,double shift[7]);
int sh_translate(double upper[703],const double shift[7]);
#endif
