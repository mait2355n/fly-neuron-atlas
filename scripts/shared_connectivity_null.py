#!/usr/bin/env python3
"""Exploratory degree-preserving comparison for shared motor targets.

Uses only the included snapshot; stdlib, no network. This conditional graph
comparison is not a test of physiological coordination or causation.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def group_counts(edges, groups):
    targets = defaultdict(set)
    for pre, post in edges:
        targets[pre].add(groups[post])
    return {pre: len(g) for pre, g in targets.items()}


def rewire(edges, rng, attempts):
    """Symmetric double-edge proposals, including rejected self-transitions.

    Preserve both degree sequences and a simple directed bipartite graph.
    A finite chain is not asserted to sample the null ensemble uniformly.
    """
    result = list(edges)
    present = set(edges)
    if len(result) != len(present):
        raise ValueError('duplicate edge in null-model input')
    if len(result) < 2:
        raise ValueError('at least two edges are required')
    accepted = 0
    for _ in range(attempts):
        i, j = rng.sample(range(len(result)), 2)
        a, b = result[i]
        c, d = result[j]
        if a == c or b == d or (a, d) in present or (c, b) in present:
            continue
        present.remove((a, b)); present.remove((c, d))
        present.add((a, d)); present.add((c, b))
        result[i], result[j] = (a, d), (c, b)
        accepted += 1
    return result, accepted


def run(root, threshold, replicates, attempts_per_edge, seed):
    d = root / 'data'
    motors = {r['bodyId'] for r in read_csv(d / 'motor_atlas.csv')}
    groups = {r['bodyId']: r['group_id'] for r in read_csv(d / 'motor_groups.csv')}
    edges = [(r['bodyId_pre'], r['bodyId_post'])
             for r in read_csv(d / 'connectivity/motor_inputs.csv.gz')
             if int(r['weight']) >= threshold and r['bodyId_post'] in groups
             and r['preIsNeuron'] == 'True' and r['bodyId_pre'] not in motors]
    observed = group_counts(edges, groups)
    source_degree = Counter(a for a, _ in edges)
    target_degree = Counter(b for _, b in edges)
    observed_shared = sum(n >= 2 for n in observed.values())
    trials, per_cell = [], defaultdict(list)
    for replicate in range(replicates):
        # Every chain starts at the observed graph; seeds and chain length are explicit.
        rewired, accepted = rewire(edges, random.Random(seed + replicate), len(edges) * attempts_per_edge)
        preserved = (Counter(a for a, _ in rewired) == source_degree
                     and Counter(b for _, b in rewired) == target_degree
                     and len(set(rewired)) == len(edges))
        if not preserved:
            raise ValueError('degree/simple-graph invariant failed')
        counts = group_counts(rewired, groups)
        for pre, count in counts.items(): per_cell[pre].append(count)
        trials.append({'replicate':replicate, 'seed':seed + replicate,
                       'attempts':len(edges) * attempts_per_edge, 'accepted_swaps':accepted,
                       'shared_candidates':sum(n >= 2 for n in counts.values()),
                       'degree_invariants':preserved})
    null_counts = [r['shared_candidates'] for r in trials]
    report = {
        'schema_version':'fly-neuron-atlas-shared-null/v1', 'status':'exploratory',
        'dataset':json.loads((d/'snapshot.json').read_text(encoding='utf-8'))['dataset'],
        'threshold':threshold, 'source_neurons':len(source_degree), 'selected_motor_neurons':len(groups),
        'target_groups':len(set(groups.values())), 'eligible_edges':len(edges),
        'replicates':replicates, 'attempts_per_edge':attempts_per_edge, 'seed':seed,
        'observed_shared_candidates':observed_shared,
        'null_shared_mean':statistics.mean(null_counts), 'null_shared_min':min(null_counts),
        'null_shared_max':max(null_counts),
        'descriptive_upper_tail_fraction':sum(n >= observed_shared for n in null_counts)/replicates,
        'preserved':['binary degree of each source neuron at the threshold',
                     'binary degree of each target motor neuron at the threshold',
                     'motor-to-group membership and group cell counts', 'edge count and absence of duplicate edges'],
        'not_preserved':['edge weights', 'spatial geometry', 'cell type matching', 'anatomical wiring constraints'],
        'limitations':['Finite swap chains; mixing/uniform sampling is not established.',
                       'Replicates restart from the observed graph, not biological replicates.',
                       'Conditional graph comparison does not establish causal coordination.',
                       'Per-cell summaries are exploratory, not multiplicity-corrected significance tests.'],
        'input_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [d/'motor_atlas.csv',d/'motor_groups.csv',d/'connectivity/motor_inputs.csv.gz']},
        'trials':trials,
    }
    cells = [{'bodyId':pre,'threshold_degree':source_degree[pre],
              'observed_target_groups':observed[pre], 'null_group_mean':statistics.mean(values),
              'null_group_min':min(values),'null_group_max':max(values),
              'descriptive_upper_tail_fraction':sum(n >= observed[pre] for n in values)/replicates}
             for pre, values in sorted(per_cell.items())]
    return report, cells


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--threshold',type=int,default=10)
    ap.add_argument('--replicates',type=int,default=32)
    ap.add_argument('--attempts-per-edge',type=int,default=10)
    ap.add_argument('--seed',type=int,default=20260915)
    ap.add_argument('--output',type=Path,required=True)
    args = ap.parse_args()
    if min(args.threshold,args.attempts_per_edge) < 1 or args.replicates < 2:
        ap.error('positive threshold/attempt count and at least two replicates required')
    out = args.output.resolve()
    if out == ROOT or any(out == ROOT/p or ROOT/p in out.parents for p in ('data','scripts','docs','tests','licenses','.git')):
        ap.error('use a new .local or external output directory')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        ap.error('output must be a new or empty directory')
    report, cells = run(ROOT,args.threshold,args.replicates,args.attempts_per_edge,args.seed)
    out.mkdir(parents=True,exist_ok=True)
    (out/'RUN.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    with (out/'per_cell.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(cells[0]));writer.writeheader();writer.writerows(cells)
    print(json.dumps({k:v for k,v in report.items() if k != 'trials'},indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
