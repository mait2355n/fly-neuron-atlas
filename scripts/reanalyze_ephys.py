#!/usr/bin/env python3
"""Optional raw-voltage rerun with explicit download/output paths.

Example: python scripts/reanalyze_ephys.py --fly a2_d_08 --download \
  --raw-dir .local/raw --output .local/ephys
Requires requirements-ephys.txt. Writes only to --raw-dir and --output.
Selected raw files must match the published size and MD5 before analysis.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            md5.update(b); sha.update(b)
    return md5.hexdigest(), sha.hexdigest()


def download_verified(entry, destination, opener=None):
    """Use an attempt-owned temporary file; failed/stale parts cannot block retry.

    A legacy ``filename.part`` is preserved and ignored. Publication of verified
    bytes is exclusive: an existing destination is never overwritten.
    """
    opener = opener or urllib.request.urlopen
    legacy_part = destination.with_suffix(destination.suffix + '.part')
    note = {'fly': entry['fly'], 'legacy_partial_preserved': legacy_part.exists() or legacy_part.is_symlink()}
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent,
                                         prefix='.' + destination.name + '.', suffix='.part', delete=False) as target:
            tmp = Path(target.name)
            with opener(entry['url'], timeout=120) as response:
                size = 0
                for chunk in iter(lambda: response.read(1024 * 1024), b''):
                    size += len(chunk)
                    if size > entry['bytes']:
                        raise ValueError('download exceeds expected size: ' + entry['fly'])
                    target.write(chunk)
        if tmp.stat().st_size != entry['bytes'] or digest(tmp)[0] != entry['md5']:
            raise ValueError('download size or MD5 differs: ' + entry['fly'])
        try:
            os.link(tmp, destination)
        except FileExistsError:
            # A concurrent completed download may be reused, never replaced.
            if (destination.is_symlink() or destination.stat().st_size != entry['bytes']
                    or digest(destination)[0] != entry['md5']):
                raise ValueError('existing destination differs; preserved: ' + entry['fly'])
        return note
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def assess_record(core, info, channels, pairs):
    """Independently guard the wrapper's success decision against empty results."""
    expected = core.labels(info['fly'])
    channel_keys = Counter((r.get('fly'), r.get('neuron')) for r in channels)
    expected_channel_keys = Counter((info['fly'], n) for n in expected)
    expected_pairs = [] if len(expected) == 1 else [
        (expected[0] + '_rate', expected[1] + '_rate'),
        ('A_minus_B', 'yaw'), ('A_plus_B', 'yaw'),
    ]
    pair_kind = 'same_side_cross_type' if info['fly'].startswith('a1_a2') else 'bilateral_same_type'
    pair_keys = Counter((r.get('fly'), r.get('kind'), r.get('signal'), r.get('target')) for r in pairs)
    expected_pair_keys = Counter((info['fly'], pair_kind, a, b) for a, b in expected_pairs)

    def usable(row, metric):
        try:
            return (row.get('numerical_valid') is True
                    and int(row.get('n_valid_r150', 0)) >= 100
                    and all(math.isfinite(float(row[k])) for k in (metric, metric.replace('r150', 'r0'))))
        except (KeyError, TypeError, ValueError):
            return False

    good_channels = [r for r in channels if (r.get('fly'), r.get('neuron')) in expected_channel_keys and usable(r, 'yaw_r150')]
    good_pairs = [r for r in pairs if (r.get('fly'), r.get('kind'), r.get('signal'), r.get('target')) in expected_pair_keys and usable(r, 'r150')]
    complete = (channel_keys == expected_channel_keys and pair_keys == expected_pair_keys
                and len(good_channels) == len(expected) and len(good_pairs) == len(expected_pairs)
                and info.get('processing_status') == 'completed')
    state = 'usable' if complete else ('partial' if good_channels else 'excluded')
    reasons = []
    if channel_keys != expected_channel_keys: reasons.append('channel_identity_set_mismatch')
    if pair_keys != expected_pair_keys: reasons.append('pair_identity_set_mismatch')
    if len(good_channels) != len(expected): reasons.append('unavailable_expected_channel_analysis')
    if len(good_pairs) != len(expected_pairs): reasons.append('unavailable_expected_pair_analysis')
    info.update(analysis_status=state, status=state, analysis_complete=complete,
                main_summary_eligible=complete and info['fly'] != 'a2_d_14')
    if reasons:
        info['wrapper_analysis_reasons'] = reasons
    for row in channels + pairs:
        row['main_summary_eligible'] = bool(row.get('main_summary_eligible')) and complete
    return state, reasons


