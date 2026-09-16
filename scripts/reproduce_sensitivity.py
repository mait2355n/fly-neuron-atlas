#!/usr/bin/env python3
"""Regenerate principal sensitivities from a completed corrected ephys run.

Requires requirements-ephys.txt, original raw MAT files, and RUN.json,
inventory.csv, channels.csv and aligned/*.npz from reanalyze_ephys.py (v2).
Writes only to a new or empty --output directory. No downloads are performed.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
METHOD = 'epoch-isolated-sensitivity/v2'
MULTIPLIERS = (0.75, 1.0, 1.25, 1.5, 2.0, 2.5)
GUARDS = (0.5, 5.5)
FIELDS = {
    'threshold_lag_sensitivity': ['fly', 'neuron', 'absolute_prominence', 'prominence_multiplier',
        'spikes', 'r150', 'peak_abs_lag_ms', 'peak_abs_r'],
    'paired_threshold_sensitivity': ['fly', 'kind', 'multiplier', 'difference_r150',
        'difference_peak_lag_ms', 'difference_peak_r'],
    'pair_sensitivity': ['fly', 'prominence', 'source_notebook_example', 'main_file_eligible',
        'difference_r150', 'sum_r150', 'left_r150', 'right_r150',
        'difference_peak_abs_lag_ms', 'difference_peak_abs_r'],
    'voltage_sensitivity': ['fly', 'signal', 'kind', 'r150', 'vm_cutoff_r150',
        'baseline_valid_bins', 'vm_cutoff_valid_bins', 'vm_cutoff_fraction_retained',
        'main_summary_eligible', 'interpretation'],
    'clock_boundary_sensitivity': ['fly', 'method', 'guard_s', 'signal', 'target',
        'r150', 'peak_abs_lag_ms', 'peak_abs_r', 'valid_s'],
    'source_example_comparison': ['fly', 'neuron', 'source_example_prominence',
        'source_example_spikes', 'source_example_yaw_r150', 'threshold_grid_sign_stable',
        'threshold_grid_all_estimable', 'threshold_grid_finite_n',
        'threshold_grid_r150_min', 'threshold_grid_r150_max'],
}


def read_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'invalid CSV header: {path.name}')
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f'malformed CSV: {path.name}')
    return rows


def digest(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            md5.update(block)
            sha.update(block)
    return {'bytes': path.stat().st_size, 'md5': md5.hexdigest(), 'sha256': sha.hexdigest()}


def unique(rows, key, name):
    result = {}
    for row in rows:
        identity = tuple(row[k] for k in key)
        if any(not v for v in identity) or identity in result:
            raise ValueError(f'duplicate or empty {name} key: {identity}')
        result[identity] = row
    return result


def validate_run(run_dir, flies=None):
    run = json.loads((run_dir / 'RUN.json').read_text(encoding='utf-8'))
    if (run.get('schema_version') != 'fly-neuron-atlas-ephys-run/v2' or
            run.get('processing_status') != 'completed' or run.get('analysis_status') != 'usable' or
            run.get('status') != 'pass'):
        raise ValueError('run must be completed, usable and pass under ephys-run/v2')
    selection = run.get('selected_flies')
    if (not isinstance(selection, list) or not selection or
            any(not isinstance(f, str) or Path(f).name != f for f in selection) or
            len(set(selection)) != len(selection)):
        raise ValueError('RUN selected_flies must be a nonempty unique label list')
    inventory = unique(read_rows(run_dir / 'inventory.csv'), ('fly',), 'inventory')
    if set(inventory) != {(f,) for f in selection}:
        raise ValueError('inventory fly population differs from RUN selected_flies')
    channels = unique(read_rows(run_dir / 'channels.csv'), ('fly', 'neuron'), 'channels')
    hashes = unique(run.get('source_hashes', []), ('fly',), 'source_hashes')
    if set(hashes) != set(inventory):
        raise ValueError('source_hashes fly population differs from RUN selected_flies')
    expected_channels = set()
    for (fly,), row in inventory.items():
        if row['status'] != 'usable':
            raise ValueError(f'nonusable inventory row: {fly}')
        labels = row['neurons'].split(';')
        if not all(labels) or len(labels) != len(set(labels)):
            raise ValueError(f'invalid inventory neuron labels: {fly}')
        expected_channels.update((fly, label) for label in labels)
    if set(channels) != expected_channels or any(c['status'] != 'usable' for c in channels.values()):
        raise ValueError('usable channel population differs from inventory neurons')
    selected = flies or selection
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(selection):
        raise ValueError('--fly must select unique labels from RUN selected_flies')
    return run, [inventory[(f,)] for f in selected], channels, hashes


def output_path(value, raw_dir, run_dir):
    output = value.resolve()
    for protected in (ROOT, raw_dir, run_dir):
        if output == protected or output in protected.parents:
            raise ValueError('--output overlaps an input or repository root')
    for protected in (raw_dir, run_dir, *(ROOT / p for p in ('data', 'docs', 'scripts', 'tests', 'licenses', '.git'))):
        if output == protected or protected in output.parents:
            raise ValueError('--output overlaps protected inputs or published files')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('--output must be a new or empty directory')
    return output


def summarize(x, y, mask, epochs, core):
    np = core.np
    curve = np.array([core.corr(x, y, mask, lag=int(lag), epochs=epochs) for lag in core.LAGS])
    index = int(np.nanargmax(abs(curve))) if np.isfinite(curve).any() else None
    return {'r150': core.corr(x, y, mask, lag=15, epochs=epochs),
            'peak_abs_lag_ms': int(core.LAGS[index] * 10) if index is not None else float('nan'),
            'peak_abs_r': float(curve[index]) if index is not None else float('nan')}


def guard_mask(mask, time_s, epochs, guard_s, np):
    result = mask.copy()
    for index in np.flatnonzero(np.diff(epochs) != 0) + 1:
        boundary = time_s[index] - 0.5 / 100
        result &= abs(time_s - boundary) >= guard_s
    return result


def process_record(info, channels, raw_dir, run_dir, expected_hash, output, core):
    np = core.np
    fly = info['fly']
    filename = info['file']
    if Path(filename).name != filename:
        raise ValueError(f'raw filename must be a basename: {fly}')
    raw = raw_dir / filename
    hashes = digest(raw)
    if hashes['md5'] != expected_hash['md5'] or hashes['bytes'] != expected_hash['bytes']:
        raise ValueError(f'raw MD5/size differs from completed run: {fly}')
    if expected_hash.get('sha256') and hashes['sha256'] != expected_hash['sha256']:
        raise ValueError(f'raw SHA256 differs from completed run: {fly}')
    with np.load(run_dir / 'aligned' / (fly + '.npz'), allow_pickle=False) as archive:
        z = {name: archive[name] for name in archive.files}
    nbin = int(info['bins'])
    labels = info['neurons'].split(';')
    if labels != core.labels(fly):
        raise ValueError(f'inventory neuron identity differs from record label: {fly}')
    needed = ['valid', 'yaw', 'time_s', 'epoch_id'] + [lab + '_' + suffix
        for lab in labels for suffix in ('valid', 'fr', 'counts', 'vm')]
    if any(name not in z or z[name].ndim != 1 or len(z[name]) != nbin for name in needed):
        raise ValueError(f'aligned arrays absent or wrong shape: {fly}')
    if z['valid'].dtype != np.bool_ or any(z[lab + '_valid'].dtype != np.bool_ for lab in labels):
        raise ValueError(f'aligned masks must be boolean: {fly}')
    if not np.allclose(z['time_s'], float(info['start_s']) + (np.arange(nbin) + .5) / 100,
                       atol=1e-9, rtol=0):
        raise ValueError(f'aligned time coordinate differs from inventory: {fly}')
    if int(z['valid'].sum()) != round(float(info['valid_no_stim_s']) * 100):
        raise ValueError(f'aligned valid duration differs from inventory: {fly}')
    d = core.loadmat(raw, squeeze_me=True)
    fs = int(d['ephys_SR'])
    if fs != int(info['ephys_hz']) or fs % 100:
        raise ValueError(f'raw sampling rate differs from inventory: {fly}')
    spb = fs // 100
    starti = int(round(float(info['start_s']) * fs))
    endi = starti + nbin * spb
    source_time = np.asarray(d['t_ephys'])
    bounds = np.r_[0, np.flatnonzero(np.diff(source_time) <= 0) + 1, len(source_time)]
    expected_epochs = np.searchsorted(bounds, starti + np.arange(nbin) * spb, side='right') - 1
    if not np.array_equal(expected_epochs, z['epoch_id']):
        raise ValueError(f'aligned epochs differ from raw clock resets: {fly}')
    if len(bounds) - 2 != int(info['source_clock_resets']):
        raise ValueError(f'raw reset count differs from inventory: {fly}')
    tables = {name: [] for name in FIELDS}
    rates, references = {}, {}
    epochs, yaw = z['epoch_id'], z['yaw']
    for index, label in enumerate(labels):
        channel = channels[(fly, label)]
        expected_channel = 'ephys_' + ('A' if index == 0 else 'B')
        if channel['mat_channel'] != expected_channel:
            raise ValueError(f'channel mapping differs from inventory: {fly}:{label}')
        base = 7.5 if label.startswith('a2') else 5.75
        if float(channel['prominence']) != base:
            raise ValueError(f'base prominence differs from supported method: {fly}:{label}')
        result = core.process_voltage_epochs(np.asarray(d[expected_channel]), fs, base, spb,
                                             bounds, starti, endi)
        # A completed run must contain the exact base detector representation.
        if not np.array_equal(result['counts'], z[label + '_counts']):
            raise ValueError(f'baseline counts differ from completed run: {fly}:{label}')
        if not np.allclose(result['fr'], z[label + '_fr'], atol=1e-10, rtol=1e-10):
            raise ValueError(f'baseline rates differ from completed run: {fly}:{label}')
        if not np.allclose(result['vm'], z[label + '_vm'], atol=1e-10, rtol=1e-10):
            raise ValueError(f'baseline Vm differs from completed run: {fly}:{label}')
        mask = z[label + '_valid']
        if np.any(mask & ~z['valid']):
            raise ValueError(f'channel validity exceeds record validity: {fly}:{label}')
        grid = MULTIPLIERS if label.startswith('a2') else MULTIPLIERS[:3]
        correlations, spike_counts = {}, {}
        for mult in grid:
            if mult == 1:
                peaks, counts, rate = result['peaks'], result['counts'], result['fr']
            else:
                peaks, counts, rate, _ = core.extract_spikes_by_epoch(
                    result['proc'], fs, base * mult, spb, result['epoch_bounds'])
            rates[label, mult] = rate
            summary = summarize(rate, yaw, mask, epochs, core)
            correlations[mult], spike_counts[mult] = summary['r150'], len(peaks)
            tables['threshold_lag_sensitivity'].append({'fly': fly, 'neuron': label,
                'absolute_prominence': base * mult, 'prominence_multiplier': mult,
                'spikes': len(peaks), **summary})
            if mult == (2 if label.startswith('a2') else 1):
                references[label + '_fr'], references[label + '_counts'] = rate, counts
        finite = [value for value in correlations.values() if math.isfinite(value)]
        ref_mult = 2 if label.startswith('a2') else 1
        tables['source_example_comparison'].append({'fly': fly, 'neuron': label,
            'source_example_prominence': base * ref_mult,
            'source_example_spikes': spike_counts[ref_mult],
            'source_example_yaw_r150': correlations[ref_mult],
            'threshold_grid_sign_stable': len(set(np.sign(finite))) == 1,
            'threshold_grid_all_estimable': len(finite) == len(grid),
            'threshold_grid_finite_n': len(finite),
            'threshold_grid_r150_min': min(finite) if finite else float('nan'),
            'threshold_grid_r150_max': max(finite) if finite else float('nan')})
        del result
    (output / 'source_example_aligned').mkdir(exist_ok=True)
    np.savez_compressed(output / 'source_example_aligned' / (fly + '.npz'), **references)
    pair_inputs = []
    if len(labels) == 2:
        a, b = labels
        pair_mask = z[a + '_valid'] & z[b + '_valid']
        same_type = a[:2] == b[:2]
        grid = MULTIPLIERS if a.startswith('a2') and b.startswith('a2') else MULTIPLIERS[:3]
        for mult in grid:
            difference = rates[a, mult] - rates[b, mult]
            summary = summarize(difference, yaw, pair_mask, epochs, core)
            tables['paired_threshold_sensitivity'].append({'fly': fly,
                'kind': 'bilateral' if same_type else 'same_side_cross_type', 'multiplier': mult,
                'difference_r150': summary['r150'], 'difference_peak_lag_ms': summary['peak_abs_lag_ms'],
                'difference_peak_r': summary['peak_abs_r']})
            if fly.startswith('a2_d_'):
                tables['pair_sensitivity'].append({'fly': fly, 'prominence': 7.5 * mult,
                    'source_notebook_example': mult == 2,
                    'main_file_eligible': all(channels[(fly, lab)]['main_summary_eligible'] == 'True' for lab in labels),
                    'difference_r150': summary['r150'],
                    'sum_r150': core.corr(rates[a, mult] + rates[b, mult], yaw, pair_mask, lag=15, epochs=epochs),
                    'left_r150': core.corr(rates[a, mult], yaw, pair_mask, lag=15, epochs=epochs),
                    'right_r150': core.corr(rates[b, mult], yaw, pair_mask, lag=15, epochs=epochs),
                    'difference_peak_abs_lag_ms': summary['peak_abs_lag_ms'],
                    'difference_peak_abs_r': summary['peak_abs_r']})
        if not same_type:
            for mult in (1, 2):
                summary = summarize(rates[a, mult], rates[b, 1], pair_mask, epochs, core)
                tables['paired_threshold_sensitivity'].append({'fly': fly, 'kind': 'DNa02_to_DNa01_lag',
                    'multiplier': mult, 'difference_r150': float('nan'),
                    'difference_peak_lag_ms': summary['peak_abs_lag_ms'], 'difference_peak_r': summary['peak_abs_r']})
        kind = 'bilateral_same_type' if same_type else 'same_side_cross_type'
        pair_inputs = [(a + '_rate', kind, rates[a, 1], rates[b, 1]),
                       ('A_minus_B', kind, rates[a, 1] - rates[b, 1], yaw),
                       ('A_plus_B', kind, rates[a, 1] + rates[b, 1], yaw)]
    for label in labels:
        mask = z[label + '_valid']
        quality = mask & (z[label + '_vm'] <= -33)
        tables['voltage_sensitivity'].append(voltage_row(fly, label, 'single_channel',
            rates[label, 1], yaw, mask, quality, epochs,
            channels[(fly, label)]['main_summary_eligible'] == 'True', core))
    for signal, kind, x, y in pair_inputs:
        mask = z[labels[0] + '_valid'] & z[labels[1] + '_valid']
        quality = mask & (z[labels[0] + '_vm'] <= -33) & (z[labels[1] + '_vm'] <= -33)
        tables['voltage_sensitivity'].append(voltage_row(fly, signal, kind, x, y, mask, quality, epochs,
            all(channels[(fly, lab)]['main_summary_eligible'] == 'True' for lab in labels), core))
    if int(info['source_clock_resets']) > 0:
        for guard in GUARDS:
            for method in ('baseline7.5', 'source_example15'):
                signals = {lab: rates[lab, 1] if method == 'baseline7.5' else references[lab + '_fr'] for lab in labels}
                for lab in labels:
                    mask = guard_mask(z[lab + '_valid'], z['time_s'], epochs, guard, np)
                    tables['clock_boundary_sensitivity'].append({'fly': fly, 'method': method,
                        'guard_s': guard, 'signal': lab + '_fr', 'target': 'yaw',
                        **summarize(signals[lab], yaw, mask, epochs, core), 'valid_s': int(mask.sum()) / 100})
                if len(labels) == 2:
                    mask = guard_mask(z[labels[0] + '_valid'] & z[labels[1] + '_valid'],
                                      z['time_s'], epochs, guard, np)
                    tables['clock_boundary_sensitivity'].append({'fly': fly, 'method': method,
                        'guard_s': guard, 'signal': labels[0] + '_fr', 'target': labels[1] + '_fr',
                        **summarize(signals[labels[0]], signals[labels[1]], mask, epochs, core),
                        'valid_s': int(mask.sum()) / 100})
    return tables, {'fly': fly, **hashes,
        'aligned_sha256': digest(run_dir / 'aligned' / (fly + '.npz'))['sha256']}


def voltage_row(fly, signal, kind, x, y, mask, quality, epochs, eligible, core):
    return {'fly': fly, 'signal': signal, 'kind': kind,
        'r150': core.corr(x, y, mask, lag=15, epochs=epochs),
        'vm_cutoff_r150': core.corr(x, y, quality, lag=15, epochs=epochs),
        'baseline_valid_bins': int(mask.sum()), 'vm_cutoff_valid_bins': int(quality.sum()),
        'vm_cutoff_fraction_retained': float(quality.sum() / max(1, mask.sum())),
        'main_summary_eligible': eligible,
        'interpretation': 'Exploratory pointwise Vm <= -33 mV sensitivity, not author exclusion reproduction'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fly', action='append')
    args = parser.parse_args(argv)
    try:
        raw, run_dir = args.raw_dir.resolve(), args.run_dir.resolve()
        output = output_path(args.output, raw, run_dir)
        run, inventory, channels, hashes = validate_run(run_dir, args.fly)
        import ephys_core as core
        if not hasattr(core, 'process_voltage_epochs'):
            raise ValueError('corrected ephys_core with epoch helpers is required')
        output.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(json.dumps({'schema_version': 'fly-neuron-atlas-sensitivity-run/v2',
                          'status': 'error', 'message': str(exc)}, allow_nan=False))
        return 2
    tables = {name: [] for name in FIELDS}
    inputs, errors, processed = [], [], []
    for info in inventory:
        fly = info['fly']
        print('Sensitivity ' + fly, file=sys.stderr, flush=True)
        try:
            generated, receipt = process_record(info, channels, raw, run_dir, hashes[(fly,)], output, core)
            for name, rows in generated.items():
                tables[name].extend(rows)
            inputs.append(receipt)
            processed.append(fly)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append({'fly': fly, 'message': str(exc)})
    for name, fields in FIELDS.items():
        with (output / (name + '.csv')).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields + ['method_version'])
            writer.writeheader()
            writer.writerows({**row, 'method_version': METHOD} for row in tables[name])
    report = {'schema_version': 'fly-neuron-atlas-sensitivity-run/v2',
        'method_version': METHOD, 'status': 'pass' if not errors else 'fail',
        'processing_status': 'completed' if not errors else 'partial' if processed else 'failed',
        'selected_flies': [r['fly'] for r in inventory], 'processed_flies': processed,
        'source_run_schema': run['schema_version'],
        'source_run_sha256': digest(run_dir / 'RUN.json')['sha256'],
        'inventory_sha256': digest(run_dir / 'inventory.csv')['sha256'],
        'channels_sha256': digest(run_dir / 'channels.csv')['sha256'],
        'generator_sha256': digest(Path(__file__))['sha256'],
        'core_sha256': digest(Path(core.__file__))['sha256'],
        'numpy': core.np.__version__, 'scipy': core.scipy.__version__,
        'settings': {'DNa02_multipliers': MULTIPLIERS, 'DNa01_multipliers': MULTIPLIERS[:3],
                     'DNa02_prominence': 7.5, 'DNa01_prominence': 5.75,
                     'voltage_cutoff_mV': -33, 'clock_guards_s': GUARDS, 'lag_ms': [-500, 500, 10]},
        'inputs': inputs, 'errors': errors, 'rows': {name: len(rows) for name, rows in tables.items()},
        'scope': 'Corrected epoch-isolated regeneration with archived settings. '
                 'New method results supersede corresponding legacy calculations; '
                 'they do not assert numerical identity with v1 or biological validity.'}
    (output / 'SENSITIVITY.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
