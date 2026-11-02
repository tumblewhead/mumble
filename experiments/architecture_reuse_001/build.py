"""Isolated native builds; existing campaign build/default paths stay untouched."""
from pathlib import Path
import shutil
import subprocess
from experiments.foster_campaign_001.backend import ROOT, identity
from experiments.h7_history_quality_001.history import write
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.field_tangent_native_001.native import Native
from experiments.hysteresis_refinement_001.field import MixedField
from experiments.foster_uncertainty_audit_001.conditional_packet import partition

HERE=Path(__file__).resolve().parent
FLAGS=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-fPIC','-fstack-usage']


def build(directory,candidate=True,counters=False,native=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=HERE/'response.c' if candidate else ROOT/'experiments/hysteresis_refinement_001/response.c'
    text=source.read_text()
    if counters:
        text=text.replace('exp(','ar_exp(').replace('expm1(','ar_expm1(')
        wrapper='''#include <stdint.h>
static uint64_t nexp,nexpm1;
void ar_reset(void) { nexp=0;nexpm1=0; }
uint64_t ar_exp_count(void) { return nexp; }
uint64_t ar_expm1_count(void) { return nexpm1; }
static double ar_exp(double x) { nexp++;return exp(x); }
static double ar_expm1(double x) { nexpm1++;return expm1(x); }
'''
        text=text.replace('#include <stddef.h>','#include <stddef.h>\n'+wrapper)
    path=directory/'response.c';path.write_text(text)
    response=directory/'response.so';commands=[['cc',*FLAGS,'-shared',str(path),'-lm','-o',str(response)]]
    subprocess.run(commands[-1],check=True)
    tangent=None
    if native:
        if counters:raise ValueError('timed native builds must not contain counters')
        for name in ('kernel.c','kernel.h'):shutil.copy2(ROOT/'experiments/field_tangent_native_001'/name,directory/name)
        tangent=directory/'tangent.so'
        commands.append(['cc',*FLAGS,'-DFT_HDEG=7','-shared',str(directory/'kernel.c'),str(path),'-lm','-o',str(tangent)])
        subprocess.run(commands[-1],check=True)
    macros=subprocess.check_output(['cc','-dM','-E','-include','float.h','-'],input='',text=True)
    write(directory/'build.json',dict(candidate=candidate,counters=counters,commands=commands,
        compiler=subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
        floating_macros=[s for s in macros.splitlines() if any(k in s for k in ('FLT_EVAL_METHOD','__STDC_IEC_559__','__DBL_MANT_DIG__'))],
        original_source={str(source.relative_to(ROOT)):identity(source)},
        built_sources={p.name:identity(p) for p in directory.iterdir() if p.suffix in ('.c','.h')},
        binaries={p.name:identity(p) for p in directory.glob('*.so')},
        stack_reports={p.name:p.read_text() for p in directory.glob('*.su')}))
    return response,tangent


class ReuseBackend(H7Backend):
    def _make_field(self,campaign,config,source):
        self._reuse_response,self._reuse_tangent=build(campaign/'reuse_native',native=True)
        return MixedField(config,partition(self.mean)[1],1.,7,self._reuse_response,source)

    def _make_native(self,campaign):
        return Native(self._reuse_tangent,self.field,self.mean,self.prior_root)
