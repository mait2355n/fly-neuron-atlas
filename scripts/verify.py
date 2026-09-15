#!/usr/bin/env python3
"""Read-only file-integrity and table-contract validation. Python 3.10+."""
import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    failures = []
    manifest = json.loads((root/'MANIFEST.json').read_text())
    for e in manifest['files']:
        p = root/e['path']
        if not p.is_file() or p.is_symlink():
            failures.append('missing or symlink: '+e['path']); continue
        b = p.read_bytes()
        if len(b) != e['bytes'] or hashlib.sha256(b).hexdigest() != e['sha256']:
            failures.append('hash/size mismatch: '+e['path'])
    prov = json.loads((root/'data/provenance.json').read_text())
    sources = json.loads((root/'data/sources.json').read_text())
    source_ids = {s['id'] for s in sources['sources']}
    for e in prov['entries']:
        p = root/e['path']
        if e.get('format') == 'json':
            obj = json.loads(p.read_text())
            if list(obj) != e['top_level_keys']:
                failures.append('JSON top-level shape: '+e['path'])
            if not set(e['source_ids']) <= source_ids:
                failures.append('unknown source id: '+e['path'])
            continue
        opener = gzip.open if p.suffix == '.gz' else open
        with opener(p, 'rt', encoding='utf-8', newline='') as f:
            r = csv.DictReader(f)
            n = 0
            for row in r:
                n += 1
                if None in row or any(v is None for v in row.values()):
                    failures.append('malformed CSV: '+e['path']); break
            if r.fieldnames != e['columns'] or n != e['rows']:
                failures.append('table shape: '+e['path'])
        if not set(e['source_ids']) <= source_ids:
            failures.append('unknown source id: '+e['path'])
    for p in root.rglob('*.md'):
        if any(part in ('.git','.local','outputs','raw','.venv') for part in p.relative_to(root).parts): continue
        for raw in re.findall(r'\]\(([^)]+)\)', p.read_text()):
            target = raw.split('#',1)[0]
            if not target or '://' in target or target.startswith('mailto:'): continue
            if not (p.parent/unquote(target)).exists():
                failures.append(f'broken local link: {p.relative_to(root)} -> {target}')
    return {'schema_version':'fly-neuron-atlas-integrity/v1','status':'pass' if not failures else 'fail','manifest_files':len(manifest['files']),'tables':len(prov['entries']),'failures':failures,'scope':'Checksums, CSV shapes, source references and local Markdown link targets; upstream validity and biological conclusions are not certified.'}


if __name__ == '__main__':
    try:
        report = verify()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report['status'] == 'pass' else 1)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(json.dumps({'status':'error','message':str(exc)}), file=sys.stderr)
        sys.exit(1)
