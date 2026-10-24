#ifndef SCM_FEATURES_H
#define SCM_FEATURES_H
/* Reconstructed research projection module; no byte-identity claim to the
 * lost version. Basis storage is explicit and separately counted from payload.
 * Inputs must be whitened for general covariance; common scalar iid variance
 * needs only the caller's common likelihood scaling. Physical states, source
 * identities, chronology and covariance remain the caller's responsibility. */
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
enum {
    SCM_FEATURES_ERR_ARGUMENT=-1,
    SCM_FEATURES_ERR_ALLOCATION=-2,
    SCM_FEATURES_ERR_CAPACITY=-3,
    SCM_FEATURES_ERR_NONFINITE=-4
};
typedef struct {
    size_t n, rank, capacity;
    double *q;                 /* q[column*n+row] */
    double *work;
    double relative_tolerance, absolute_tolerance;
    size_t columns_seen, columns_rejected;
    double max_discarded_norm, max_discarded_relative_norm;
    size_t allocated_bytes;     /* struct + q allocation + scratch */
} scm_feature_basis;
/* Initialize a new/freed object. Both tolerances are finite and nonnegative.
 * Retain a column iff twice-orthogonalized norm > max(atol,rtol*original norm).
 * max_rank is capped at n. Errors leave a zero object safe to free. */
int scm_features_init(scm_feature_basis*,size_t,size_t,double,double);
void scm_features_reset(scm_feature_basis*);
void scm_features_free(scm_feature_basis*);
/* 1 added, 0 numerically dependent, negative error. Capacity never truncates
 * silently. An add error leaves all previously accepted basis columns valid. */
int scm_features_add(scm_feature_basis*,const double*,size_t stride);
/* Row-major n*ncolumns; row_stride>=ncolumns. 0 success. Failure resets rank. */
int scm_features_build(scm_feature_basis*,const double*,size_t ncolumns,size_t row_stride);
/* Nonoverlapping caller arrays. z holds rank doubles; x may be a centered
 * residual. A model reference is permitted; known-truth OCV subtraction is not
 * part of this module. rank=0 permits z=NULL. */
void scm_features_project(const scm_feature_basis*,const double*,size_t stride,double*);
/* Output is row-major rank*ncolumns. */
void scm_features_project_matrix(const scm_feature_basis*,const double*,size_t ncolumns,size_t row_stride,double*);
void scm_features_expand(const scm_feature_basis*,const double*,double*);
size_t scm_features_payload_bytes(const scm_feature_basis*);
double scm_features_orthogonality_error(const scm_feature_basis*);
#ifdef __cplusplus
}
#endif
#endif
