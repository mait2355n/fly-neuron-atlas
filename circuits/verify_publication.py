"""Verify shipped files and independently count every published circuit set.

Uses only the standard library. Raw retrieval records are not shipped or verified.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def independent_summary(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    selected = set(manifest['selected_ids'])
    annotations = json.loads((manifest_path.parent / manifest['nodes_file']).read_text(encoding='utf-8'))
    nodes = {str(node['bodyId']) for node in annotations}
    counts = {name: {'edges': 0, 'weight': 0} for name in ('internal', 'incoming', 'outgoing', 'other')}
    with gzip.open(manifest_path.parent / manifest['edges_file'], 'rt', newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            pre, post = row['bodyId_pre'], row['bodyId_post']
            nodes.update((pre, post))
            name = ('internal' if pre in selected and post in selected else 'incoming'
                    if post in selected else 'outgoing' if pre in selected else 'other')
            counts[name]['edges'] += 1
            counts[name]['weight'] += int(row['weight'])
    return {'nodes': len(nodes), 'selected': len(selected), 'partition': counts,
            'edges': sum(x['edges'] for x in counts.values()),
            'weight': sum(x['weight'] for x in counts.values())}


def engine(command, path):
    run = subprocess.run([sys.executable, str(HERE / 'circuit_ops.py'), command, str(path)],
                         capture_output=True, text=True, encoding="utf-8", timeout=180)
    if run.returncode:
        raise ValueError(f'{command} failed: {run.stderr.strip()}')
    if run.stderr:
        raise ValueError(f'{command} wrote unexpected stderr')
    return json.loads(run.stdout)['result']


def main():
    publication = json.loads((HERE / 'PUBLICATION.json').read_text(encoding='utf-8'))
    checked_files, results = 0, []
    for record in publication.get('implementation_files', []):
        path = HERE / record['path']
        if path.stat().st_size != record['size_bytes'] or digest(path) != record['sha256']:
            raise ValueError('publication file hash mismatch: ' + record['path'])
        checked_files += 1
    for record in publication['sets']:
        for item in record['files']:
            path = HERE / item['path']
            if path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                raise ValueError('publication file hash mismatch: ' + item['path'])
            checked_files += 1
        manifest = HERE / record['manifest']
        inputs = engine('verify-inputs', manifest)
        inspected = engine('inspect', manifest)
        if inspected != record['expected_structure']:
            raise ValueError('original graph structure mismatch: ' + record['name'])
        independent = independent_summary(manifest)
        if independent != {k: v for k, v in inspected.items() if k != 'fingerprint'}:
            raise ValueError('independent structure count mismatch: ' + record['name'])
        results.append({'name': record['name'], 'input_verification': inputs,
                        'structure': inspected, 'independent_counts_match': True})
    print(json.dumps({'status': 'ok', 'publication_files_checked': checked_files,
                      'sets_checked': len(results), 'results': results,
                      'archival_sources_verified': False,
                      'original_retrieval_replay_available': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}), file=sys.stderr)
        raise SystemExit(2)
