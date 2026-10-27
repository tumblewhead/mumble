"""One bounded probe or posterior-prefix worker; observation-only inputs."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np
from common import Target,Work,model,smc,posterior,read_records,save


def worker(mode,n,inputs,out):
    out.mkdir(parents=True)
    cfg=json.loads((inputs/'inference.json').read_text())
    source,records=read_records(inputs/f'observations_{n}.json')
    profile=model.k.Profile(tuple(cfg['profile_rates']))
    cap=(cfg['cost_probes']['total_conservative_steps_cap']//len(cfg['cost_probes']['prefixes'])
         if mode=='probe' else cfg['caps']['prefix_conservative_steps'][str(n)])
    work=Work(cap)
    started_cpu=time.process_time();started_wall=time.monotonic()
    targets=[]
    result=dict(status='failed',mode=mode,prefix=n,source_id=source,
                elapsed_s=sum(r.dt for r in records),dimension=16+2*n,
                canonical_records=0,truth_reads=0,posterior_populations_completed=0)
    def target():
        t=Target(records,profile,work,source,max_paths=cfg['max_paths_per_population'])
        targets.append(t)
        return t
    try:
        if mode=='probe':
            t=target();paths=t.draw(np.random.default_rng(900000+n),cfg['cost_probes']['prior_paths'])
            times=[]
            for _ in range(cfg['cost_probes']['repeated_density_batches']):
                before=time.process_time();prior,like,projected=t.evaluate(paths);times.append(time.process_time()-before)
                model.k.require(np.isfinite(prior).all(),'sampling_unresolved','invalid probe prior')
            d=t.dimension
            result.update(status='completed_cost_probe_only',density_batch_CPU_s=times,
                median_CPU_s_per_evaluated_path=float(np.median(times))/len(paths),
                prior_paths=len(paths),path_matrix_bytes=paths.nbytes,
                one_4096_path_matrix_bytes=4096*d*8,one_dense_covariance_bytes=d*d*8,
                posterior_numerical_status='not_computed')
        elif mode=='posterior':
            levels=[];population_stats=[]
            for level,nparticles in enumerate(cfg['particle_levels']):
                populations=[]
                for replicate in range(1,cfg['replicates_per_level']+1):
                    seed=800000+1000*n+100*level+replicate
                    t=target();cpu=time.process_time();wall=time.monotonic()
                    p=smc.population(t,smc.Config(nparticles,mutations=cfg['mutations'],
                        proposal_factor=cfg['proposal_factor'],ess_fraction=cfg['ess_fraction'],
                        max_stages=cfg['max_stages']),seed)
                    # Capture a completed population BEFORE other accounting or
                    # adequacy checks can fail. No hidden completed-run loss.
                    stem=f'population_n{nparticles}_seed{seed}'
                    with (out/(stem+'.npz')).open('xb') as f:
                        np.savez_compressed(f,particles=p['particles'],projected=p['projected'])
                    metadata={key:value for key,value in p.items() if key not in ('particles','projected')}
                    metadata.update(CPU_s=time.process_time()-cpu,wall_s=time.monotonic()-wall,
                        actual_model_steps=t.model_steps,path_evaluations=t.path_evaluations,
                        path_matrix_bytes=p['particles'].nbytes,projected_array_bytes=p['projected'].nbytes)
                    save(out/(stem+'.json'),metadata)
                    population_stats.append(metadata);populations.append(p)
                    result['posterior_populations_completed']+=1
                    print(json.dumps(dict(prefix=n,particles=nparticles,replicate=replicate,
                        status='population_saved',CPU_s=metadata['CPU_s'],stages=len(p['stages']),
                        reserved_steps=work.steps)),flush=True)
                levels.append(smc.level(populations))
                save(out/f'level_{nparticles}.json',levels[-1])
            adequacy=smc.assess(*levels,posterior.SCALES)
            result.update(status=adequacy['status'],adequacy=adequacy,
                current_order=posterior.CURRENT_ORDER,current_mean=levels[-1]['mean'][:17],
                current_covariance=levels[-1]['covariance'][:17,:17],
                current_mean_MCSE=levels[-1]['mean_MCSE'][:17],
                marginal_quantiles_05_50_95=levels[-1]['quantiles'][:,:17],
                capacity_component_probability=levels[-1]['mean'][17],
                capacity_component_probability_MCSE=levels[-1]['mean_MCSE'][17],
                population_stage_counts=[len(p['stages']) for p in population_stats],
                minimum_stage_acceptance=min(s['accepted_fraction'] for p in population_stats for s in p['stages']),
                final_stage_acceptance=[p['stages'][-1]['accepted_fraction'] for p in population_stats],
                surviving_initial_ancestors=[p['stages'][-1]['surviving_initial_ancestors'] for p in population_stats],
                owns_initial_prior=True,observation_interval=[0,n],transition_interval=[0,n],
                measurement_vs_prediction_change='not_computed_in_conditioned_only_scaling_query',
                coverage_validated=False,density_contrast_gate_qualified=False,target_measured=False)
        else:raise ValueError(mode)
    except Exception as exc:
        import traceback
        result.update(status=exc.status if isinstance(exc,model.k.ModelError) else 'execution_failed',
                      error=traceback.format_exc(),posterior_numerical_status='uncertainty_unresolved')
    result.update(work=work.report(),actual_model_steps=sum(t.model_steps for t in targets),
        CPU_s=time.process_time()-started_cpu,wall_s=time.monotonic()-started_wall,
        peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    save(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('prefix','mode','status','CPU_s','posterior_populations_completed')}),flush=True)
    # Numerical/resource stops are recorded scientific outcomes, not a reason
    # to lose their output by throwing out of the supervisor.
    return 0 if result['status'] not in ('execution_failed','failed') else 1


if __name__=='__main__':
    raise SystemExit(worker(sys.argv[1],int(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4])))
