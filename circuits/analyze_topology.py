"""Static selected-internal reachability under explicit weight thresholds."""
import csv
import argparse
import gzip
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def component_sizes(nodes, edges):
    adjacency = {n:[] for n in nodes}
    reverse = {n:[] for n in nodes}
    for a,b in edges:
        adjacency[a].append(b)
        reverse[b].append(a)
    seen, order = set(), []
    for start in nodes:
        if start in seen:
            continue
        stack = [(start,False)]
        while stack:
            node, done = stack.pop()
            if done:
                order.append(node)
                continue
            if node in seen:
                continue
            seen.add(node)
            stack.append((node,True))
            stack.extend((other,False) for other in adjacency[node] if other not in seen)
    seen, sizes = set(), []
    for start in reversed(order):
        if start in seen:
            continue
        count, stack = 0, [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            count += 1
            stack.extend(other for other in reverse[node] if other not in seen)
        sizes.append(count)
    return sorted(sizes, reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='optional JSON output; default is stdout only')
    args = parser.parse_args()
    records = []
    for source in sorted((HERE/'inputs').glob('*/*/set_manifest.json')):
        manifest = json.loads(source.read_text(encoding='utf-8'))
        ids = set(manifest['selected_ids'])
        edges = {}
        with gzip.open(source.parent/manifest['edges_file'],'rt', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['bodyId_pre'] in ids and row['bodyId_post'] in ids:
                    edges[(row['bodyId_pre'],row['bodyId_post'])] = int(row['weight'])
        conditions = []
        for threshold in (1,3,5,10):
            kept = {key:value for key,value in edges.items() if value >= threshold}
            sizes = component_sizes(ids,kept)
            conditions.append({'threshold':threshold, 'edges':len(kept), 'weight':sum(kept.values()), 'largest_strong_component':max(sizes,default=0), 'component_sizes':sizes, 'reciprocal_pairs':sum(1 for a,b in kept if a<b and (b,a) in kept)})
        records.append({'set':manifest['name'],'nodes':len(ids),'conditions':conditions})
    result = {'method':'independent iterative Kosaraju on saved selected-internal directed edges', 'limits':'Static reachability only; no neural dynamics or functional capacity implied','results':records}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
