"""Public desktop full-joint posterior API; retained complete paths.

Use solve(records, explicit_profile). No truth argument or saved-posterior
factor exists. A report is usable only to the extent its adequacy checks pass.
"""
from dataclasses import dataclass, replace
import math
import numpy as np
from model import Target, k
import smc


@dataclass(frozen=True)
class Study:
    particles: tuple = (2048, 4096)
    seeds: tuple = ((3201,3202,3203,3204),(4201,4202,4203,4204))
    mutations: int = 48
    proposal_factor: float = .5
    max_paths_per_population: int = 8_000_000

    def __post_init__(self):
        k.require(len(self.particles)==2 and self.particles[1]>=2*self.particles[0]
            and len(self.seeds)==2 and all(len(s)>=4 for s in self.seeds)
            and len(set(self.seeds[0]+self.seeds[1]))==sum(map(len,self.seeds)),
            'invalid_input','independent seeds and particle-count refinement required')


def refine(factory, scales, study=Study(), on_population=None, on_target=None):
    levels=[]
    for n,seeds in zip(study.particles,study.seeds):
        populations=[]
        for seed in seeds:
            target=factory()
            try:
                result=smc.population(target,smc.Config(n,mutations=study.mutations,
                    proposal_factor=study.proposal_factor),seed)
            finally:
                if on_target is not None:on_target(target)
            if on_population is not None:on_population(n,seed,result)
            populations.append(result)
        levels.append(smc.level(populations))
    return dict(levels=levels,adequacy=smc.assess(*levels,scales))


SCALES=np.r_[k.SD,.06,1.,.06,1.]
CURRENT_ORDER=('log_tau1_s','log_tau2_s','log_tau3_s','log_gamma_plus_per_Ah',
    'log_gamma_minus_per_Ah','log_Q_Ah','R0_ohm','R1_ohm','R2_ohm','R3_ohm',
    'H_V','SOC','v1_V','v2_V','v3_V','hysteresis','Q_Ah')


def boundary_report(records, prediction, conditioning):
    """Join independently qualified predictive/conditioned marginal reports."""
    p,q=prediction['levels'][-1],conditioning['levels'][-1]
    pa,qa=prediction['adequacy'],conditioning['adequacy']
    adequate=pa['status']==qa['status']=='finite_moment_checks_passed'
    health={}
    for name,j,old in [('Q_Ah',16,18),('R0_ohm',6,19)]:
        # MCSE for within-run differences must include covariance. The saved
        # per-functional MCSE below is a conservative sum, not independent SE.
        health[name]=dict(predicted_mean=p['mean'][j],conditioned_mean=q['mean'][j],
            predicted_variance=p['covariance'][j,j],conditioned_variance=q['covariance'][j,j],
            model_predicted_change=p['mean'][j]-p['mean'][old],
            model_predicted_change_MCSE_upper_estimate=p['mean_MCSE'][j]+p['mean_MCSE'][old],
            measurement_correction=q['mean'][j]-p['mean'][j],
            measurement_correction_MCSE=math.hypot(q['mean_MCSE'][j],p['mean_MCSE'][j]),
            prediction_uncertainty_change=p['covariance'][j,j]-p['covariance'][old,old],
            conditioning_uncertainty_change=q['covariance'][j,j]-p['covariance'][j,j])
    flags=sorted(set('outside_validated_temperature_scope' for r in records if r.temperature_C!=25))
    return dict(source_id=records[0].source_id if records else 'empty',
        next_record_index=len(records),elapsed_s=sum(r.dt for r in records),
        point_statistic_kind='current_joint_particle_marginal',
        posterior_numerical_status='finite_moment_checks_passed' if adequate else 'uncertainty_unresolved',
        uncertainty_status='model_conditional_numerically_checked_moments' if adequate else 'uncertainty_unresolved',
        prediction_adequacy=pa,posterior_adequacy=qa,health=health,
        current_order=CURRENT_ORDER,current_mean=q['mean'][:17],current_covariance=q['covariance'][:17,:17],
        current_mean_MCSE=q['mean_MCSE'][:17],marginal_quantiles_05_50_95=q['quantiles'][:,:17],
        initial_low_capacity_component_probability=q['mean'][17],
        owns_initial_prior=True,transition_interval=(0,len(records)),observation_interval=(0,len(records)),
        valid_observation_count=sum(r.measurement_valid for r in records),
        boundary_prediction_scope='Previous/current health under predictive path posterior conditional on valid physical support',
        direct_excitation='nonzero final current; not proof of identifiability' if records and records[-1].current else 'no final ohmic excitation',
        correlation_mediated_update='correlations retained; contribution not separately identified',
        flags=flags,physical_rate_calibration=False,coverage_validated=False,target_measured=False,
        residual_mismatch_attribution='not identified; posterior health correction is not proof of aging')


def solve(records, profile, study=Study(), on_population=None, on_target=None):
    records=tuple(records)
    source_id=records[0].source_id if records else 'empty'
    # Validate before launching any populations; failures consume no records.
    Target(records,profile,source_id)
    predicted=records[:-1]+(replace(records[-1],measurement_valid=False,voltage=None),) if records else ()
    def query(rs,name):
        callback=(lambda n,seed,result:on_population(name,n,seed,result)) if on_population is not None else None
        return refine(lambda:Target(rs,profile,source_id,study.max_paths_per_population),
                      SCALES,study,callback,on_target)
    prediction=query(predicted,'prediction')
    if records and records[-1].measurement_valid:
        # Distinct seed blocks avoid treating correlated prediction/posterior
        # simulation noise as independent in measurement_correction_MCSE.
        shifted=replace(study,seeds=tuple(tuple(s+10000 for s in block) for block in study.seeds))
        callback=(lambda n,seed,result:on_population('conditioned',n,seed,result)) if on_population is not None else None
        conditioning=refine(lambda:Target(records,profile,source_id,study.max_paths_per_population),
                             SCALES,shifted,callback,on_target)
    else:
        conditioning=prediction
    report=boundary_report(records,prediction,conditioning)
    if conditioning is prediction:
        for values in report['health'].values():
            values['measurement_correction_MCSE']=0.
    return dict(report=report,prediction=prediction,conditioning=conditioning,
                profile_rates=profile.rates,study=study)
