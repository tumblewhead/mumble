/* IEEE binary64 subtraction via sign-bit flip and the same addition runtime.
   Finite supported inputs preserve arithmetic; NaN payload identity not promised.
   --wrap prevents pulling libgcc's separate duplicate subtraction implementation. */
#include <stdint.h>
#include <string.h>
__attribute__((used,externally_visible)) double __wrap___aeabi_dsub(double a,double b){uint64_t u;memcpy(&u,&b,8);u^=UINT64_C(0x8000000000000000);memcpy(&b,&u,8);return a+b;}
