"""Fault-injection audit of a too-strong transactional claim. No source changes."""
from unittest.mock import patch
import json
from pathlib import Path
import numpy as np
from experiments.hysteresis_refinement_001.test_field import MixedTests
from experiments.foster_campaign_001.backend import identity

OUT=Path('provenance/h7_proofs_001/flush_failure.json')
if OUT.exists():raise FileExistsError(OUT)
MixedTests.setUpClass()
try:
    fixture=MixedTests();field=fixture.field(7);before=dict(count=field.count,state=field.state.copy(),root=field.root.copy())
    caught=None
    with patch('numpy.linalg.qr',side_effect=np.linalg.LinAlgError('injected QR failure')):
        try:field.update(0,fixture.obs[:16])
        except np.linalg.LinAlgError as e:caught=str(e)
    result=dict(status='strong_failure_atomicity_claim_refuted',exception=caught,
        before_count=before['count'],after_count=field.count,
        response_state_changed=not np.array_equal(field.state,before['state']),
        likelihood_root_unchanged=np.array_equal(field.root,before['root']),
        source=identity(Path('experiments/hysteresis_refinement_001/field.py')),
        disposition='Do not retry or checkpoint this partial field. Current compact campaign catches LinAlgError and marks arm unresolved; successful normal-path proof excludes this failure. Backend-wide rollback/quarantine proof remains open.',
        production_changed=False)
    assert caught and result['response_state_changed'] and result['likelihood_root_unchanged']
    OUT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
finally:MixedTests.tearDownClass()
