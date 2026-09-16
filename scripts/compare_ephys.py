#!/usr/bin/env python3
"""Compare an ephys run with an independently supplied saved reference (stdlib).

Exit 0: all selected cells agree; 1: comparison failed; 2: invalid invocation
or unreadable input. A pass is numerical agreement, not biological validation.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
KEYS = {
    'inventory': ('fly',),
    'channels': ('fly', 'neuron'),
    'pairs': ('fly', 'kind', 'signal', 'target'),
    'lag_curves': ('fly', 'signal', 'target', 'lag_ms'),
}
CHANNEL_METRICS = {
    'rate_no_stim_mean_Hz', 'fraction_ISI_under2ms', 'yaw_counts_r150',
    'yaw_vm_r150', 'rate_vm_r0', 'yaw_peak_abs_r', 'yaw_peak_abs_lag_ms',
    *(f'{axis}_{metric}' for axis in ('yaw', 'fwd', 'lat')
      for metric in ('r0', 'r150', 'shift1_r150', 'shift2_r150')),
    *(f'yaw_r150_third{i}' for i in (1, 2, 3)),
    'source_example_yaw_r150', 'threshold_grid_r150_min', 'threshold_grid_r150_max',
}
PAIR_METRICS = {'r0', 'r150', 'shift1_r150', 'shift2_r150', 'peak_abs_r', 'peak_abs_lag_ms'}
# Empty CSV cells and the token "nan" denote the same undefined value only here.
NAN_COLUMNS = {'inventory': set(), 'channels': CHANNEL_METRICS,
               'pairs': PAIR_METRICS, 'lag_curves': {'r'}}
REQUIRED = {
    'inventory': {'fly', 'file', 'status', 'source_clock_resets', 'time_coordinate',
                  'ephys_hz', 'ball_hz', 'analyzed_s', 'start_s', 'end_s', 'bins',
                  'neurons', 'valid_no_stim_s', 'file_id', 'author_quality_flag',
                  'source_md5_verified', 'mat_fields', 'epoch_durations_s', 'reason',
                  'available_ephys_s', 'author_spike_arrays',
                  'fwd_lat_raw_exact_equal_fraction', 'stim_bin_fraction', 'stim_min', 'stim_max'},
    'channels': {'fly', 'neuron', 'status', 'type', 'side', 'mat_channel', 'spikes',
                 'rate_mean_Hz', 'prominence', 'main_summary_eligible',
                 'rate_no_stim_mean_Hz', 'fraction_ISI_under2ms', 'yaw_r0', 'yaw_r150',
                 'author_quality_flag', 'noise_scale_median_mV', 'noise_scale_p05_mV', 'zero_mad_blocks'},
    'pairs': set(KEYS['pairs']) | PAIR_METRICS | {'main_summary_eligible'},
    'lag_curves': set(KEYS['lag_curves']) | {'r'},
}
TEXT_COLUMNS = {
    'fly', 'file', 'file_id', 'author_quality_flag', 'status', 'mat_fields',
    'epoch_durations_s', 'time_coordinate', 'reason', 'author_spike_arrays', 'neurons',
    'neuron', 'type', 'side', 'mat_channel', 'main_summary_eligible', 'source_md5_verified',
    'kind', 'signal', 'target', 'threshold_grid_sign_stable', 'all_thirds_yaw_sign_agree',
    'threshold_grid_all_estimable', 'processing_status', 'analysis_status',
}
EXCLUDED_COLUMNS = {'processing_seconds'}
REQUIRED['channels'] |= CHANNEL_METRICS - {
    'source_example_yaw_r150', 'threshold_grid_r150_min', 'threshold_grid_r150_max',
}
NUMERIC_COLUMNS = (set().union(*REQUIRED.values(), *NAN_COLUMNS.values()) - TEXT_COLUMNS) | {
    'available_ephys_s', 'fwd_lat_raw_exact_equal_fraction', 'stim_bin_fraction',
    'stim_min', 'stim_max', 'noise_scale_median_mV', 'noise_scale_p05_mV', 'zero_mad_blocks',
    'source_example_prominence', 'source_example_spikes', 'threshold_grid_finite_n',
}


class InputError(ValueError):
    pass


def read_table(directory, name):
    path = directory / (name + '.csv')
    if not path.is_file():
        return None, []
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if fields is None or len(fields) != len(set(fields)):
            raise InputError(f'{path}: missing or duplicate header')
        records = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in records):
        raise InputError(f'{path}: malformed CSV row')
    return fields, records


def row_key(name, row):
    result = []
    for column in KEYS[name]:
        value = row[column]
        if not value:
            raise InputError(f'{name}: empty primary key {column}')
        if column == 'lag_ms':
            number = float(value)
            if not math.isfinite(number) or not number.is_integer():
                raise InputError('lag_curves: lag_ms must be a finite integer')
            value = str(int(number))
        result.append(value)
    return tuple(result)


def equal_cell(name, column, generated, reference, atol, rtol):
    if column in TEXT_COLUMNS:
        return generated == reference, 'text'
    # Unknown common columns are still compared. They never gain NaN equivalence.
    try:
        a = float('nan' if generated == '' and column in NAN_COLUMNS[name] else generated)
        b = float('nan' if reference == '' and column in NAN_COLUMNS[name] else reference)
    except ValueError:
        if column in NUMERIC_COLUMNS:
            return False, 'non_numeric_or_missing'
        if generated == reference and generated != '':
            return True, 'text'
        return False, 'non_numeric_or_missing'
    if math.isinf(a) or math.isinf(b):
        return False, 'infinity_forbidden'
    if math.isnan(a) or math.isnan(b):
        return (column in NAN_COLUMNS[name] and math.isnan(a) and math.isnan(b)), 'undefined_value'
    return abs(a - b) <= atol + rtol * abs(b), 'numeric_tolerance'


def compare_table(name, generated, reference, selected, known, atol, rtol):
    gf, gr = read_table(generated, name)
    rf, rr = read_table(reference, name)
    result = {'primary_key': list(KEYS[name]), 'missing_files': [], 'missing_columns': {},
              'duplicate_keys': {}, 'missing_rows': [], 'extra_rows': [], 'differences': []}
    for role, fields in [('generated', gf), ('reference', rf)]:
        if fields is None:
            result['missing_files'].append(role)
        elif not set(KEYS[name]).issubset(fields):
            result['missing_columns'][role] = sorted(set(KEYS[name]) - set(fields))
    if result['missing_files'] or result['missing_columns']:
        result['status'] = 'fail'
        return result
    result['ignored_known_flies'] = sorted({r['fly'] for r in gr if r['fly'] in known - selected})
    gr = [r for r in gr if r['fly'] in selected or r['fly'] not in known]
    rr = [r for r in rr if r['fly'] in selected]
    for role, fields, rows in [('generated', gf, gr), ('reference', rf, rr)]:
        required = REQUIRED[name]
        if name in ('channels', 'inventory') and rows and all(r.get('status') == 'excluded' for r in rows):
            required = set(KEYS[name]) | {'status'}
        if rows and required - set(fields):
            result['missing_columns'][role] = sorted(required - set(fields))
    indexed = []
    for role, records in [('generated', gr), ('reference', rr)]:
        mapping, duplicates = {}, []
        for row in records:
            key = row_key(name, row)
            if key in mapping:
                duplicates.append(list(key))
            mapping[key] = row
        indexed.append(mapping)
        result['duplicate_keys'][role] = duplicates
    gm, rm = indexed
    result['missing_rows'] = [list(k) for k in sorted(rm.keys() - gm.keys())]
    result['extra_rows'] = [list(k) for k in sorted(gm.keys() - rm.keys())]
    columns = sorted(set(gf) & set(rf) - set(KEYS[name]) - EXCLUDED_COLUMNS)
    result['compared_columns'] = columns
    result['reference_only_columns'] = sorted(set(rf) - set(gf) - EXCLUDED_COLUMNS)
    result['generated_only_columns'] = sorted(set(gf) - set(rf) - EXCLUDED_COLUMNS)
    result['excluded_runtime_columns'] = sorted((set(gf) | set(rf)) & EXCLUDED_COLUMNS)
    result['generated_rows'], result['reference_rows'] = len(gr), len(rr)
    result['excluded_records'] = {role: [list(row_key(name, row)) for row in rows
                                       if row.get('status') == 'excluded']
                                  for role, rows in [('generated', gr), ('reference', rr)]}
    for key in sorted(gm.keys() & rm.keys()):
        for column in columns:
            a, b = gm[key][column], rm[key][column]
            # Excluded rows have absent numerical measurements, never zero.
            if a == b == '' and gm[key].get('status') == rm[key].get('status') == 'excluded':
                continue
            same, reason = equal_cell(name, column, a, b, atol, rtol)
            if not same:
                result['differences'].append({'key': list(key), 'column': column,
                                              'generated': a, 'reference': b, 'reason': reason})
    failed = (result['missing_columns'] or any(result['duplicate_keys'].values()) or
              result['missing_rows'] or result['extra_rows'] or result['differences'])
    result['status'] = 'fail' if failed else 'pass'
    return result


def compare(generated, reference, flies=None, atol=1e-10, rtol=1e-10):
    if not math.isfinite(atol) or not math.isfinite(rtol) or min(atol, rtol) < 0:
        raise InputError('tolerances must be finite and nonnegative')
    if not generated.is_dir() or not reference.is_dir():
        raise InputError('generated and reference must be existing directories')
    fields, inventory = read_table(reference, 'inventory')
    if fields is None or 'fly' not in fields:
        raise InputError('reference inventory.csv with fly column is required')
    known = {row['fly'] for row in inventory}
    selection_source = 'explicit --fly' if flies else 'reference inventory'
    run_path = generated / 'RUN.json'
    run = json.loads(run_path.read_text(encoding='utf-8')) if run_path.is_file() else None
    if not flies and isinstance(run, dict) and 'selected_flies' in run:
        flies = run['selected_flies']
        selection_source = 'generated RUN.json selected_flies'
    if flies is not None and (not isinstance(flies, list) or not flies or
                             any(not isinstance(fly, str) for fly in flies) or len(flies) != len(set(flies))):
        raise InputError('selection must be a nonempty list of unique fly labels')
    selected = set(flies) if flies else known
    if not selected or selected - known:
        raise InputError(f'unknown or empty reference selection: {sorted(selected - known)}')
    tables = {name: compare_table(name, generated, reference, selected, known, atol, rtol) for name in KEYS}
    return {'schema_version': 'fly-neuron-atlas-ephys-comparison/v1',
            'status': 'pass' if all(t['status'] == 'pass' for t in tables.values()) else 'fail',
            'generated': str(generated.resolve()), 'reference': str(reference.resolve()),
            'selected_flies': sorted(selected), 'selection_source': selection_source,
            'run_status': run.get('status') if isinstance(run, dict) else None,
            'tolerance': {'absolute': atol, 'relative_to_reference': rtol},
            'nan_policy': {name: sorted(cols) for name, cols in NAN_COLUMNS.items()},
            'tables': tables,
            'scope': 'Selected saved table cells; independent comparison logic; no biological validation. '
                     'Run completion and numerical agreement are separate statuses.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', type=Path, required=True)
    parser.add_argument('--reference', type=Path, default=ROOT / 'data/activity')
    parser.add_argument('--fly', action='append')
    parser.add_argument('--atol', type=float, default=1e-10)
    parser.add_argument('--rtol', type=float, default=1e-10)
    args = parser.parse_args(argv)
    try:
        result = compare(args.generated, args.reference, args.fly, args.atol, args.rtol)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'schema_version': 'fly-neuron-atlas-ephys-comparison/v1',
                          'status': 'error', 'message': str(exc)}, allow_nan=False))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
