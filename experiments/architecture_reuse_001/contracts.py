"""Static architecture checks, not a runtime executive or physical proof."""
import json
from experiments.foster_campaign_001.backend import ROOT


def load():
    return json.loads((ROOT/'specifications/architecture_reuse_001/graph.json').read_text())


def validate(graph):
    # Ordered dependency coverage is the premise required before caching a node.
    leaves=graph['leaves']
    if len(leaves)!=len(set(leaves)):raise ValueError('duplicate leaf')
    dependencies={leaf:{leaf} for leaf in leaves}
    for node in graph['nodes']:
        if node['id'] in dependencies:raise ValueError('duplicate node')
        if not node['deps'] or any(d not in dependencies for d in node['deps']):
            raise ValueError('missing dependency or non-topological order')
        full=set().union(*(dependencies[d] for d in node['deps']))
        if 'cache_key' in node and set(node['cache_key'])!=full:
            raise ValueError('incomplete or extraneous cache dependency')
        dependencies[node['id']]=full
    columns=graph['columns'];entries=graph['coefficient_entries']
    expected={(i,j):sorted(set(columns[i]['shape_dependencies']+columns[j]['shape_dependencies']))
              for i in range(len(columns)) for j in range(i,len(columns))}
    actual={(e['i'],e['j']):e['shape_dependencies'] for e in entries}
    if len(actual)!=len(entries) or actual!=expected:raise ValueError('joint coefficient dependency missing')
    return dependencies
