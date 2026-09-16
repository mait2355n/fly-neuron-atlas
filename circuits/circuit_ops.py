"""Provenance-preserving static circuit operations. No neural dynamics are inferred."""
from __future__ import annotations
import argparse
import copy
import csv
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
import zlib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ('weight', 'weightHP', 'weightHR')
EDGE_FIELDS = ('bodyId_pre', 'bodyId_post', *WEIGHTS, 'source_refs')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def identifier(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or int(value) < 1 or str(int(value)) != value:
        raise ValueError('bodyId must be a canonical positive decimal string')
    return value


def weight(value, nullable=False):
    if value is None or value == '':
        if nullable:
            return None
        raise ValueError('weight is required')
    if isinstance(value, bool):
        raise ValueError('boolean weight')
    if isinstance(value, str):
        if not value.isascii() or not value.isdecimal():
            raise ValueError('noninteger weight')
        value = int(value)
    if not isinstance(value, int) or value < 0:
        raise ValueError('negative or noninteger weight')
    return value


def flag(value):
    if value is None or value == '':
        return None
    if value is True or value == 'true':
        return True
    if value is False or value == 'false':
        return False
    raise ValueError('invalid neuron flag')


@dataclass
class Graph:
    snapshot: dict
    nodes: dict
    edges: dict
    selected_ids: tuple
    coverage: dict


def validate(graph):
    for key in ('dataset', 'uuid', 'tag', 'latestMutationId'):
        if key not in graph.snapshot or graph.snapshot[key] in ('', None):
            raise ValueError('missing snapshot field: ' + key)
    if len(set(graph.selected_ids)) != len(graph.selected_ids) or not set(graph.selected_ids) <= graph.nodes.keys():
        raise ValueError('selected identity missing or duplicated')
    prefix = graph.snapshot['dataset'] + ':'
    for key, node in graph.nodes.items():
        if node.get('entity_id') != key:
            raise ValueError('node identity mismatch')
        reference = node.get('ref')
        if not isinstance(reference, str) or '・' not in reference or reference.rsplit('・', 1)[1] != key:
            raise ValueError('compact ref identity mismatch')
        if key.startswith('clone:'):
            uuid.UUID(key.removeprefix('clone:'))
            if node.get('derived_from') != prefix + identifier(node.get('bodyId')):
                raise ValueError('clone biological lineage mismatch')
        elif key != prefix + identifier(node.get('bodyId')):
            raise ValueError('node namespace mismatch')
    for (pre, post), edge in graph.edges.items():
        if pre not in graph.nodes or post not in graph.nodes:
            raise ValueError('dangling edge')
        if not set(WEIGHTS) <= edge.keys():
            raise ValueError('weight fields missing')
        for name in WEIGHTS:
            weight(edge.get(name), name != 'weight')
        if not isinstance(edge.get('source_refs'), list) or not edge['source_refs'] or not all(isinstance(x,str) and x for x in edge['source_refs']):
            raise ValueError('edge source provenance missing')
    return graph


def fingerprint(graph):
    validate(graph)
    h = hashlib.sha256()
    h.update(encoded({'snapshot':graph.snapshot, 'selected_ids':sorted(graph.selected_ids), 'coverage':graph.coverage}).encode())
    for key in sorted(graph.nodes):
        h.update(('\nN' + encoded([key, graph.nodes[key]])).encode())
    for key in sorted(graph.edges):
        edge = graph.edges[key]
        h.update(('\nE' + encoded([*key, *[edge[n] for n in WEIGHTS], sorted(set(edge['source_refs']))])).encode())
    return h.hexdigest()


def verify_inputs(manifest_path):
    path = Path(manifest_path)
    manifest = load_json(path)
    sources = load_json(path.parent / manifest['sources_file'])
    publication = manifest.get('publication')
    if publication is not None:
        if publication.get('schema_version') != 'circuit-published-inputs/v1':
            raise ValueError('unknown publication input schema')
        if publication.get('archival_sources_verified') is not False:
            raise ValueError('publication must not claim archival source verification')
        names = [manifest[key] for key in ('nodes_file', 'edges_file', 'sources_file')]
        if len(set(names)) != 3 or set(publication['files']) != set(names):
            raise ValueError('published input digest inventory mismatch')
        for name in names:
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError('published input filename must be local')
            record = publication['files'][name]
            p = path.parent / name
            if p.stat().st_size != record['size_bytes'] or file_hash(p) != record['sha256']:
                raise ValueError('published input hash mismatch: ' + name)
    seen = set()
    for source in sources:
        if source['id'] in seen:
            raise ValueError('duplicate source id')
        seen.add(source['id'])
        if publication is not None:
            if source.get('availability') != 'archival_not_shipped' or source.get('path_basis') != 'original_research_root':
                raise ValueError('published source lacks explicit archival availability')
            if (not isinstance(source['sha256'], str) or len(source['sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in source['sha256'])
                    or type(source['size_bytes']) is not int or source['size_bytes'] < 0):
                raise ValueError('invalid archival source digest record')
            continue
        p = ROOT / source['path']
        if p.stat().st_size != source['size_bytes'] or file_hash(p) != source['sha256']:
            raise ValueError('source hash mismatch: ' + source['path'])
    if publication is not None:
        return {'verification_scope':'published_normalized_files', 'published_files_checked':len(names),
                'sources_checked':0, 'archival_source_records':len(sources),
                'archival_sources_verified':False, 'original_retrieval_replay_available':False}
    return {'verification_scope':'available_original_sources', 'sources_checked':len(sources)}


def load_source(manifest_path):
    path = Path(manifest_path)
    m = load_json(path)
    if m.get('schema_version') != 'circuit-source-set/v1':
        raise ValueError('unknown source schema')
    snap = {'dataset':m['dataset'], **{k:m['snapshot'][k] for k in ('uuid','tag','latestMutationId')}}
    snap['latestMutationId'] = str(snap['latestMutationId'])
    selected_raw = [identifier(x) for x in m['selected_ids']]
    if len(set(selected_raw)) != len(selected_raw):
        raise ValueError('duplicate selected bodyId')
    prefix = m['dataset'] + ':'
    selected = tuple(prefix + x for x in selected_raw)
    selected_set = set(selected)
    src = load_json(path.parent / m['sources_file'])
    if len({x['id'] for x in src}) != len(src):
        raise ValueError('duplicate source identifier')
    refs = {x['id']:x['path'] + '#sha256=' + x['sha256'] for x in src}
    nodes = {}
    annotations = load_json(path.parent / m['nodes_file'])
    for original in annotations:
        node = copy.deepcopy(original)
        body = identifier(str(node['bodyId']))
        key = prefix + body
        node.update(bodyId=body, entity_id=key)
        if not node.get('ref'):
            node['ref'] = str(node.get('type') or 'untyped') + '・' + key
        if key in nodes:
            raise ValueError('duplicate node annotation')
        nodes[key] = node
    if not set(selected) <= nodes.keys():
        raise ValueError('selected node annotation missing')
    edges = {}
    with gzip.open(path.parent / m['edges_file'], 'rt', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            pre, post = prefix + identifier(row['bodyId_pre']), prefix + identifier(row['bodyId_post'])
            if pre not in selected_set and post not in selected_set:
                raise ValueError('source includes an edge outside the selected incident scope')
            for key, which in ((pre,'pre'), (post,'post')):
                is_neuron = flag(row.get(which + '_is_neuron'))
                if key not in nodes:
                    nodes[key] = {'bodyId':key.removeprefix(prefix), 'entity_id':key, 'is_neuron':is_neuron, 'type':None, 'ref':'untyped・' + key}
                elif is_neuron is not None:
                    prior = nodes[key].get('is_neuron')
                    if prior is not None and flag(prior) != is_neuron:
                        raise ValueError('conflicting neuron label: ' + key)
                    nodes[key]['is_neuron'] = is_neuron
            source_ids = json.loads(row['source_ids'])
            if not isinstance(source_ids, list) or not source_ids or any(x not in refs for x in source_ids):
                raise ValueError('unresolved edge source')
            edge = {name:weight(row[name], name != 'weight') for name in WEIGHTS}
            edge['source_refs'] = sorted({refs[x] for x in source_ids})
            pair = (pre, post)
            if pair in edges:
                raise ValueError('source edges are not unique')
            edges[pair] = edge
    coverage = {'source':m['coverage'], 'representation':'all_saved_incident', 'complete_biological_system':False, 'notes':m.get('notes',[])}
    return validate(Graph(snap, nodes, edges, selected, coverage))


def cut(graph, selected_entity_ids):
    validate(graph)
    selected = set(selected_entity_ids)
    if not selected <= graph.nodes.keys():
        raise ValueError('cut selects unknown node')
    inside_edges, boundary_edges = {}, {}
    for key, edge in graph.edges.items():
        (inside_edges if key[0] in selected and key[1] in selected else boundary_edges)[key] = copy.deepcopy(edge)
    inside = Graph(copy.deepcopy(graph.snapshot), {k:copy.deepcopy(graph.nodes[k]) for k in selected}, inside_edges, tuple(sorted(selected)), {**copy.deepcopy(graph.coverage), 'representation':'induced_only'})
    boundary = Graph(copy.deepcopy(graph.snapshot), copy.deepcopy(graph.nodes), boundary_edges, graph.selected_ids, {**copy.deepcopy(graph.coverage), 'representation':'boundary_and_remainder'})
    return {'inside':inside, 'boundary':boundary, 'selected_ids':sorted(selected), 'original_selected_ids':graph.selected_ids, 'original_coverage':copy.deepcopy(graph.coverage), 'original_fingerprint':fingerprint(graph), 'snapshot':copy.deepcopy(graph.snapshot)}


def merge(graphs):
    if not graphs:
        raise ValueError('empty merge')
    snapshot = graphs[0].snapshot
    nodes, edges, selected, coverages = {}, {}, set(), []
    for graph in graphs:
        validate(graph)
        if graph.snapshot != snapshot:
            raise ValueError('snapshot mismatch')
        for key, node in graph.nodes.items():
            if key in nodes and nodes[key] != node:
                raise ValueError('node annotation conflict: ' + key)
            nodes[key] = copy.deepcopy(node)
        for key, edge in graph.edges.items():
            if key in edges:
                if any(edges[key][name] != edge[name] for name in WEIGHTS):
                    raise ValueError('edge weight conflict')
                edges[key]['source_refs'] = sorted(set(edges[key]['source_refs']) | set(edge['source_refs']))
            else:
                edges[key] = {**edge, 'source_refs':list(edge['source_refs'])}
        selected.update(graph.selected_ids)
        if graph.coverage not in coverages:
            coverages.append(copy.deepcopy(graph.coverage))
    coverage = {'representation':'union', 'inputs':coverages, 'complete_biological_system':False}
    return Graph(copy.deepcopy(snapshot), nodes, edges, tuple(sorted(selected)), coverage)


def reconnect(record):
    if record['inside'].snapshot != record['snapshot'] or record['boundary'].snapshot != record['snapshot']:
        raise ValueError('cut snapshot changed')
    if set(record['inside'].edges) & set(record['boundary'].edges):
        raise ValueError('cut partitions overlap')
    out = merge([record['inside'], record['boundary']])
    out.selected_ids = tuple(record['original_selected_ids'])
    out.coverage = copy.deepcopy(record['original_coverage'])
    if fingerprint(out) != record['original_fingerprint']:
        raise ValueError('reconnection does not restore original structure')
    return out


def edge_record(key, edge):
    return {'pre':key[0], 'post':key[1], **copy.deepcopy(edge)}


def clone_node(graph, entity_id, clone_tag):
    validate(graph)
    if entity_id not in graph.nodes or entity_id.startswith('clone:') or not clone_tag:
        raise ValueError('invalid clone source or tag')
    clone_id = 'clone:' + str(uuid.uuid5(uuid.NAMESPACE_URL, encoded([graph.snapshot, entity_id, clone_tag])))
    if clone_id in graph.nodes:
        raise ValueError('clone tag already applied')
    nodes = copy.deepcopy(graph.nodes)
    node = copy.deepcopy(graph.nodes[entity_id])
    node.update(entity_id=clone_id, ref=str(node.get('type') or 'untyped') + '・' + clone_id, derived_from=entity_id, clone_tag=clone_tag, biological_instance=False)
    nodes[clone_id] = node
    edges = copy.deepcopy(graph.edges)
    additions = []
    for (pre, post), edge in graph.edges.items():
        if entity_id not in (pre, post):
            continue
        pair = (clone_id if pre == entity_id else pre, clone_id if post == entity_id else post)
        edges[pair] = {**edge, 'source_refs':list(edge['source_refs'])}
        additions.append(edge_record(pair, edges[pair]))
    out = Graph(copy.deepcopy(graph.snapshot), nodes, edges, (*graph.selected_ids, clone_id) if entity_id in graph.selected_ids else graph.selected_ids, {**copy.deepcopy(graph.coverage), 'representation':'artificial_clone'})
    change = {'operation':'clone_full_incident_neighborhood', 'source':entity_id, 'clone':clone_id, 'clone_tag':clone_tag, 'removed':[], 'added_nodes':[node], 'added_edges':additions, 'biological_function_verified':False}
    return validate(out), change


def drop_edges(graph, predicate):
    removed = [edge_record(k,e) for k,e in graph.edges.items() if predicate(k,e)]
    remove_keys = {(x['pre'],x['post']) for x in removed}
    out = Graph(copy.deepcopy(graph.snapshot), copy.deepcopy(graph.nodes), {k:copy.deepcopy(e) for k,e in graph.edges.items() if k not in remove_keys}, graph.selected_ids, {**copy.deepcopy(graph.coverage), 'representation':'edges_removed'})
    return out, {'operation':'drop_edges', 'removed':removed, 'added_edges':[], 'biological_function_verified':False}


def swap_targets(graph, key1, key2):
    if key1 not in graph.edges or key2 not in graph.edges or len(set((*key1,*key2))) != 4:
        raise ValueError('swap requires two edges and four distinct endpoints')
    new1, new2 = (key1[0],key2[1]), (key2[0],key1[1])
    if new1 in graph.edges or new2 in graph.edges:
        raise ValueError('swap collides with existing edge')
    edges = copy.deepcopy(graph.edges)
    e1, e2 = edges.pop(key1), edges.pop(key2)
    edges[new1], edges[new2] = e1, e2
    out = Graph(copy.deepcopy(graph.snapshot), copy.deepcopy(graph.nodes), edges, graph.selected_ids, {**copy.deepcopy(graph.coverage), 'representation':'targets_swapped'})
    return out, {'operation':'swap_targets', 'removed':[edge_record(key1,e1),edge_record(key2,e2)], 'added_edges':[edge_record(new1,e1),edge_record(new2,e2)], 'preserves':'unweighted directed degrees and each source outgoing weight; not target weighted input', 'biological_function_verified':False}


def write_graph(graph, outdir):
    validate(graph)
    out = Path(outdir)
    if out.exists():
        raise ValueError('output already exists')
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.circuit-', dir=out.parent))
    try:
        dump_json(stage / 'graph.json', {'schema_version':'circuit-graph/v1', 'snapshot':graph.snapshot, 'nodes':graph.nodes, 'selected_ids':list(graph.selected_ids), 'coverage':graph.coverage})
        with (stage / 'edges.csv.gz').open('wb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
                with io.TextIOWrapper(compressed, newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=EDGE_FIELDS)
                    writer.writeheader()
                    for (pre,post), edge in sorted(graph.edges.items()):
                        writer.writerow({'bodyId_pre':pre, 'bodyId_post':post, **{n:edge[n] for n in WEIGHTS}, 'source_refs':encoded(sorted(set(edge['source_refs'])))})
        dump_json(stage / 'manifest.json', {'schema_version':'circuit-export/v1', 'fingerprint':fingerprint(graph), 'files':{n:file_hash(stage/n) for n in ('graph.json','edges.csv.gz')}})
        stage.rename(out)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def read_graph(outdir):
    path = Path(outdir)
    manifest = load_json(path / 'manifest.json')
    if manifest.get('schema_version') != 'circuit-export/v1' or set(manifest['files']) != {'graph.json','edges.csv.gz'}:
        raise ValueError('unknown export manifest')
    for name, digest in manifest['files'].items():
        if file_hash(path/name) != digest:
            raise ValueError('export file hash mismatch: ' + name)
    m = load_json(path / 'graph.json')
    if m.get('schema_version') != 'circuit-graph/v1':
        raise ValueError('unknown graph schema')
    edges = {}
    with gzip.open(path / 'edges.csv.gz','rt',newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = row['bodyId_pre'],row['bodyId_post']
            if key in edges:
                raise ValueError('duplicate exported edge')
            edges[key] = {**{n:weight(row[n],n!='weight') for n in WEIGHTS}, 'source_refs':json.loads(row['source_refs'])}
    graph = Graph(m['snapshot'],m['nodes'],edges,tuple(m['selected_ids']),m['coverage'])
    if fingerprint(graph) != manifest['fingerprint']:
        raise ValueError('export semantic fingerprint mismatch')
    return graph


def stats(graph):
    selected = set(graph.selected_ids)
    counts = {name:{'edges':0,'weight':0} for name in ('internal','incoming','outgoing','other')}
    for (pre,post), edge in graph.edges.items():
        role = 'internal' if pre in selected and post in selected else 'incoming' if post in selected else 'outgoing' if pre in selected else 'other'
        counts[role]['edges'] += 1
        counts[role]['weight'] += edge['weight']
    return {'nodes':len(graph.nodes),'selected':len(selected),'edges':len(graph.edges),'weight':sum(e['weight'] for e in graph.edges.values()),'partition':counts,'fingerprint':fingerprint(graph)}


def demo(manifest_path, outdir):
    engine_sha256 = file_hash(Path(__file__))
    started_at = datetime.now(timezone.utc).isoformat()
    out = Path(outdir)
    if out.exists():
        raise ValueError('demo output already exists')
    verify = verify_inputs(manifest_path)
    graph = load_source(manifest_path)
    before = stats(graph)
    record = cut(graph, graph.selected_ids)
    restored = reconnect(record)
    out.mkdir(parents=True)
    write_graph(record['inside'],out/'inside')
    write_graph(record['boundary'],out/'boundary')
    write_graph(restored,out/'reconnected')
    if fingerprint(read_graph(out/'reconnected')) != before['fingerprint']:
        raise ValueError('persisted reconnection mismatch')
    dump_json(out/'cut.json',{k:v for k,v in record.items() if k not in ('inside','boundary')})
    selected = set(graph.selected_ids)
    upstream = {}
    for pre,post in graph.edges:
        if pre not in selected and post in selected:
            upstream.setdefault(pre,set()).add(post)
    shared = {key:sorted(targets) for key,targets in upstream.items() if len(targets)>1}
    dump_json(out/'shared_inputs.json',shared)
    comparisons = [{'condition':'original','result':before},{'condition':'internal_only','result':stats(record['inside'])},{'condition':'reconnected','result':stats(restored)}]
    changed, edits = drop_edges(graph,lambda key,edge:key[0] in selected and key[1] in selected and edge['weight']<10)
    edits.update(reason='explicit sensitivity condition: remove only selected-internal edges below weight 10',base_fingerprint=before['fingerprint'],result_fingerprint=fingerprint(changed))
    write_graph(changed,out/'threshold10')
    dump_json(out/'threshold10_changes.json',edits)
    comparisons.append({'condition':'internal_threshold10','result':stats(changed)})
    del changed, edits
    if shared:
        known_neurons = [key for key in shared if graph.nodes[key].get('is_neuron') is True]
        key = min(known_neurons or shared, key=lambda key:(-len(shared[key]),key))
        cloned, edits = clone_node(graph,key,'shared-input-copy')
        edits.update(reason='duplicate one external node shared by several selected targets; preserve original and copy full incident neighborhood',base_fingerprint=before['fingerprint'],result_fingerprint=fingerprint(cloned))
        write_graph(cloned,out/'shared_clone')
        dump_json(out/'shared_clone_changes.json',edits)
        comparisons.append({'condition':'shared_input_duplicated','result':stats(cloned)})
        del cloned, edits
    keys = sorted(record['inside'].edges)
    pair = None
    for i,a in enumerate(keys):
        for b in keys[i+1:]:
            if len(set((*a,*b)))==4 and (a[0],b[1]) not in graph.edges and (b[0],a[1]) not in graph.edges:
                pair = a,b
                break
        if pair:
            break
    if pair:
        swapped, edits = swap_targets(graph,*pair)
        edits.update(reason='two-edge target exchange as an explicitly artificial wiring comparison',base_fingerprint=before['fingerprint'],result_fingerprint=fingerprint(swapped))
        write_graph(swapped,out/'target_swap')
        dump_json(out/'target_swap_changes.json',edits)
        comparisons.append({'condition':'two_targets_swapped','result':stats(swapped)})
        del swapped, edits
    summary = {'schema_version':'circuit-demo/v1','status':'complete','started_at':started_at,'finished_at':datetime.now(timezone.utc).isoformat(),'engine_sha256':engine_sha256,'source_manifest':str(Path(manifest_path).resolve().relative_to(ROOT)),'source_manifest_sha256':file_hash(manifest_path),'verified_inputs':verify,'shared_external_input_ids':len(shared),'roundtrip_exact':before['fingerprint']==fingerprint(restored),'conditions':comparisons,'unmeasured':['neural firing','effective signs and delays','plasticity','behavior','artificial subject utility'],'two_target_swap_available':pair is not None}
    dump_json(out/'RESULT.json',summary)
    return summary


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main():
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('inspect','verify-inputs','demo','verify-graph'))
    parser.add_argument('path')
    parser.add_argument('--out')
    try:
        args = parser.parse_args()
        if args.command == 'inspect':
            result = stats(load_source(args.path))
        elif args.command == 'verify-inputs':
            result = verify_inputs(args.path)
        elif args.command == 'verify-graph':
            result = stats(read_graph(args.path))
        else:
            if not args.out:
                raise ValueError('demo requires --out')
            result = demo(args.path,args.out)
        print(encoded({'status':'ok','result':result}))
        return 0
    except (ValueError,KeyError,OSError,TypeError,EOFError,zlib.error) as exc:
        print(encoded({'status':'error','error':{'type':type(exc).__name__,'message':str(exc)}}),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
