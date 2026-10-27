"""Shared finite-step reservations around unchanged qualified arithmetic."""
import json
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'joint_health_posterior_001'))
import model
import smc
import posterior
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner


def save(path,value):
    def convert(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    # Keep the exclusive, fsynced repository receipt writer.
    runner.save(path,json.loads(json.dumps(value,default=convert,allow_nan=False)))


class Work:
    def __init__(self,limit):
        model.k.require(type(limit) is int and limit>=0,'invalid_input','work limit')
        self.limit=limit
        self.steps=self.paths=self.calls=self.denied=0

    def reserve(self,paths,records):
        model.k.require(type(paths) is int and paths>=0 and type(records) is int and records>=0,
                        'invalid_input','work reservation')
        requested=paths*records
        if requested>self.limit-self.steps:
            self.denied+=1
            raise model.k.ModelError('resource_limit','prospective shared physical-step cap')
        self.steps+=requested
        self.paths+=paths
        self.calls+=1

    def report(self):
        return dict(limit=self.limit,conservative_steps=self.steps,evaluated_paths=self.paths,
                    admitted_batches=self.calls,denied_batches=self.denied)


class Target(model.Target):
    def __init__(self,records,profile,work,source_id='fixture',max_paths=8_000_000):
        super().__init__(records,profile,source_id,max_paths)
        self.work=work

    def evaluate(self,u):
        # Reserve before invoking any inherited model computation. Parent prior
        # sampling calls this override, so its validation work is covered too.
        self.work.reserve(len(u),len(self.records))
        return super().evaluate(u)


def read_records(path):
    document=json.loads(path.read_text())
    rows=tuple(model.k.Record(**r) for r in document['records'])
    return document['source_id'],rows
