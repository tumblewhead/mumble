"""Targeted reservation/adapter qualification before scientific sampling."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from dataclasses import replace
import json
from pathlib import Path
import sys
import numpy as np
from common import HERE,Target,Work,model,read_records,save


def main(out,inputs):
    out.mkdir(parents=True)
    checks=0
    def check(ok,label):
        nonlocal checks
        checks+=1
        if not ok:raise AssertionError(label)
    def rejects(fn,status):
        try:fn()
        except model.k.ModelError as exc:check(exc.status==status,'expected '+status)
        else:check(False,'missing '+status)
    result=dict(status='failed',new_posterior_populations=0,independent_review=False)
    try:
        work=Work(12)
        work.reserve(2,3);work.reserve(3,2)
        check(work.steps==12 and work.paths==5,'exact limit allowed')
        before=(work.steps,work.paths,work.calls)
        rejects(lambda:work.reserve(1,1),'resource_limit')
        check(before==(work.steps,work.paths,work.calls) and work.denied==1,'denial does not consume reserved work')
        rejects(lambda:Work(-1),'invalid_input')
        rs=(model.k.Record('fixture',0,.03,.02,3.85),model.k.Record('fixture',1,.04,-.02,3.86))
        profile=model.k.Profile((-.001,-.01,.0001,.001,.2,.5,.1,.3))
        original=model.Target(rs,profile)
        shared=Work(100000)
        wrapped=Target(rs,profile,shared)
        a=original.draw(np.random.default_rng(1),32)
        b=wrapped.draw(np.random.default_rng(1),32)
        check(np.array_equal(a,b),'wrapper leaves seeded prior unchanged')
        for left,right in zip(original.evaluate(a),wrapped.evaluate(a)):
            check(np.array_equal(left,right),'density/projected state bitwise parity')
        check(shared.steps>=wrapped.model_steps and shared.paths==wrapped.path_evaluations,'prior validation included')
        exhausted=Work(0);blocked=Target(rs,profile,exhausted)
        rejects(lambda:blocked.evaluate(a),'resource_limit')
        check(blocked.model_steps==blocked.path_evaluations==exhausted.steps==0,'denial precedes model work')
        # Two targets share the same prospective ledger, rather than each
        # receiving a fresh copy of the campaign allowance.
        shared=Work(64);one=Target(rs,profile,shared);two=Target(rs,profile,shared)
        one.evaluate(a)
        rejects(lambda:two.evaluate(a),'resource_limit')
        check(two.model_steps==0 and shared.steps==64,'shared limit across populations')
        rejects(lambda:Target((replace(rs[0],index=2),),profile,Work(10)),'source_order_error')
        rejects(lambda:Target((replace(rs[0],input_known=False),),profile,Work(10)),'recovery_required')
        previous=()
        for n in (8,32,128):
            source,rows=read_records(inputs/f'observations_{n}.json')
            check(len(rows)==n and rows[:len(previous)]==previous,'exact nested prefix')
            check([r.index for r in rows]==list(range(n)),'record order')
            check(abs(sum(r.dt for r in rows)-n/35)<1e-12,'actual elapsed preserved')
            check(len(set(r.dt for r in rows))>1,'actual interval variation retained')
            check(all(r.source_id==source for r in rows),'source identity')
            previous=rows
        cfg=json.loads((inputs/'inference.json').read_text())
        check('plant_initial_x' not in cfg and 'generation_seed' not in cfg,'inference configuration excludes plant')
        result.update(status='passed',checks=checks,original_model_steps=original.model_steps,
                      wrapped_model_steps=wrapped.model_steps,truth_reads=0)
    except Exception:
        import traceback
        result.update(checks=checks,error=traceback.format_exc())
    save(out/'receipt.json',result);print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]),Path(sys.argv[2])))
