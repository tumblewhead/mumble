"""Opt-in RC5/H7 history with native fixed-origin tangent feedback.

No harness inputs or truth; no conversion of existing H5 checkpoints.
"""
import json
from .backend import identity,ROOT
from .tangent_backend import TangentBackend,DEPENDENCIES as TANGENT_DEPENDENCIES
from experiments.field_tangent_native_001.native import Native,build as build_native
from experiments.hysteresis_refinement_001.field import MixedField,Compressed,build
from experiments.foster_uncertainty_audit_001.conditional_packet import partition

DEPENDENCIES=[*TANGENT_DEPENDENCIES,'experiments/foster_campaign_001/h7_backend.py',
              'experiments/hysteresis_refinement_001/field.py','experiments/hysteresis_refinement_001/response.c']


def prepare_h7(campaign):
    directory=campaign/'backend_h7';receipt=directory/'build.json'
    if receipt.exists():
        info=json.loads(receipt.read_text())
        for name in ('response','tangent'):
            if identity(directory/(name+'.so'))!=info[name]:raise ValueError('H7 binary changed')
        return directory/'response.so',directory/'tangent.so'
    response=build(directory);tangent=build_native(directory,hdegree=7)
    receipt.write_text(json.dumps(dict(response=identity(response),tangent=identity(tangent),
        representation='RC5/H7 width112 live167',sources={n:identity(ROOT/n) for n in DEPENDENCIES}),indent=2)+'\n')
    return response,tangent


class H7Backend(TangentBackend):
    def _make_field(self,campaign,config,source):
        response,_=prepare_h7(campaign)
        return MixedField(config,partition(self.mean)[1],1.,7,response,source)
    def _make_native(self,campaign):
        _,native=prepare_h7(campaign)
        return Native(native,self.field,self.mean,self.prior_root)
    def _make_objective(self):
        return Compressed(self.field,self.mean,self.prior_root)
