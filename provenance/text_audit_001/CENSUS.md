# Linked text census

Source: `c2cb9fc`, Cortex-M23, procedural Horner math, 48-bit history storage. Arithmetic remains binary64.

These are disjoint DWARF leaf attributions in a byte-identical diagnostic build. They include nearby literal pools/padding; they are not marginal removable costs.

| Functional group | Attributed bytes | Share of .text |
|---|---:|---:|
| Binary64 arithmetic runtime | 4,772 | 27.9% |
| Model coefficients, support and endpoint transport | 4,008 | 23.4% |
| Joint refit and scalar uncertainty | 2,674 | 15.6% |
| Shared elementary math | 1,720 | 10.1% |
| Sample propagation | 1,450 | 8.5% |
| History and local QR storage/update | 1,128 | 6.6% |
| Memory runtime | 572 | 3.3% |
| Ownership and interface checks | 510 | 3.0% |
| Entry and integer runtime | 266 | 1.6% |
| **Total** | **17,100** | **100%** |

The compiler-helper physical union is 4,746 B, or 4,762 B with the project subtraction wrapper. This differs from DWARF attribution because padding and symbol boundaries differ. Do not add the two views.

## Individual functions

| Innermost source function | Attributed bytes | Group |
|---|---:|---|
| `transported` | 1,514 | Model coefficients, support and endpoint transport |
| `__aeabi_dadd` | 1,460 | Binary64 arithmetic runtime |
| `stream_row` | 1,450 | Sample propagation |
| `__aeabi_ddiv` | 1,312 | Binary64 arithmetic runtime |
| `__aeabi_dmul` | 1,072 | Binary64 arithmetic runtime |
| `feature` | 1,008 | Model coefficients, support and endpoint transport |
| `supported` | 740 | Model coefficients, support and endpoint transport |
| `qr_insert` | 516 | History and local QR storage/update |
| `br_rebuild` | 508 | Joint refit and scalar uncertainty |
| `history_insert` | 430 | History and local QR storage/update |
| `evaluate` | 428 | Joint refit and scalar uncertainty |
| `tm_log` | 420 | Shared elementary math |
| `fit` | 382 | Joint refit and scalar uncertainty |
| `br_variance` | 288 | Joint refit and scalar uncertainty |
| `tm_exp` | 264 | Shared elementary math |
| `memmove` | 264 | Memory runtime |
| `tm_hypot` | 248 | Shared elementary math |
| `cost_at` | 244 | Joint refit and scalar uncertainty |
| `bind` | 234 | Ownership and interface checks |
| `append` | 234 | Joint refit and scalar uncertainty |
| `spline` | 230 | Model coefficients, support and endpoint transport |
| `br_step` | 220 | Joint refit and scalar uncertainty |
| `tm_tanh` | 206 | Shared elementary math |
| `__gedf2` | 190 | Binary64 arithmetic runtime |
| `__ledf2` | 188 | Binary64 arithmetic runtime |
| `initialize` | 186 | Joint refit and scalar uncertainty |
| `reset` | 182 | Entry and integer runtime |
| `cardinal` | 178 | Model coefficients, support and endpoint transport |
| `memcpy` | 164 | Memory runtime |
| `memset` | 144 | Memory runtime |
| `tm_atanh` | 136 | Shared elementary math |
| `br_acquire` | 128 | Ownership and interface checks |
| `history_put` | 126 | History and local QR storage/update |
| `tm_sqrt` | 124 | Shared elementary math |
| `__eqdf2` | 118 | Binary64 arithmetic runtime |
| `cheb` | 114 | Model coefficients, support and endpoint transport |
| `sm_eval` | 112 | Shared elementary math |
| `estimate` | 112 | Joint refit and scalar uncertainty |
| `__aeabi_d2iz` | 96 | Binary64 arithmetic runtime |
| `__aeabi_i2d` | 78 | Binary64 arithmetic runtime |
| `chart` | 76 | Model coefficients, support and endpoint transport |
| `dcheb` | 76 | Model coefficients, support and endpoint transport |
| `emit` | 72 | Model coefficients, support and endpoint transport |
| `scalar` | 72 | Joint refit and scalar uncertainty |
| `tm_expm1_reduced` | 70 | Shared elementary math |
| `tm_scale` | 70 | Shared elementary math |
| `br_release` | 70 | Ownership and interface checks |
| `ingest` | 68 | Ownership and interface checks |
| `__aeabi_ui2d` | 62 | Binary64 arithmetic runtime |
| `__clzsi2` | 60 | Entry and integer runtime |
| `__aeabi_dcmpun` | 56 | Binary64 arithmetic runtime |
| `tm_expm1` | 50 | Shared elementary math |
| `history_get` | 40 | History and local QR storage/update |
| `__aeabi_dcmple` | 20 | Binary64 arithmetic runtime |
| `__aeabi_dcmpgt` | 20 | Binary64 arithmetic runtime |
| `__aeabi_dcmpge` | 20 | Binary64 arithmetic runtime |
| `__gnu_thumb1_case_uqi` | 20 | Entry and integer runtime |
| `__aeabi_cdrcmple` | 18 | Binary64 arithmetic runtime |
| `__aeabi_dcmplt` | 18 | Binary64 arithmetic runtime |
| `index_of` | 16 | History and local QR storage/update |
| `__wrap___aeabi_dsub` | 16 | Binary64 arithmetic runtime |
| `__aeabi_cdcmple` | 16 | Binary64 arithmetic runtime |
| `tm_value` | 12 | Shared elementary math |
| `__aeabi_dcmpeq` | 12 | Binary64 arithmetic runtime |
| `stream_ingest` | 10 | Ownership and interface checks |
| `tm_nextup` | 8 | Shared elementary math |
| `fault` | 4 | Entry and integer runtime |

