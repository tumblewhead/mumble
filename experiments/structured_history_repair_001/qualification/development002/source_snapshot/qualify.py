#!/usr/bin/env python3
"""Fabricated-input qualification; no canonical observation or reference reads."""
import argparse
import ctypes as C
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import study
from study import HERE, ROOT, runner, shape
import numpy as np


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


iq=module('old_types',HERE.parent/'live_anchor_integration_001/qualification/independent_qualification.py')
ad=module('physical_oracle',HERE.parent/'live_anchor_integration_001/qualification/independent_oracle.py')
D=C.c_double;P=C.POINTER;D16=D*16;D37=D*37;D703=D*703
mean=list(ad.PUBLIC_MEAN);sd=list(ad.PUBLIC_SD)


def features(point,origin):
    x=ad.variables(point);d=[(x[i]-origin[i])/sd[i] for i in range(5)]
    d += [(x[11]-origin[11])/sd[11],((-x[5]).exp()-math.exp(-origin[5]))/5.7926168556214002]
    amplitudes=[(x[7+i]/sd[7+i],x[12+i]/sd[12+i]) for i in range(3)]
    h=x[10]/sd[10];u=x[10]*x[15]/(sd[10]*sd[15]);one=ad.AD(1)
    q=[v*d[i]*d[i] for i in range(3) for v in amplitudes[i]]
    q += [v*m for v in (h,u) for m in (d[3]*d[3],d[3]*d[4],d[4]*d[4])]
    q += [d[5]*d[5],d[5]*d[6],d[6]*d[6]]
    linear=[v*d[i] for i in range(3) for v in amplitudes[i]]+[h*d[3],h*d[4],u*d[3],u*d[4],d[5],d[6]]
    return q+linear+[v for pair in amplitudes for v in pair]+[h,u,x[6]/sd[6],one]


def bind(lib):
    sig={
      'sh_context_bytes':([],C.c_size_t),'sh_snapshot_bytes':([],C.c_size_t),
      'sh_feature':([P(D),P(D),C.c_uint],D),
      'sh_feature_derivative':([P(D),P(D),C.c_uint,C.c_uint],D),
      'sh_shift':([P(D),P(D),P(D)],C.c_int),'sh_translate':([P(D),P(D)],C.c_int),
      're_init':([P(iq.Context),P(C.c_ubyte),P(iq.Calibration)],C.c_int),
      're_offer':([P(iq.Context),P(C.c_ubyte),C.c_uint64,P(iq.Raw)],C.c_int),
      're_admit':([P(iq.Context)],C.c_int),'re_commit':([P(iq.Context)],C.c_int),
      're_query':([P(iq.Context),C.c_int,C.c_int],C.c_int),
      're_refine':([P(iq.Context),C.c_uint],C.c_int),'re_process':([P(iq.Context),C.c_uint],C.c_int),
      'rm_init_jet':([P(iq.Jet),P(D)],C.c_int),
      'rm_merge_step':([P(iq.Jet),P(D),P(iq.Sample),D,P(D)],C.c_int),
      'rm_transport':([P(iq.Jet),P(D),P(D),P(iq.Jet)],C.c_int),
      'rm_query_init':([P(iq.QueryState),P(iq.Jet),P(D),P(D)],C.c_int),
      'sh_save':([C.c_char_p,P(iq.Context)],C.c_int),'sh_load':([C.c_char_p,P(iq.Context)],C.c_int)}
    for name,(args,restype) in sig.items():f=getattr(lib,name);f.argtypes=args;f.restype=restype


