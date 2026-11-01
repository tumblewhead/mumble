"""Build the compact qualification receipt; preserve all earlier evidence."""
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity,ROOT

HERE=Path(__file__).resolve().parent

def main():
    parent=HERE.parent/'field_feedback_preservation_001';old=json.loads((parent/'qualification.json').read_text())
    for key in ('source_identities','artifacts'):
        for name,expected in old[key].items():
            if identity(parent/name)!=expected:raise ValueError('preserved parent changed: '+name)
    parity=json.loads((HERE/'parity001/result.json').read_text())
    assert all(c['status']=='passed' for c in parity['cases'])
    n=sum(c['windows'] for c in parity['cases']);native=sum(c['timing']['native_s'] for c in parity['cases']);python=sum(c['timing']['python_s'] for c in parity['cases'])
    artifacts={};campaigns={}
    for label in ('weak','embedded'):
        campaign=HERE/(label+'4h002');case=campaign/'case_0000';result=json.loads((case/'result.json').read_text())
        assert result['status']=='completed'
        arms={}
        for kind,arm in result['arms'].items():
            message=np.load(case/(kind+'_message.npy'))
            prior_message=np.load(HERE/(label+'4h001')/'case_0000'/(kind+'_message.npy'))
            np.testing.assert_array_equal(message,prior_message)
            if label=='weak':np.testing.assert_array_equal(message,np.load(HERE/'weak_replay001'/(kind+'_message.npy')))
            arms[kind]=dict(metrics=arm['all'],final_Q_log_SD_percent=100*float(np.linalg.norm(message[16:272].reshape(16,16)[5])),
                            field_history=arm.get('field_history'),status=arm['status'])
        profile=json.loads((HERE/(label+'_profile.json')).read_text())
        campaigns[label]=dict(path=str(campaign.relative_to(ROOT)),configuration=json.loads((campaign/'campaign_plan.json').read_text())['configuration'],
                              records=result['records'],arms=arms,backend_microseconds_per_window=profile['microseconds_per_window'],
                              plotted=all((case/(name+'.png')).exists() for name in ('errors','parameters_reference','parameters_effective','states','signals','capacitances')))
        for name in ['summary.json','campaign_plan.json','backend_tangent/build.json','case_0000/result.json','case_0000/inputs.json','case_0000/checkpoints/index.json']:
            path=campaign/name;artifacts[str(path.relative_to(HERE))]=identity(path)
    for name in ('parity001/result.json','weak_profile.json','embedded_profile.json','weak_replay001/result.json'):
        artifacts[name]=identity(HERE/name)
    for name in ('weak4h001/case_0000/result.json','embedded4h001/case_0000/result.json'):
        artifacts[name]=identity(HERE/name)
    files=list(HERE.glob('*.py'))+list(HERE.glob('kernel.*'))
    files += [ROOT/'experiments/foster_campaign_001'/name for name in ('backend.py','tangent_backend.py','compact.py','run.py','plot.py','compact_plot.py','test_tangent_backend.py','test_field_backend.py')]
    receipt=dict(schema='field_tangent_native_v1',status='qualified_for_opt_in_short_desktop_controls',base_revision='375ef47',branch='implementation/field-tangent-native-001',
        mainline_changed=False,default_changed=False,tests=dict(native=10,campaign=37,
        commands=['OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.field_tangent_native_001.test_native -q',
        'OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.foster_campaign_001.test_tangent_backend experiments.foster_campaign_001.test_field_backend experiments.foster_campaign_001.test_field_default experiments.foster_campaign_001.test_compact experiments.foster_campaign_001.test_plot_summary -q']),
        parity=parity,kernel_host_timing=dict(windows=n,native_update_query_us=native/n*1e6,python_update_query_us=python/n*1e6,speed_ratio=python/native,
        exclusions='Common field accumulation, scheduled nonlinear fitting, campaign adapter, disk, plots; not MCU timing'),
        storage=dict(previous_partial_packed_B=41368,field_packed_plus_live_B=28864,native_context_B=1376,combined_partial_packed_B=30240,
        native_explicit_workspace_B=5880,packed_plus_native_workspace_B=36120,original_prior_mean_root_B=2176,desktop_readout_carrier_B=2208,
        desktop_extra_live_state_B=888,desktop_pending_raw_B=163840,desktop_dense_field_root_B=53792,
        kernel_host_max_reported_function_frame_B=160,kernel_host_frame_scope='Compiler -fstack-usage per function; excludes nested calls/libm/ctypes/ARM ABI; not total stack',
        scope='Partial layout accounting, not whole subsystem SRAM. Projection tables, caller lifted rows/query output, field QR/full-fit workspace, binding metadata and Python overhead additional. No M23 timing or10KiB qualification.'),
        campaigns=campaigns,final_debug_replay_bitwise_equal=True,prior_study_artifacts_and_sources_preserved=True,
        adaptations=['First smoke found duplicate storage scope metadata key; fixed before qualification.',
        '001 campaigns retained before removal of misleading legacy rolling-token storage fields for tangent64. 002 repeats with final recording code and plots; all final messages bitwise identical.',
        'C streaming Givens replaces Python Householder QR; structured contractions replace dense derivative cache. Mathematical tangent objective unchanged.',
        'Live16-sample response transport plus bounded4096-row raw batching retains prior field accumulation order; response recurrence is computed twice across batch flushes.'],
        limits=['Local GN uncertainty, not calibrated posterior coverage; same-stream miss counts are correlated diagnostics.',
                'Stationary parameters only; long-duration hysteresis compression error, aging and24/72/720h inference unqualified.',
                'Default/mainline unchanged. Integrated native tangent is about1.5x slower than current field arm in suffix profiles, despite8.4x kernel improvement over Python prototype.',
                'Original public prior once; outgoing Gaussian never fed back. Invalid readout triggers explicit full-field recovery; unresolved recovery stops arm.'],
        sources={str(p.relative_to(ROOT)):identity(p) for p in files},artifacts=artifacts,
        next='Run24/72h mixed/weak controls with identical streams and local-uncertainty diagnostics; inspect hysteresis drift separately before promotion. Profile adapter/duplicate recurrence before optimizing; retain physical-domain/source guards.')
    (HERE/'qualification.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=receipt['status'],storage=receipt['storage'],kernel_timing=receipt['kernel_host_timing']),indent=2))
if __name__=='__main__':main()