## Physical symbols

`reset` occupies 3,856 B, but only 182 B is attributed to its own source body; most is inlined estimator work. Symbol size alone would misdirect the optimization.

| Symbol / same-extent aliases | Nominal extent bytes |
|---|---:|
| `reset` | 3,856 |
| `transported.constprop.0` | 1,828 |
| `__aeabi_dadd` | 1,460 |
| `feature.constprop.0` | 1,428 |
| `__aeabi_ddiv` | 1,312 |
| `__aeabi_dmul` | 1,072 |
| `evaluate.constprop.0` | 996 |
| `supported.constprop.0` | 740 |
| `qr_insert.constprop.0` | 516 |
| `tm_log` | 420 |
| `tm_hypot` | 372 |
| `tm_exp` | 356 |
| `br_step.constprop.0` | 296 |
| `memmove` | 262 |
| `cost_at.constprop.0` | 244 |
| `tm_tanh` | 232 |
| `__gedf2` / `__gtdf2` | 190 |
| `__ledf2` / `__ltdf2` | 188 |
| `memcpy` | 162 |
| `memset` | 142 |
| `__eqdf2` / `__nedf2` | 118 |
| `sm_eval` | 112 |
| `__aeabi_d2iz` | 96 |
| `__aeabi_i2d` | 78 |
| `emit` | 72 |
| `tm_expm1` | 72 |
| `__aeabi_ui2d` | 62 |
| `__clzsi2` | 60 |
| `__aeabi_dcmpun` | 54 |
| `chart.constprop.0` | 44 |
| `history_get.constprop.0` | 40 |
| `chart` | 32 |
| `__aeabi_cdrcmple` | 32 |
| `__aeabi_dcmpge` | 18 |
| `__aeabi_dcmpgt` | 18 |
| `__aeabi_dcmple` | 18 |
| `__aeabi_dcmplt` | 18 |
| `__gnu_thumb1_case_uqi` | 18 |
| `__aeabi_cdcmpeq` / `__aeabi_cdcmple` | 16 |
| `__wrap___aeabi_dsub` | 16 |
| `index_of` | 16 |
| `__aeabi_dcmpeq` | 12 |
| `fault` | 2 |

The symbol table has 16 B of overlapping extents and 20 B outside named function extents. Individual overlap ownership is conventional. The byte union, not the sum of extents, is authoritative.

## Reconciliation

17,608 B raw symbol-name extents − 512 B same-extent aliases − 16 B overlapping tail + 20 B unowned = **17,100 B**.

Static total: 17,100 text + 1,016 constants + 6,928 BSS + 28 vectors = **25,072 B**. Adding the provisional 1,024 B stack allowance gives **26,096 B**. Platform integration and a worst-case stack bound remain open.
