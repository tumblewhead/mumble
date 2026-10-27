#ifndef MUMBLE_LIVE_HISTORY_TRANSLATION_H
#define MUMBLE_LIVE_HISTORY_TRANSLATION_H

#include <stddef.h>

/* Translation of an ALREADY REPRESENTED polynomial, not historical replay.
 * Features are [20 quadratic monomials, 16 linear coordinates, constant].
 * Coordinates use the same immutable scale before and after translation.
 * This ordering is deliberately different from compact_history_001. An old
 * linear-first QR factor cannot be reinterpreted as this representation.
 */
#define HT_DIM 16u
#define HT_PAIRS 20u
#define HT_FEATURES 37u
#define HT_PACKED 703u

enum { HT_OK=0, HT_ARGUMENT=-1, HT_ALIAS=-2, HT_NONFINITE=-3,
       HT_MUTATION_FAULT=-4 };

extern const unsigned char ht_pair[HT_PAIRS][2];
size_t ht_index(unsigned row, unsigned column);

/* If d_old=d_new+shift, replace R by R*T so that
 *   ||R_old*phi(d_old)||^2 == ||R_new*phi(d_new)||^2
 * in real arithmetic. Quadratic-first ordering makes T upper triangular.
 * Both arrays must have the stated size, be disjoint and be externally
 * serialized. No heap, second factor, sample archive or prior is used.
 *
 * Every prospective value is checked in a read-only first pass. Argument,
 * alias and nonfinite errors leave every factor byte unchanged. An unexpected
 * numerical fault in the mutation pass returns HT_MUTATION_FAULT; an owning
 * estimator must latch itself unavailable because no rollback factor exists.
 * Source/order/evidence counters belong to that owner and are not touched.
 * Floating-point arithmetic must not use fast-math or concurrent mutation.
 */
int ht_translate(double upper[HT_PACKED], const double shift[HT_DIM]);

#endif
