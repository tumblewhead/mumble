# Current Foster estimator: Cortex-M23 resource audit

There is a useful C core to analyze, but the current successful desktop pipeline
is not yet a complete C estimator. This audit targets the user's baseline
Cortex-M23 custom silicon running in Verilog simulation at **16 MHz**, with the
existing **10,240-byte estimator SRAM** planning ceiling.

| Component | Current implementation |
|---|---|
| Physical Foster recurrence, five states, eleven parameters, analytic sensitivities and boundary transport | [model.c](../foster_feedback_001/model.c), C, all double precision |
| Rolling four-round fit and line search | [estimator.py](../foster_feedback_001/estimator.py), Python/NumPy |
| Likelihood QR, joint square-root update and token encoding | [history.py](../foster_feedback_001/history.py), Python/NumPy |
| Evidence ownership, staging and commit | Python protocol; needs a C implementation |
| Earlier bounded rolling engine | [rolling_engine.c](../live_anchor_integration_001/rolling_engine.c), C, but a different original-state/history approximation |

The old C engine offers useful packed-workspace and ingestion patterns. Its
8,680-byte context plus two768-byte stack/runtime reserves gave a10,216-byte
plan, not a measured full target result. That budget cannot be transferred to
the newer Gaussian-history estimator or its new physical conventions.

## Actual cross-build measurements

The unchanged current model compiled successfully with ARM GCC16.2.0,
`-mcpu=cortex-m23 -mthumb -mfloat-abi=soft -O2`, strict floating-point settings
and `-fstack-usage`. [summary.json](summary.json) records commands and arithmetic;
[size.txt](size.txt), the `.su` files and disassembly preserve compiler evidence.

| Item | Bytes | Scope |
|---|---:|---|
| Model's own M23 stack frame | **3,944** | Excludes called math/software-arithmetic routines |
| Model object text | **2,820** | Before linking math/runtime |
| Minimal linked model-probe text | **11,972** | Model, caller and this toolchain's required runtime/math |
| Probe static data + BSS | **8,032** | One history message, one raw block and one evaluation output set, plus library globals |
| Probe static RAM + known caller/model frames | **12,000** | Already above10,240; still excludes library call-stack and interrupts |

The [link probe](link_probe.c) is an accounting artifact. It uses default linker
addresses and placeholder inputs, without vector table, startup or the custom
silicon's memory map. It was not executed and is not a firmware image. The
newlib/nosys link emitted unimplemented-I/O-stub warnings; there is no I/O driver
or acquisition claim. Text/data totals depend on the selected libraries.

## Memory gap and plausible reductions

The familiar **6,269 B** is only two full joint messages plus a float32 token.
The16-record numeric input window adds640 B; that subtotal omits model and solver
workspace. A16-record evaluation returns4,352 B: voltages128, Jacobian2,048,
endpoint128 and transport2,048. The compiled model's3,944-byte frame is additional.

A simple model-evaluation phase needs at least **11,360 B of named numerical
storage and own frame** with the current interface, before the caller/library
stack. A literal translation retaining the Python path's prediction, current-fit
and trial output arrays reaches **22,624 B** of named trial-phase buffers and own
frame, still before complete runtime accounting. This latter number is a
source-lifetime ledger, not a measured complete C port. Therefore a straightforward
translation is more than twice the SRAM budget; a deliberately scheduled layout
is required. Token-creation and model-evaluation peaks are separate phases and
must not simply be added indiscriminately.

There are specific reductions that preserve the intended mathematics:

1. Eliminate dense mostly-zero parameter-derivative arrays and reuse scratch
   across phases. Two11×16 derivative tables alone contain2,816 B of doubles.
2. Use a value-only model path for diagnostic predictions and rejected line-search
   trials; retain full Jacobians only where required.
3. Store the first five rows of transport F; its last eleven rows are exactly
   `[0,I]` for the stationary parameter model. This saves704 B in a float32 token.
4. Re-triangularize the propagated covariance root using orthogonal transforms
   and pack its136 independent entries. A message would then use1,224 B including
   its mean and log normalizer, versus2,184 B now. Dropping entries from the
   current nontriangular root without that transform would be incorrect.
5. Use explicit reusable QR/Cholesky/triangular-solve workspaces and one staged
   history computation. The desktop path currently computes history advancement
   once for preview and again during prepare.

Items3–4 suggest **3,645 B** for two messages plus a structured float32 token,
before all workspace/metadata. This is an unimplemented design estimate, not a
10 KiB certificate. Compiler frames, acquisition buffering, configuration,
transactions, math-library stack and interrupts still need a simultaneous-live
layout and RTL validation. No precision reduction is necessary to derive these
structural savings.

## Compute at16 MHz

The stream provides about **457,143 cycles per sample**, or **7,314,286 cycles
per16-sample block**, if the estimator could use the entire processor. Other
work reduces that allowance. The actual implementation must also accept samples
while processing a block, with an explicit ingress buffer/deadline contract.

M23 has no FPU ([Arm Keil core description](https://www.keil.arm.com/devices/arm-armcm23/processors/)).
The compiled model calls software double add/multiply/divide/comparison helpers,
plus `exp` and `expm1`. **The float32 token option does not make the computation
float32**: tokens decode to double, and messages, fitting and model arithmetic
remain double precision.

At nonzero current, one16-sample model evaluation invokes251 `exp` and64 `expm1`
calls in the current source. The preserved original four-hour run averaged
4.317 full model evaluations per block, including its predictive diagnostic,
plus a zero-length domain check. An all-active-current workload at that mean
would mean approximately2,395 `exp` and604 `expm1` calls per simulated second,
in addition to software-double recurrence/sensitivity arithmetic and16-dimensional
matrix work. The original trace contains rest, so this is an active-equivalent
projection, not its measured transcendental count. The bounded line search can
require up to34 full model evaluations per block including the diagnostic.

This is sufficient to flag compute as a serious16 MHz risk, but it does **not**
establish a cycle count or prove the deadline is missed. Software-library paths,
multiplier behavior, instruction/data memory waits and bus integration require
measurement on the RTL. Host seconds are not a reliable conversion to target
cycles. Neither QEMU nor RTL timing was measured in this audit.

Useful arithmetic reductions include caching known thermal factors when T is
unchanged, reusing exact RC/hysteresis decays for repeated dt/I/T within a
candidate evaluation, value-only trial evaluation and specialized triangular
solves. Reducing precision is a later independent experiment: the earlier
coefficient-only precision comparison does not validate a float32 solver.

## Next concrete step

Port the current block fitter and joint-history update into an explicit-workspace
C reference, preserving source ownership and the desktop likelihood. Replay the
saved successful CC–CV case and the weak-excitation failures through it. Then
provide an RTL-callable block benchmark with completion/status symbols and the
custom memory map, measuring both typical and bounded worst-case work at16 MHz.
This establishes the complete SRAM/CPU gap before replacing arithmetic or
introducing approximations. No model or estimator was changed in this audit.