def qualification(directory):
    directory.mkdir(parents=True);bound=study.sources();budget=runner.Budget(directory,cpu=120,wall=180)
    for name in study.OWN:
        dest=directory/'source_snapshot'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(HERE/name,dest)
    result={'status':'failed','sources':bound,'checks':0,'canonical_input_reads':0,'independent':False,
            'binaries':{},'memory':{},'cases':[]}
    def check(ok,message):
        if not ok:raise AssertionError(message)
        result['checks']+=1
    def close(a,b,message,atol=2e-10,rtol=2e-11):
        check(math.isfinite(a) and math.isfinite(b) and abs(a-b)<=atol+rtol*max(abs(a),abs(b)),message+f': {a} vs {b}')
    try:
        pp=study.paths(shape.load(HERE/'plan.json'));check(len(pp)==5 and all(p.is_absolute() for p in pp.values()),'path preparation')
        for arm in ('control','full'):
            sub=directory/arm;sub.mkdir()
            executable=directory/(arm+'_worker')
            budget.run(study.build(executable,arm),'build_'+arm)
            result['binaries'][arm]=runner.identity(executable)
            shared=sub/'candidate.so';budget.run(study.build(shared,arm,shared=True,stack=True),'shared_'+arm)
            lib=C.CDLL(str(shared));bind(lib)
            check(lib.sh_context_bytes()==C.sizeof(iq.Context)==8680,'context ABI')
            check(lib.sh_snapshot_bytes()==6864,'snapshot ABI')
            # Preprocess branches/macros for the conservative source call graph.
            pre=sub/'preprocessed';pre.mkdir();source_paths=[]
            for name in study.SOURCES[1:]:
                path=ROOT/name if not Path(name).is_absolute() else Path(name)
                output=subprocess.check_output(['cc','-E','-P','-Iinclude',f'-DSH_ANALYTIC_ATTENUATION={int(arm=="full")}',str(path)],cwd=ROOT)
                dest=pre/path.name;dest.write_bytes(output);source_paths.append(dest)
            memory=iq.project_stack(source_paths,list(sub.glob('*.su')))
            memory.update(context_bytes=8680,runtime_IRQ_caller_reservation_bytes=768)
            memory['planning_total_bytes']=8680+max(768,memory['maximum_project_path_bytes'])+768
            result['memory'][arm]=memory;runner.save(sub/'memory.json',memory)
            check(memory['planning_total_bytes']<=10240,'complete planning memory '+str(memory['planning_total_bytes']))
            points=[mean.copy(),[v+.03*s*((i%3)-1) for i,(v,s) in enumerate(zip(mean,sd))]]
            points[1][15]=.25
            for point in points:
                expected=features(point,mean)
                for k,f in enumerate(expected):
                    close(lib.sh_feature(D16(*mean),D16(*point),k),f.v,'feature')
                    for j in range(16):close(lib.sh_feature_derivative(D16(*mean),D16(*point),k,j),f.g[j],'feature derivative')
            check(math.isnan(lib.sh_feature(D16(*mean),D16(*mean),37)),'feature index rejection')
            # Factor translation across repeated shifts, checked against host AD features.
            rng=np.random.default_rng(7821);upper=rng.normal(size=703)*.02;buf=D703(*upper);old=mean.copy()
            def evaluate(u,o,x):
                fs=features(x,o);fv=np.array([z.v for z in fs]);fg=np.array([z.g for z in fs]);mat=np.zeros((37,37));k=0
                for a in range(37):
                    for b in range(a,37):mat[a,b]=u[k];k+=1
                res=mat@fv;return .5*float(res@res),(mat@fg).T@res
            for n in range(3):
                new=[v+(.01 if n%2 else -.015)*s for v,s in zip(old,sd)];shift=(D*7)()
                check(lib.sh_shift(D16(*old),D16(*new),shift)==0,'shift')
                before=[evaluate(list(buf),old,x) for x in points]
                check(lib.sh_translate(buf,shift)==0,'translation')
                for x,(cost,g) in zip(points,before):
                    c2,g2=evaluate(list(buf),new,x);close(c2,cost,'translated cost')
                    for a,b in zip(g2,g):close(a,b,'translated gradient')
                old=new
            before=bytes(buf);bad=(D*7)(*([math.inf]+[0]*6))
            check(lib.sh_translate(buf,bad)<0 and bytes(buf)==before,'nonfinite translation atomic')
            check(lib.sh_translate(buf,C.cast(buf,P(D)))<0 and bytes(buf)==before,'alias translation atomic')
            hostile=D703(*([0.]*703));hostile[0]=sys.float_info.max;before=bytes(hostile)
            check(lib.sh_translate(hostile,(D*7)(2,0,0,0,0,0,0))<0 and bytes(hostile)==before,'overflow preflight atomic')
            # Exact conditional amplitude dependence against independent physical recurrence.
            jet=iq.Jet();check(lib.rm_init_jet(C.byref(jet),D16(*mean))==0,'jet init')
            stream=[(.01+(i%4)*.003,(.04 if i%7<4 else -.025),3.8) for i in range(64)]
            rows=[]
            for dt,current,voltage in stream:
                row=D37();check(lib.rm_merge_step(C.byref(jet),D16(*mean),C.byref(iq.Sample(dt,current,voltage)),.001,row)==0,'merge')
                rows.append(np.array(row))
            amp_points=[]
            for h,h0 in ((0.,0.),(0.,.8),(.02,.7),(.045,-.6)):
                x=mean.copy();x[10]=h;x[15]=h0;x[6]=.12;x[7:10]=[.08,.11,.13];x[12:15]=[.004,-.003,.006];amp_points.append(x)
            for x in amp_points:
                fv=np.array([f.v for f in features(x,mean)])
                predicted=np.array(rows)@fv
                original=ad.block_scalar(x,stream,.001)
                residuals=[(v-s[2])/.001 for v,s in zip(original['voltage'],stream)]
                for a,b in zip(predicted,residuals):close(float(a),b,'exact conditional amplitude',atol=3e-9)
            # Endpoint attenuation under changed rates; forced response need not be exact.
            if arm=='full':
                cp=sum(max(i,0)*dt/3600 for dt,i,v in stream);cm=sum(max(-i,0)*dt/3600 for dt,i,v in stream)
                close(jet.dda[0],cp,'positive charge');close(jet.dda[1],cm,'negative charge')
                previous=mean.copy()
                for n in range(4):
                    x=mean.copy()
                    for i in range(5):x[i]+=(.13 if n%2 else -.17)*(i+1)/5
                    moved=iq.Jet();check(lib.rm_transport(C.byref(jet),D16(*previous),D16(*x),C.byref(moved))==0,'transport')
                    state=iq.QueryState();check(lib.rm_query_init(C.byref(state),C.byref(moved),D16(*x),D16(*x))==0,'query attenuation')
                    for i in range(3):
                        q=jet.model.elapsed/math.exp(x[i]);close(state.a[i],math.exp(-q),'analytic RC');close(state.da[i],q*math.exp(-q),'analytic RC tangent')
                    ha=math.exp(-math.exp(x[3])*cp-math.exp(x[4])*cm);close(state.ha,ha,'analytic ha')
                    for i,c in enumerate((cp,cm)):close(state.dha[i],-math.exp(x[3+i])*c*ha,'ha tangent')
                    jet=moved;previous=x
                jet.model.elapsed=1e6;jet.dda[0]=jet.dda[1]=1e6
                moved=iq.Jet();check(lib.rm_transport(C.byref(jet),D16(*previous),D16(*previous),C.byref(moved))==0,'attenuation underflow')
                check(all(v==0 for v in moved.model.a) and moved.model.ha==0 and all(v==0 for v in moved.model.dha),'underflow finite zeros')
            # Lifecycle, current block Jacobian, prior, cost-only workspace and schema.
            sid=iq.source_id();cal=iq.Calibration.in_dll(lib,'hp_fixture_calibration')
            def new():
                c=iq.Context();check(lib.re_init(C.byref(c),sid,C.byref(cal))==0,'init');return c
            def raw(i):return iq.Raw(200000,iq.Codes(2350+i%4,2048+(80 if i%5<3 else -40),1040))
            def fill(c,start,count):
                for i in range(start,start+count):
                    rr=raw(i);check(lib.re_offer(C.byref(c),sid,i,C.byref(rr))==0,'offer');check(lib.re_admit(C.byref(c))==0,'admit')
            def query(c,x,deriv=1,prior=0):
                c.core.workspace.query.point[:]=x;return lib.re_query(C.byref(c),deriv,prior)
            c=new();fill(c,0,16)
            decoded=[(200000*cal.seconds_per_tick,cal.current_A.offset+raw(i).codes.current*cal.current_A.units_per_code,
                      cal.voltage_V.offset+raw(i).codes.voltage*cal.voltage_V.units_per_code) for i in range(16)]
            exact=ad.block_ad(mean,decoded,.001);check(query(c,mean)==0,'raw block query')
            close(c.core.result.evidence.likelihood_cost,exact['cost'].v,'raw cost',atol=2e-7)
            for i in range(16):close(c.core.workspace.query.gradient[i]*sd[i],exact['cost'].g[i]*sd[i],'raw gradient',atol=3e-7)
            prior,_=ad.public_prior_ad(mean);count=c.core.bank.prior_evaluations
            check(query(c,mean,1,1)==0 and c.core.bank.prior_evaluations==count+1,'prior once')
            close(c.core.result.evidence.prior_cost,prior.v,'unchanged prior')
            before_factor=bytes(c.core.bank.upper);count=c.core.bank.prior_evaluations
            check(lib.re_commit(C.byref(c))==0,'commit')
            check(c.core.bank.next_index==c.core.bank.qr_rows==16 and c.inputs.block_count==0 and c.core.bank.prior_evaluations==count,'exactly once ownership')
            check(query(c,mean)==0,'history query');close(c.core.result.evidence.likelihood_cost,exact['cost'].v,'anchor value retained',atol=2e-7)
            for i in range(16):close(c.core.workspace.query.gradient[i]*sd[i],exact['cost'].g[i]*sd[i],'anchor derivative retained',atol=3e-7)
            packed=bytes(c.core.workspace.query.packed);gradient=bytes(c.core.workspace.query.gradient)
            check(query(c,amp_points[-1],0,1)==0,'cost only')
            check(bytes(c.core.workspace.query.packed)==packed and bytes(c.core.workspace.query.gradient)==gradient,'workspace preservation')
            bank=sub/'valid.bank.bin';check(lib.sh_save(str(bank).encode(),C.byref(c))==0,'save schema')
            restored=iq.Context();check(lib.sh_load(str(bank).encode(),C.byref(restored))==0,'load schema')
            check(bytes(restored.core.bank)==bytes(c.core.bank),'snapshot identity')
            for label,magic in [('old',b'FPSH001\0'),('other',b'SHF0001\0' if arm=='control' else b'SHC0001\0')]:
                badpath=sub/(label+'.bank.bin');badpath.write_bytes(magic+bank.read_bytes()[8:]);before=bytes(restored)
                check(lib.sh_load(str(badpath).encode(),C.byref(restored))<0 and bytes(restored)==before,'schema rejection')
            fill(c,16,16);owned=iq.evidence_identity(c);status=lib.re_refine(C.byref(c),1)
            check(status in (0,1) and iq.evidence_identity(c)==owned,'bounded refine preserves evidence')
            check(lib.re_commit(C.byref(c))==0,'post-refine commit')
            guarded=new();rr=raw(0);wrong=iq.source_id();wrong[0]^=1
            for identity,index in ((wrong,0),(sid,1)):
                before=bytes(guarded);check(lib.re_offer(C.byref(guarded),identity,index,C.byref(rr))<0 and bytes(guarded)==before,'source/order atomic')
            guarded.core.bank.next_index=guarded.inputs.next_ingress_sequence=2**64-1;before=bytes(guarded)
            check(lib.re_offer(C.byref(guarded),sid,2**64-1,C.byref(rr))<0 and bytes(guarded)==before,'counter rejection')
            fault=new();fill(fault,0,1);fault.core.bank.upper[1]=sys.float_info.max;fault.core.bank.upper[37]=sys.float_info.max
            check(lib.re_commit(C.byref(fault))<0 and not fault.core.bank.available and fault.inputs.block_count==1 and fault.core.bank.next_index==0,'partial merge latches unavailable')
            before=bytes(fault);check(lib.re_commit(C.byref(fault))<0 and bytes(fault)==before,'failed state stable')
            result['cases'].append({'arm':arm,'status':'passed','checks_so_far':result['checks']})
        check(study.sources()==bound,'sources unchanged');result['status']='passed'
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result.update(children=budget.children,CPU_s=budget.used_cpu(),
                      files={str(p.relative_to(directory)):runner.identity(p) for p in directory.rglob('*') if p.is_file()})
        runner.save(directory/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','checks','error') if k in result}))
    return int(result['status']!='passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();sys.exit(qualification(args.output.resolve()))
