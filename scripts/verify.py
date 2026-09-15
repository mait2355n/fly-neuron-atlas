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

from table_contracts import finite, validate

ROOT = Path(__file__).resolve().parents[1]


def contract_columns(entry, name):
    columns = entry.get(name, [])
    if (not isinstance(columns, list) or any(not isinstance(c, str) or not c for c in columns)
            or len(columns) != len(set(columns)) or (name == 'primary_key' and name in entry and not columns)):
        raise ValueError(f'invalid {name}: {entry["path"]}')
    return columns


def inspect_csv(path, label, failures, primary_key=(), finite_columns=()):
    """Read one table once; retain identities only when explicitly requested."""
    opener = gzip.open if path.suffix == '.gz' else open
    identities, invalid = set(), set()
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        for column in set(primary_key) | set(finite_columns):
            if column not in fields:
                invalid.add('missing contract column ' + column)
        count = 0
        for row in reader:
            count += 1
            if None in row or any(v is None for v in row.values()):
                invalid.add('malformed CSV')
                continue
            if primary_key and all(column in row for column in primary_key):
                key = tuple(row[column] for column in primary_key)
                if any(not value.strip() for value in key):
                    invalid.add('empty primary key')
                if key in identities:
                    invalid.add('duplicate primary key')
                identities.add(key)
            for column in finite_columns:
                if column in row and not finite(row[column]):
                    invalid.add('nonfinite required column ' + column)
    # At most one diagnostic per failure class/column avoids unbounded reports
    # when every generated row is invalid. All rows were still inspected.
    failures.extend(issue + ': ' + label for issue in sorted(invalid))
    return fields, count, identities


def verify_entry(root, entry, source_ids, failures):
    """Shared provenance route for original and optional generated artifacts."""
    path = root / entry['path']
    if not set(entry['source_ids']) <= source_ids:
        failures.append('unknown source id: ' + entry['path'])
    if entry.get('format') == 'json':
        obj = json.loads(path.read_text(encoding='utf-8'))
        if list(obj) != entry['top_level_keys']:
            failures.append('JSON top-level shape: ' + entry['path'])
        return
    primary_key = contract_columns(entry, 'primary_key')
    finite_columns = contract_columns(entry, 'finite_columns')
    reference = entry.get('identity_reference')
    if 'identity_reference' in entry:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError('invalid identity_reference: ' + entry['path'])
        if not primary_key:
            raise ValueError('identity_reference requires primary_key: ' + entry['path'])
    fields, count, identities = inspect_csv(path, entry['path'], failures, primary_key, finite_columns)
    if fields != entry['columns'] or count != entry['rows']:
        failures.append('table shape: ' + entry['path'])
    if reference is not None:
        _, _, expected = inspect_csv(root / reference, reference, failures, primary_key)
        if identities != expected:
            failures.append('identity reference mismatch: ' + entry['path'] + ' -> ' + reference)


def verify(root=ROOT):
    failures = []
    manifest = json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
    for e in manifest['files']:
        p = root/e['path']
        if not p.is_file() or p.is_symlink():
            failures.append('missing or symlink: '+e['path']); continue
        b = p.read_bytes()
        if len(b) != e['bytes'] or hashlib.sha256(b).hexdigest() != e['sha256']:
            failures.append('hash/size mismatch: '+e['path'])
    prov = json.loads((root/'data/provenance.json').read_text(encoding='utf-8'))
    sources = json.loads((root/'data/sources.json').read_text(encoding='utf-8'))
    source_ids = {s['id'] for s in sources['sources']}
    for e in prov['entries']:
        verify_entry(root, e, source_ids, failures)
    generated_path = root / 'data/reanalysis/PROVENANCE.json'
    generated = json.loads(generated_path.read_text(encoding='utf-8'))['entries'] if generated_path.exists() else []
    for e in generated:
        verify_entry(root, e, source_ids, failures)
    contracts = validate(root)
    failures.extend(contracts['failures'])
    for p in root.rglob('*.md'):
        if any(part in ('.git','.local','outputs','raw','.venv') for part in p.relative_to(root).parts): continue
        for raw in re.findall(r'\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
            target = raw.split('#',1)[0]
            if not target or '://' in target or target.startswith('mailto:'): continue
            if not (p.parent/unquote(target)).exists():
                failures.append(f'broken local link: {p.relative_to(root)} -> {target}')
    return {'schema_version':'fly-neuron-atlas-integrity/v1','status':'pass' if not failures else 'fail','manifest_files':len(manifest['files']),'tables':len(prov['entries']),'generated_artifacts':len(generated),'failures':failures,'table_contracts':contracts,'scope':'Checksums, CSV/JSON shapes, explicit structural/activity and declared generated-artifact contracts, source references and local Markdown link targets; upstream validity and biological conclusions are not certified.'}


if __name__ == '__main__':
    try:
        report = verify()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report['status'] == 'pass' else 1)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(json.dumps({'status':'error','message':str(exc)}), file=sys.stderr)
        sys.exit(1)
