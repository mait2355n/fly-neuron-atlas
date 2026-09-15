#!/usr/bin/env python3
"""Optional raw-voltage rerun with explicit download/output paths.

Example: python scripts/reanalyze_ephys.py --fly a2_d_08 --download \
  --raw-dir .local/raw --output .local/ephys
Requires requirements-ephys.txt. Writes only to --raw-dir and --output.
Selected raw files must match the published size and MD5 before analysis.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            md5.update(b); sha.update(b)
    return md5.hexdigest(), sha.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fly', help='One record label; omit for all 23')
    ap.add_argument('--list', action='store_true', help='Print selected metadata and exit without importing numerical libraries')
    ap.add_argument('--download', action='store_true', help='Download missing selected raw files from Harvard Dataverse')
    ap.add_argument('--raw-dir', type=Path, default=ROOT/'.local/raw')
    ap.add_argument('--output', type=Path, default=ROOT/'.local/ephys')
    args = ap.parse_args()
    manifest = json.loads((ROOT/'data/activity/download_manifest.json').read_text())
    selected = [e for e in manifest['files'] if not args.fly or e['fly'] == args.fly]
    if not selected: ap.error('unknown --fly record label')
    if args.list:
        print(json.dumps({'selected':selected,'total_bytes':sum(e['bytes'] for e in selected)},indent=2)); return 0
    raw, output = args.raw_dir.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        ap.error('--output must be a new or empty directory; select another path to preserve previous results')
    for path in (raw, output):
        if path == ROOT or any(path == ROOT/p or ROOT/p in path.parents for p in ('data','docs','scripts','licenses','.git')):
            ap.error('output/raw path overlaps published files; use .local or an external directory')
        path.mkdir(parents=True, exist_ok=True)
    import ephys_core as core
    core.RAW, core.B = raw, output
    results = [[],[],[],[],[]]
    errors = []
    source_hashes = []
    core.selftest()
    for e in selected:
        p = raw/e['filename']
        try:
            receipt_path = p.with_suffix(p.suffix+'.receipt.json')
            if p.is_symlink() or receipt_path.is_symlink():
                raise ValueError('raw file or receipt is a symlink: '+e['fly'])
            if not p.exists() and args.download:
                tmp = p.with_suffix(p.suffix+'.part')
                with urllib.request.urlopen(e['url'], timeout=120) as response, tmp.open('xb') as target:
                    for chunk in iter(lambda:response.read(1024*1024),b''): target.write(chunk)
                if tmp.stat().st_size != e['bytes'] or digest(tmp)[0] != e['md5']:
                    raise ValueError('download size or MD5 differs: '+e['fly'])
                tmp.replace(p)
            if not p.exists(): raise FileNotFoundError('missing raw file; supply it or use --download: '+e['filename'])
            md5, sha = digest(p)
            if p.stat().st_size != e['bytes'] or md5 != e['md5']:
                raise ValueError('raw size or MD5 differs: '+e['fly'])
            # Receipts refer only to files actually checked by this run.
            receipt = {'status':'verified','md5':md5,'sha256':sha,'bytes':p.stat().st_size}
            receipt_path.write_text(json.dumps(receipt)+'\n')
            source_hashes.append({'fly':e['fly'],**receipt})
            entry = {'directoryLabel':'/ephys_data_'+e['fly'],'dataFile':{'filename':e['filename'],'id':e['file_id'],'filesize':e['bytes'],'checksum':{'value':e['md5']}}}
            print('Analyzing '+e['fly'], file=sys.stderr, flush=True)
            computed = core.run_file(entry)
            if computed[0]['status'] != 'usable': raise ValueError(str(computed[0]))
            for sink, value in zip(results,computed): sink.extend(value if isinstance(value,list) else [value])
        except (OSError, ValueError, KeyError) as exc:
            errors.append({'fly':e['fly'],'message':str(exc)})
    for name, values in zip(('inventory','channels','pairs','lag_curves','sensitivity'),results):
        core.write_csv(output/(name+'.csv'),values)
    report = {'schema_version':'fly-neuron-atlas-ephys-run/v1','status':'pass' if not errors and len(results[0]) == len(selected) else 'fail','selected_records':len(selected),'processed_records':len(results[0]),'numpy':core.np.__version__,'scipy':core.scipy.__version__,'source_hashes':source_hashes,'errors':errors,'scope':'Raw-voltage detection and base correlations. Does not reproduce all supplemental sensitivity analyses or biological ground truth.'}
    (output/'RUN.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
