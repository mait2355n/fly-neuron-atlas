#!/usr/bin/env python3
"""Recompute published counts from included data. Python 3.10+, standard library.

Read-only. stdout: JSON; exit 0 on agreement, 1 on inconsistency.
This validates snapshot arithmetic, not biological function or source truth.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from table_contracts import (BILATERAL_SIGNALS, COMPLETE_IO_STATES, MAIN_BILATERAL_FLIES,
                             THRESHOLDS, finite, rows, validate)

ROOT = Path(__file__).resolve().parents[1]


def unique_rows(path, key):
    """Reject duplicate identities instead of silently keeping the last row."""
    result = {}
    for row in rows(path):
        identity = row[key]
        if identity in result:
            raise ValueError(f'duplicate {key} in {path.name}: {identity}')
        result[identity] = row
    return result


def compute(root=ROOT):
    d = root / 'data'
    contracts = validate(root)
    checks, result = dict(contracts['checks']), {}
    motors = unique_rows(d/'motor_atlas.csv', 'bodyId')
    groups = {p: r['group_id'] for p, r in unique_rows(d/'motor_groups.csv', 'bodyId').items()}
    candidates = unique_rows(d/'shared_candidates.csv', 'bodyId')
    studied_rows = unique_rows(d/'studied_cells.csv', 'bodyId')
    sensitivity_rows = unique_rows(d/'annotation_sensitivity.csv', 'bodyId')
    excluded = set(json.loads((d/'snapshot.json').read_text(encoding='utf-8'))['excluded_annotation_only_motor_ids'])
    studied = set(studied_rows)
    denominator_rows = list(rows(d/'studied_totals.csv'))
    expected_grid = Counter((p, direction, t) for p in studied for direction in ('incoming', 'outgoing') for t in THRESHOLDS)
    actual_grid = Counter((r['target_bodyId'], r['direction'], int(r['threshold'])) for r in denominator_rows)
    checks['studied_cell_selection_matches_candidates'] = (
        studied == {p for p, r in candidates.items() if r['full_io_state'] in COMPLETE_IO_STATES}
        and all(r == candidates.get(p) for p, r in studied_rows.items())
    )
    checks['studied_denominator_grid_complete'] = actual_grid == expected_grid
    checks['annotation_sensitivity_candidate_set'] = set(sensitivity_rows) == set(candidates)
    checks['motor_group_members_are_in_atlas'] = set(groups) <= set(motors)
    totals = defaultdict(lambda: [0, 0])
    pres, annotated = set(), set()
    thresholds = {t: defaultdict(set) for t in THRESHOLDS}
    full, retained = defaultdict(Counter), defaultdict(Counter)
    for r in rows(d/'connectivity/motor_inputs.csv.gz'):
        pre, post, w = r['bodyId_pre'], r['bodyId_post'], int(r['weight'])
        totals[post][0] += 1; totals[post][1] += w
        pres.add(pre)
        if r['preIsNeuron'] == 'True':
            annotated.add(pre)
        if post in groups:
            if r['preIsNeuron'] == 'True' and pre not in motors:
                for t, by_cell in thresholds.items():
                    if w >= t: by_cell[pre].add(groups[post])
            if pre in candidates and w >= 10:
                full[pre][groups[post]] += w
                if post not in excluded: retained[pre][groups[post]] += w
    ids_t10 = {p for p, g in thresholds[10].items() if len(g) >= 2}
    result['motor_count'] = len(motors)
    result['motor_input_edges'] = sum(v[0] for v in totals.values())
    result['motor_input_weight'] = sum(v[1] for v in totals.values())
    result['presynaptic_body_ids'] = len(pres)
    result['presynaptic_neuron_labeled_ids'] = len(annotated)
    result['selected_motor_count'] = len(groups)
    result['selected_group_count'] = len(set(groups.values()))
    result['shared_candidate_counts'] = {str(t): sum(len(g) >= 2 for g in v.values()) for t, v in thresholds.items()}
    result['candidate_categories'] = dict(sorted(Counter(r['breadth_category'] for r in candidates.values()).items()))
    result['annotation_sensitivity'] = {'excluded_motor_count':len(excluded), 'retained_candidates':sum(len(v) >= 2 for v in retained.values()), 'studied_retained':sum(len(retained[p]) >= 2 for p in studied), 'studied_lost':sorted(p for p in studied if len(retained[p]) < 2)}
    checks['atlas_per_cell_input_totals'] = set(totals) == set(motors) and all(totals[p] == [int(r['incoming_edges']), int(r['incoming_weight'])] for p, r in motors.items())
    checks['t10_candidate_id_set'] = ids_t10 == set(candidates)
    checks['candidate_group_weights'] = all(len(full[p]) == int(r['group_count']) and sum(full[p].values()) == int(r['selected_motor_weight']) and set(full[p]) == set(r['target_group_ids'].split('|')) for p, r in candidates.items())
    checks['annotation_sensitivity_each_row'] = all(dict(full[r['bodyId']]) == json.loads(r['original_group_weights']) and dict(retained[r['bodyId']]) == json.loads(r['retained_group_weights']) and (len(retained[r['bodyId']]) >= 2) == (r['shared_retained'] == 'True') for r in sensitivity_rows.values())
    io_summary = {}
    for direction, target_col in [('incoming','bodyId_post'),('outgoing','bodyId_pre')]:
        count, weight = 0, 0
        by_cell = {t: defaultdict(lambda:[0,0]) for t in THRESHOLDS}
        keys = set()
        for r in rows(d/f'connectivity/studied_{direction}.csv.gz'):
            key = (r['bodyId_pre'], r['bodyId_post'])
            if key in keys: raise ValueError(f'duplicate {direction} edge: {key}')
            keys.add(key)
            p, w = r[target_col], int(r['weight'])
            count += 1; weight += w
            for t, values in by_cell.items():
                if w >= t: values[p][0] += 1; values[p][1] += w
        expected = [r for r in denominator_rows if r['direction'] == direction]
        checks[f'{direction}_totals_at_each_threshold'] = all(by_cell[int(r['threshold'])][r['target_bodyId']] == [int(r['edge_count']),int(r['weight'])] for r in expected) and set(by_cell[1]) == studied
        io_summary[direction] = {'edges':count,'weight':weight}
    result['studied_cells'] = len(studied)
    result['studied_io'] = io_summary
    inv, ch, pairs = [list(rows(d/f'activity/{f}.csv')) for f in ('inventory','channels','pairs')]
    result['activity'] = {'records':len(inv), 'voltage_channels':len(ch), 'available_seconds':round(sum(float(r['available_ephys_s']) for r in inv),2), 'aligned_seconds':round(sum(float(r['analyzed_s']) for r in inv),2), 'technical_valid_seconds':round(sum(float(r['valid_no_stim_s']) for r in inv),2)}
    # Exact channel labels and pair keys are validated in table_contracts.
    result['dna02_bilateral'] = {p: {r['signal']:float(r['r150']) for r in pairs if r['fly'] == p and r['signal'] in BILATERAL_SIGNALS and r['target'] == 'yaw' and finite(r['r150'], -1, 1)} for p in MAIN_BILATERAL_FLIES}
    checks['dna02_difference_stronger_than_sum'] = all(set(v) == set(BILATERAL_SIGNALS) and abs(v['A_minus_B']) > abs(v['A_plus_B']) for v in result['dna02_bilateral'].values())
    expected = json.loads((d/'expected_summary.json').read_text(encoding='utf-8'))
    checks['published_summary_matches_reaggregation'] = result == expected
    # These correlations are reported table values; no raw-voltage recalculation here.
    return {'schema_version':'fly-neuron-atlas-reproduction/v1','status':'pass' if all(checks.values()) else 'fail','checks':checks,'table_contracts':contracts,'results':result,'scope':'Included snapshot arithmetic and cross-table consistency; activity correlations are read from saved analysis, not re-estimated from raw voltage.'}


if __name__ == '__main__':
    try:
        report = compute()
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        sys.exit(0 if report['status'] == 'pass' else 1)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(json.dumps({'status':'error','message':str(exc)}), file=sys.stderr)
        sys.exit(1)
