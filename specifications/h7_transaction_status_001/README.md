# H7 transaction and publication implementation check

This instantiates a limited part of the reviewed [D7 containment contract](../proof_review_001/proofs/D7.md)
and [D2 authorization contract](../proof_review_001/proofs/D2.md). It does not
instantiate their physical coverage, useful authorization or bounded recovery
premises. H5 tangent shares the backend repair; the default field estimator and
the native numerical kernels are unchanged.

## Admitted execution and fault model

One owner calls `advance`, current readout, publication/status, checkpoint and
restore sequentially. Public calibration, native libraries and configuration are
fixed for the object's lifetime. Private numerical helpers and raw ctypes/NumPy
attributes are internal; caller mutation of them is outside this interface.
Synchronous Python `Exception` failures in an admitted advance or restore cause
quarantine. Asynchronous interruption (`KeyboardInterrupt`, signals), concurrent
readers, process/native crashes, power loss, arbitrary memory corruption and
malicious checkpoint substitution are excluded. A synchronous `MemoryError`
disables reads first, but availability of the resulting diagnostic allocation is
not promised. This is a desktop containment change, not firmware qualification.

Admission rejects wrong order, nonfinite/unsupported observations, unrepresentable
intervals and counter overflow before numerical mutation. Such rejection leaves
the previous publication current **at its previous prefix**, with new observations
unconsumed. Only admitted calls enter the guarded transition. No wall-clock expiry
or continued validity for an unobserved physical interval is implied.

## Field commit and consumed evidence

`MixedField.update` computes response rows/state, normalizer and QR root in local
objects, checks finiteness, then assigns all four mutable fields. A synchronous
numerical/allocation failure before that final assignment leaves the field
unchanged. `rows` remains an explicitly response-only generator; it does not
accumulate a likelihood and is not an estimator transaction.

Backend flushing updates a shallow trial field and verifies its exact source
prefix and live response state before committing it and clearing pending rows.
The proof obligation for this shallow copy is concrete: current H5/H7 update
methods replace mutable arrays and only read shared calibration/projection tables.
Future in-place changes must preserve that premise or introduce separate storage.

Native consumption can precede field flushing, query and publication. After any
admitted exception the backend first marks itself failed, then reads the native
count for diagnostics. That count, not potentially stale Python bookkeeping,
is `consumed_records`. If obtaining it fails the count is unknown (`null`). The
last carrier prefix is separately `published_records`. A quarantined arm refuses
`advance`, `full_message`, `readout` and `checkpoint_arrays`; a consumed block
cannot be retried as new evidence through this API.
Failure metadata names the operation (`advance` or `restore`); `input_first`
is an integer for advance failures and null for restore failures. Rejected index
types cannot enter later failure diagnostics.

## Publication and uncertainty meaning

All numeric publication fields (16 means, 16x16 root, normalizer and 16-coordinate
anchor), shapes and uint64 counters are prepared and checked before the carrier
copy. A later diagnostic/readout exception still quarantines the arm, even if
the new carrier has been copied. Thus published and consumed counts may agree
while current readout remains unavailable.

`publication()` returns a copied diagnostic message with its status;
`last_message()` is explicitly diagnostic and must be interpreted with
`publication_status()`. `full_message()` and `readout()` require current status.
Status binds source, model, configuration and actual published prefix. The
configuration digest includes calibration, H5/H7 degrees/width, clock and effective
refresh interval. It reports:

- execution: acquiring, tracking or quarantined;
- readout: current or unavailable;
- guarantee: `provisional_local_precision`;
- authorization: `unresolved`, because no validated query enclosure exists.

These statuses do not change covariance or estimation values. They do not prove
that local widths cover the truth, authorize proposed loads, detect silent bias,
or establish availability. A copied publication is a statement about its named
prefix, not a live capability; callers must re-query status after later operations.
The campaign stores this status in each arm's result alongside its final diagnostic
message. Bare message arrays must not be used as authorization.

## Checkpoint and recovery scope

Checkpoint arrays are independent copies and unavailable in quarantine. Compact
campaigns serialize only active, aligned arms; failed arms retain result metadata
and diagnostic messages but cannot contaminate a survivor's resumable checkpoint.
Full, compact and debug-replay recording use the explicit diagnostic API at exit.

The internal `restore_arrays` method assumes a complete, trusted checkpoint and
matching saved carrier, used by `restore_checkpoint` after file identity and
runtime/source/binary binding checks. It checks schema, source/model/configuration,
clock, counters, cadence, shape/finiteness and chronology, then requires the restored
native query to reproduce the carrier and anchor exactly before clearing quarantine.
Any exception during restoration quarantines the object. These checks are not
an authenticity mechanism or a proof against arbitrary coherent finite tampering
of a field/root/native image. No standalone untrusted-array restoration is supported.

Restoring an older valid prefix does not make it current with the physical world.
The caller must replay the missing ordered observations exactly once. The compact
replay path constructs a fresh backend and returns it only after validation.
There is no autonomous recovery controller or proved recovery deadline here.
Older campaign checkpoints remain bound to their original code; this schema does
not silently migrate them. Replay them using the recorded revision/source snapshot.

## Verification and scope of conclusions

The check combines direct QR/transport/publication/restore fault injection,
campaign failure recording and survivor replay, existing H5/H7 integration tests,
and byte-exact successful-prefix comparison with the preserved pre-repair modules.
Tests support the correspondence above for their injected paths; they do not prove
all runtime fault paths, numerical stability or long-duration physical performance.
Independent review reports and final commands/results are recorded in
[the receipt](../../provenance/h7_transaction_status_001/receipt.json).

The H7 packed field root remains 50,624 bytes (49.44 KiB); this change does not
reduce it. A flush temporarily holds an additional dense root (100,352 bytes for
112x112 doubles), response state and QR workspace; the exact process peak is not
bounded here. Python status/checkpoint copies add host overhead. Complete M23 SRAM,
16 MHz execution time and lifetime coverage remain open obligations.
