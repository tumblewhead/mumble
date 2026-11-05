#include <stdint.h>
#include <string.h>
__attribute__((used,externally_visible)) float __wrap___aeabi_fsub(float a,float b){uint32_t u;memcpy(&u,&b,4);u^=UINT32_C(0x80000000);memcpy(&b,&u,4);return a+b;}