def write_results(core, output, results):
    # Empty analyses remain valid CSV files with explicit identities, never
    # disappear from the output contract merely because all rows were excluded.
    empty_headers = {
        'inventory': ['fly', 'processing_status', 'analysis_status', 'reason'],
        'channels': ['fly', 'neuron', 'status', 'reason'],
        'pairs': ['fly', 'kind', 'signal', 'target', 'status', 'reason'],
        'lag_curves': ['fly', 'signal', 'target', 'lag_ms', 'r'],
        'sensitivity': ['fly', 'neuron', 'prominence_multiplier'],
    }
    for name, values in zip(empty_headers, results):
        path = output / (name + '.csv')
        if values:
            core.write_csv(path, values)
        else:
            with path.open('w', newline='', encoding='utf-8') as handle:
                csv.writer(handle).writerow(empty_headers[name])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fly', help='One record label; omit for all 23')
    ap.add_argument('--list', action='store_true', help='Print selected metadata and exit without importing numerical libraries')
    ap.add_argument('--download', action='store_true', help='Download missing selected raw files from Harvard Dataverse')
    ap.add_argument('--raw-dir', type=Path, default=ROOT/'.local/raw')
    ap.add_argument('--output', type=Path, default=ROOT/'.local/ephys')
    args = ap.parse_args()
    manifest = json.loads((ROOT/'data/activity/download_manifest.json').read_text(encoding='utf-8'))
    selected = [e for e in manifest['files'] if not args.fly or e['fly'] == args.fly]
    if not selected: ap.error('unknown --fly record label')
    if args.list:
        print(json.dumps({'selected':selected,'total_bytes':sum(e['bytes'] for e in selected)},indent=2)); return 0
    raw, output = args.raw_dir.resolve(), args.output.resolve()
    if output.exists() and not output.is_dir():
        ap.error('--output must be a directory')
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
    analysis_issues = []
    download_notes = []
    source_hashes = []
    core.selftest()
    for e in selected:
        p = raw/e['filename']
        try:
            if Path(e['filename']).name != e['filename'] or e['filename'] in ('', '.', '..'):
                raise ValueError('raw filename must be a single path component')
            receipt_path = p.with_suffix(p.suffix+'.receipt.json')
            if p.is_symlink() or receipt_path.is_symlink():
                raise ValueError('raw file or receipt is a symlink: '+e['fly'])
            if not p.exists() and args.download:
                download_notes.append(download_verified(e, p))
            if not p.exists(): raise FileNotFoundError('missing raw file; supply it or use --download: '+e['filename'])
            md5, sha = digest(p)
            if p.stat().st_size != e['bytes'] or md5 != e['md5']:
                raise ValueError('raw size or MD5 differs: '+e['fly'])
            # Receipts refer only to files actually checked by this run.
            receipt = {'status':'verified','md5':md5,'sha256':sha,'bytes':p.stat().st_size}
            receipt_path.write_text(json.dumps(receipt)+'\n', encoding='utf-8')
            source_hashes.append({'fly':e['fly'],**receipt})
            entry = {'directoryLabel':'/ephys_data_'+e['fly'],'dataFile':{'filename':e['filename'],'id':e['file_id'],'filesize':e['bytes'],'checksum':{'value':e['md5']}}}
            print('Analyzing '+e['fly'], file=sys.stderr, flush=True)
            computed = core.run_file(entry)
            if computed[0].get('fly') != e['fly']:
                raise ValueError('computed record identity differs from selected raw record: ' + e['fly'])
            state, reasons = assess_record(core, computed[0], computed[1], computed[2])
            if state != 'usable':
                analysis_issues.append({'fly':e['fly'], 'analysis_status':state,
                                        'reasons':reasons, 'core_reasons':computed[0].get('reasons', [])})
            for sink, value in zip(results,computed): sink.extend(value if isinstance(value,list) else [value])
        except (OSError, ValueError, KeyError) as exc:
            errors.append({'fly':e['fly'],'message':str(exc)})
    write_results(core, output, results)
    processed = sum(r.get('processing_status') == 'completed' for r in results[0])
    states = Counter(r['analysis_status'] for r in results[0])
    processing_status = 'completed' if not errors and processed == len(selected) else ('partial' if processed else 'failed')
    analysis_status = 'usable' if states['usable'] == len(selected) else ('partial' if states['usable'] or states['partial'] else 'excluded')
    report = {'schema_version':'fly-neuron-atlas-ephys-run/v2',
              'status':'pass' if processing_status == 'completed' and analysis_status == 'usable' else 'fail',
              'processing_status':processing_status, 'analysis_status':analysis_status,
              'selected_flies':[e['fly'] for e in selected], 'selected_records':len(selected), 'processed_records':processed,
              'usable_records':states['usable'], 'partial_records':states['partial'], 'excluded_records':states['excluded'],
              'analysis_method':'epoch-independent-v2', 'numpy':core.np.__version__, 'scipy':core.scipy.__version__,
              'source_hashes':source_hashes, 'errors':errors, 'analysis_issues':analysis_issues, 'download_notes':download_notes,
              'code_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('scripts/ephys_core.py','scripts/reanalyze_ephys.py')},
              'scope':'Raw-voltage detection and base correlations. Numerical availability and author-quality eligibility are separate. Biological ground truth is not certified.'}
    (output/'RUN.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
