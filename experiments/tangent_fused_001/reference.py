"""Execute under frozen original imports; never bypass original replay checks."""
import json
from pathlib import Path
import sys


def main():
    frozen,prefix,out=map(Path,sys.argv[1:])
    sys.path.insert(0,str(frozen.resolve()))
    import numpy as np
    from experiments.foster_campaign_001.compact import restore_checkpoint
    from checks import exported,capture,digest,save,identity
    meta,saved,mean,root=exported(prefix)
    job=json.loads((prefix/'job.json').read_text());campaign=Path(job['campaign']);case=campaign/job['prefix']['case']
    scenario=json.loads((case/'scenario.json').read_text())
    fields={k:scenario[k] for k in ('cell','load','noise_v','seed','load_seed') if k in scenario}
    _,banks,binding=restore_checkpoint(case,job['prefix']['checkpoint'],meta['config'],scenario['cell_definition'],fields,meta['settings'])
    bank=banks['tangent64'];actual=capture(bank)
    if not all(np.array_equal(actual[k],v) for k,v in saved.items()):raise ValueError('original checkpoint/export mismatch')
    np.testing.assert_array_equal(bank.mean,mean);np.testing.assert_array_equal(bank.prior_root,root)
    observations=np.load(prefix/'observations.npy',allow_pickle=False)
    hashes=[]
    for offset in range(0,len(observations),16):
        bank.advance(meta['sequence']+offset,observations[offset:offset+16]);hashes.append(digest(bank))
    save(out,dict(schema='frozen_tangent_suffix_v1',binding=binding['binding'],prefix=str(prefix),
        initial_export=identity(prefix/'initial_estimator_state.npz'),observations=identity(prefix/'observations.npy'),
        committed_window_hashes=hashes,final_counts=bank.counts(),records=len(observations)))


if __name__=='__main__':main()
