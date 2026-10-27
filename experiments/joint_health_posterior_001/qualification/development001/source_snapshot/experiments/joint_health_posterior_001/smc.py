"""Tempered SMC with whole-path symmetric Metropolis rejuvenation.

An individual particle population is an approximation, never an adequacy
certificate. Independent populations and particle-count refinement are required.
"""
from dataclasses import dataclass
import math
import numpy as np
from model import k


@dataclass(frozen=True)
class Config:
    particles: int
    mutations: int = 24
    ess_fraction: float = .8
    max_stages: int = 96
    proposal_factor: float = 1.5

    def __post_init__(self):
        k.require(type(self.particles) is int and self.particles >= 32 and
                  type(self.mutations) is int and self.mutations >= 1 and
                  0 < self.ess_fraction < 1 and self.max_stages >= 1 and
                  math.isfinite(self.proposal_factor) and self.proposal_factor > 0,
                  'invalid_input', 'SMC configuration')


def weights(logweights):
    k.require(np.isfinite(logweights).any() and not np.isnan(logweights).any(),
              'uncertainty_unresolved', 'no finite particle mass')
    peak = float(np.max(logweights))
    w = np.exp(logweights-peak)
    total = float(w.sum())
    return w/total, peak+math.log(total)-math.log(len(w))


def resample(rng, w):
    # Stratified resampling; input order remains the particle order, not time.
    cdf = np.cumsum(w)
    cdf[-1] = 1.
    return np.searchsorted(cdf, (np.arange(len(w))+rng.random(len(w)))/len(w))


def population(target, config, seed):
    rng = np.random.default_rng(seed)
    n, d = config.particles, target.dimension
    u = target.draw(rng, n)
    prior, like, projected = target.evaluate(u)
    k.require(np.isfinite(prior).all(), 'sampling_unresolved', 'invalid initial prior sample')
    beta, log_evidence = 0., 0.
    ancestors = np.arange(n)
    stages = []
    while beta < 1:
        k.require(len(stages) < config.max_stages, 'resource_limit', 'tempering stage cap')
        # Starting weights are uniform after each resample/move stage.
        def incremental(new_beta):
            w, logz = weights((new_beta-beta)*like)
            return w, logz, 1./float(w@w)
        w, increment, ess = incremental(1.)
        next_beta = 1.
        if ess < config.ess_fraction*n:
            left, right = beta, 1.
            for _ in range(48):
                middle = (left+right)/2
                if incremental(middle)[2] < config.ess_fraction*n:
                    right = middle
                else:
                    left = middle
            next_beta = left
            w, increment, ess = incremental(next_beta)
        k.require(next_beta > beta, 'uncertainty_unresolved', 'tempering stalled')
        # Fit covariance once per stage BEFORE mutation. Fixed symmetric
        # proposal within each Metropolis kernel; target density always exact.
        center = w@u
        delta = u-center
        covariance = (delta*w[:, None]).T@delta
        ridge = 1e-8*np.maximum(np.diag(covariance), 1e-4)
        chol = np.linalg.cholesky(covariance+np.diag(ridge))
        chol *= config.proposal_factor/math.sqrt(d)
        selected = resample(rng, w)
        u, prior, like, projected = u[selected], prior[selected], like[selected], projected[selected]
        ancestors = ancestors[selected]
        accepted = 0
        for _ in range(config.mutations):
            proposal = u+rng.normal(size=u.shape)@chol.T
            pp, pl, py = target.evaluate(proposal)
            logratio = pp-prior+next_beta*(pl-like)
            take = np.log(rng.random(n)) < logratio
            u[take], prior[take], like[take], projected[take] = proposal[take], pp[take], pl[take], py[take]
            accepted += int(take.sum())
        log_evidence += increment
        stages.append(dict(beta=next_beta, incremental_weight_ESS=ess,
                           accepted_fraction=accepted/(n*config.mutations),
                           surviving_initial_ancestors=len(np.unique(ancestors))))
        beta = next_beta
    return dict(seed=seed, particles=u, projected=projected, stages=stages,
                log_evidence=log_evidence, point_statistic_kind='particle_marginal',
                posterior_numerical_status='requires_independent_replication',
                weight_ESS_is_not_posterior_effective_sample_size=True)


def moments(samples):
    mean = np.mean(samples, axis=0)
    delta = samples-mean
    return dict(mean=mean, covariance=delta.T@delta/len(samples),
                quantiles=np.quantile(samples, [.05, .5, .95], axis=0))


def level(populations):
    summaries = [moments(p['projected']) for p in populations]
    means = np.array([s['mean'] for s in summaries])
    covariances = np.array([s['covariance'] for s in summaries])
    quantiles = np.array([s['quantiles'] for s in summaries])
    r = len(populations)
    k.require(r >= 4, 'uncertainty_unresolved', 'at least four independent populations required')
    combined = moments(np.concatenate([p['projected'] for p in populations]))
    combined.update(mean_MCSE=means.std(axis=0, ddof=1)/math.sqrt(r),
        covariance_MCSE=covariances.std(axis=0, ddof=1)/math.sqrt(r),
        quantile_MCSE=quantiles.std(axis=0, ddof=1)/math.sqrt(r),
        log_evidence_mean=float(np.mean([p['log_evidence'] for p in populations])),
        log_evidence_MCSE=float(np.std([p['log_evidence'] for p in populations], ddof=1)/math.sqrt(r)))
    return combined


def assess(low, high, scales):
    """Registered finite diagnostics for moments/quantiles; not a density gate."""
    sd = np.sqrt(np.maximum(np.diag(high['covariance']), 0.))
    sd = np.maximum(sd, 1e-8*np.asarray(scales))
    covariance_scale = np.outer(sd, sd)
    scores = dict(mean_MCSE_SD=float(np.max(high['mean_MCSE']/sd)),
        covariance_MCSE_scaled=float(np.max(high['covariance_MCSE']/covariance_scale)),
        quantile_MCSE_SD=float(np.max(high['quantile_MCSE']/sd)),
        refinement_mean_SD=float(np.max(abs(high['mean']-low['mean'])/sd)),
        refinement_covariance_scaled=float(np.max(abs(high['covariance']-low['covariance'])/covariance_scale)),
        refinement_quantile_SD=float(np.max(abs(high['quantiles']-low['quantiles'])/sd)),
        log_evidence_MCSE=high['log_evidence_MCSE'],
        refinement_log_evidence=abs(high['log_evidence_mean']-low['log_evidence_mean']))
    limits = dict(mean_MCSE_SD=.08, covariance_MCSE_scaled=.12, quantile_MCSE_SD=.15,
                  refinement_mean_SD=.15, refinement_covariance_scaled=.25,
                  refinement_quantile_SD=.3, log_evidence_MCSE=.2, refinement_log_evidence=.5)
    passed = all(scores[name] <= threshold for name, threshold in limits.items())
    return dict(status='finite_moment_checks_passed' if passed else 'uncertainty_unresolved',
                diagnostics=scores, limits=limits, rigorous_error_bound=False,
                density_contrast_0_1_NLL_qualified=False, coverage_validated=False)
