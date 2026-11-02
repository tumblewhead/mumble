"""Array/payload audit of the desktop controls, explicitly not a target layout."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.joint_rate_history_001.field import Field
from experiments.hysteresis_refinement_001.field import MixedField
from experiments.foster_campaign_001.backend import identity
from experiments.h7_history_quality_001.history import write


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    r=json.loads((args.run/'registration.json').read_text());records={};chunk=1024
    for name,degree in [('response_degree1',1),('response_degree2',2),('H7',7)]:
        if name=='H7':f=MixedField(r['config'],r['center'],1.,7,(args.run/'response/response.so').resolve())
        else:f=Field(r['config'],r['center'],1.,degree,(args.run/'response_control/response.so').resolve());f.m=f.n
        arrays={k:v.nbytes for k,v in vars(f).items() if isinstance(v,np.ndarray)}
        packed=8*f.width*(f.width+1)//2
        records[name]=dict(array_bytes=arrays,retained_numpy_array_bytes=sum(arrays.values()),packed_factor_B=packed,
            packed_factor_response_domain_scalars_B=packed+f.state.nbytes+80+16,
            input_chunk_B=8*chunk*5,response_rows_B=8*chunk*f.width,
            stacked_qr_input_B=8*(chunk+f.width)*f.width,old_dense_root_B=f.root.nbytes,new_dense_root_B=f.root.nbytes,
            response_state_trial_B=f.state.nbytes,
            scope='Scratch categories have overlapping lifetimes and are not blindly summed; QR/LAPACK workspace, row-normalization temporaries, prior, solver, Python objects, stacks/ISR and registry remain additional. Packed subtotal omits calibration/rate/projection tables and metadata. No complete MCU RAM claim.')
    write(args.out,dict(source=identity(Path(__file__)),registration=identity(args.run/'registration.json'),chunk_records=chunk,arms=records))

if __name__=='__main__':main()
