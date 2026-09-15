"""Explicit contracts for the structural and activity tables used by reproduce.

The dataset in snapshot.json scopes tables without a dataset column. These
checks validate a saved observation scope; absence outside that scope is unknown.
"""
import csv
import gzip
import json
import math
import re
from collections import Counter

THRESHOLDS = (1, 3, 5, 10)
COMPLETE_IO_STATES = {'complete_previous_same_snapshot', 'complete_additional_same_snapshot'}
MAIN_BILATERAL_FLIES = ('a2_d_08', 'a2_d_12', 'a2_d_13')
BILATERAL_SIGNALS = ('A_minus_B', 'A_plus_B')
NEURONS = {
    'a1_l': ('DNa01', 'left'), 'a1_r': ('DNa01', 'right'),
    'a2_l': ('DNa02', 'left'), 'a2_r': ('DNa02', 'right'),
}
WEIGHTS = ('weight', 'weightHP', 'weightHR')


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f'missing or duplicate CSV header: {path.name}')
        for number, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'malformed CSV: {path.name}:{number}')
            yield row


def integer(value, minimum=0):
    return isinstance(value, str) and re.fullmatch(r'0|[1-9][0-9]*', value) is not None and int(value) >= minimum


def finite(value, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and (minimum is None or number >= minimum) and (maximum is None or number <= maximum)


def validate(root):
    """Return bounded diagnostics; never change tables or fill unknown values."""
    data = root / 'data'
    snapshot = json.loads((data / 'snapshot.json').read_text(encoding='utf-8'))
    dataset = snapshot['dataset']
    checks, failures, comparisons = {}, [], {}

    def check(code, ok, detail=''):
        checks[code] = checks.get(code, True) and bool(ok)
        if not ok and len(failures) < 30:
            failures.append(code + (': ' + detail if detail else ''))

    def unique(records, columns, table):
        keys = [tuple(r[k] for k in columns) for r in records]
        check('table_primary_keys', len(keys) == len(set(keys)), table)

    def scalar(records, table, ints=(), enums=None, numbers=()):
        for i, r in enumerate(records, 2):
            ok = all(integer(r[k], minimum) for k, minimum in ints)
            ok = ok and all(r[k] in values for k, values in (enums or {}).items())
            ok = ok and all(finite(r[k], low, high) for k, low, high in numbers)
            check('table_scalar_values', ok, f'{table}:{i}')

    check('table_dataset_scope', isinstance(dataset, str) and bool(dataset))
    tables = {name: list(rows(data / (name + '.csv'))) for name in (
        'motor_atlas', 'motor_groups', 'shared_candidates', 'studied_cells',
        'annotation_sensitivity', 'studied_totals',
        'activity/inventory', 'activity/channels', 'activity/pairs')}
    for name in ('motor_atlas', 'motor_groups', 'shared_candidates', 'studied_cells', 'annotation_sensitivity'):
        unique(tables[name], ('bodyId',), name)
        scalar(tables[name], name, ints=(('bodyId', 1),))
    for name in ('motor_atlas', 'shared_candidates', 'studied_cells'):
        check('table_dataset_scope', all(r['dataset'] == dataset for r in tables[name]), name)
    scalar(tables['motor_atlas'], 'motor_atlas', ints=(('incoming_edges', 0), ('incoming_weight', 0)))
    for name in ('shared_candidates', 'studied_cells'):
        scalar(tables[name], name, ints=(('group_count', 2), ('selected_motor_weight', 1)), enums={
            'threshold': {'10'}, 'preIsNeuron': {'True'},
            'full_io_state': COMPLETE_IO_STATES | {'not_fetched_in_this_study'},
        })
    motors = {r['bodyId'] for r in tables['motor_atlas']}
    candidates = {r['bodyId']: r for r in tables['shared_candidates']}
    studied = {r['bodyId']: r for r in tables['studied_cells']}
    group_ids = {r['group_id'] for r in tables['motor_groups']}
    check('motor_group_members_are_in_atlas', {r['bodyId'] for r in tables['motor_groups']} <= motors)
    check('table_group_references', all(r['group_id'] for r in tables['motor_groups']) and all(
        len(r['target_group_ids'].split('|')) == len(set(r['target_group_ids'].split('|')))
        and set(r['target_group_ids'].split('|')) <= group_ids for r in candidates.values()))
    check('studied_cell_selection_matches_candidates', set(studied) == {
        p for p, r in candidates.items() if r['full_io_state'] in COMPLETE_IO_STATES
    } and all(r == candidates.get(p) for p, r in studied.items()))
    check('annotation_sensitivity_candidate_set', {r['bodyId'] for r in tables['annotation_sensitivity']} == set(candidates))
    scalar(tables['annotation_sensitivity'], 'annotation_sensitivity', enums={'shared_retained': {'True', 'False'}})
    for r in tables['annotation_sensitivity']:
        for field in ('original_group_weights', 'retained_group_weights'):
            weights = json.loads(r[field])
            check('table_group_references', isinstance(weights, dict) and set(weights) <= group_ids and all(
                type(v) is int and v > 0 for v in weights.values()), field)
    denominators = tables['studied_totals']
    scalar(denominators, 'studied_totals', ints=(('target_bodyId', 1), ('edge_count', 0), ('weight', 0)), enums={
        'direction': {'incoming', 'outgoing'}, 'threshold': {str(t) for t in THRESHOLDS},
    })
    unique(denominators, ('target_bodyId', 'direction', 'threshold'), 'studied_totals')
    check('studied_denominator_grid_complete', Counter(
        (r['target_bodyId'], r['direction'], r['threshold']) for r in denominators
    ) == Counter((p, direction, str(t)) for p in studied for direction in ('incoming', 'outgoing') for t in THRESHOLDS))

    edges = {}
    for name, endpoint, targets in (
        ('motor_inputs', 'bodyId_post', motors),
        ('studied_incoming', 'bodyId_post', set(studied)),
        ('studied_outgoing', 'bodyId_pre', set(studied)),
    ):
        index = {}
        for r in rows(data / 'connectivity' / (name + '.csv.gz')):
            key = (dataset, r['bodyId_pre'], r['bodyId_post'])
            check('table_dataset_scope', r.get('dataset', dataset) == dataset, name)
            check('table_primary_keys', key not in index, f'{name} {key}')
            scalar([r], name, ints=(('bodyId_pre', 1), ('bodyId_post', 1), ('weight', 1), ('weightHP', 0), ('weightHR', 0)), enums={
                k: {'True', 'False'} for k in ('preIsNeuron', 'postIsNeuron') if k in r
            })
            check('edge_endpoint_references', r[endpoint] in targets, f'{name} {key}')
            # Invalid scalars have already failed. Keep their text for comparison;
            # never make an unknown/missing weight into a numerical zero.
            index[key] = tuple(r[k] for k in WEIGHTS)
        edges[name] = index
    for left, right, keep in (
        ('motor_inputs', 'studied_outgoing', lambda k: k[1] in studied and k[2] in motors),
        ('studied_incoming', 'studied_outgoing', lambda k: k[1] in studied and k[2] in studied),
        ('motor_inputs', 'studied_incoming', lambda k: k[2] in motors and k[2] in studied),
    ):
        a = {k: v for k, v in edges[left].items() if keep(k)}
        b = {k: v for k, v in edges[right].items() if keep(k)}
        missing_right, missing_left = a.keys() - b.keys(), b.keys() - a.keys()
        conflicts = [k for k in a.keys() & b.keys() if a[k] != b[k]]
        code = left + '_' + right + '_edges_match'
        check(code, not missing_right and not missing_left and not conflicts)
        comparisons[code] = {
            'left_edges': len(a), 'right_edges': len(b),
            'missing_from_right': len(missing_right), 'missing_from_left': len(missing_left),
            'weight_conflicts': len(conflicts), 'weight_fields': list(WEIGHTS),
            'scope_status': 'checked' if a or b else 'no_overlapping_observations',
            'examples': [{'key': list(k), 'left': a.get(k), 'right': b.get(k)}
                         for k in sorted(missing_right | missing_left | set(conflicts))[:5]],
        }

    inv, channels, pairs = [tables['activity/' + name] for name in ('inventory', 'channels', 'pairs')]
    unique(inv, ('fly',), 'activity/inventory')
    unique(channels, ('fly', 'neuron'), 'activity/channels')
    unique(pairs, ('fly', 'signal', 'target'), 'activity/pairs')
    scalar(inv, 'activity/inventory', enums={'status': {'usable', 'excluded'}})
    scalar(channels, 'activity/channels', enums={'status': {'usable', 'excluded'}, 'neuron': set(NEURONS)})
    expected_channels, expected_pairs, pair_kinds = Counter(), Counter(), {}
    channel_by_key = {(r['fly'], r['neuron']): r for r in channels}
    for r in inv:
        labels = r['neurons'].split(';') if r['neurons'] else []
        check('activity_inventory_labels', bool(r['fly']) and len(labels) == len(set(labels)) and set(labels) <= set(NEURONS)
              and (r['status'] != 'usable' or 1 <= len(labels) <= 2), r['fly'])
        expected_channels.update((r['fly'], label) for label in labels)
        for i, label in enumerate(labels):
            channel = channel_by_key.get((r['fly'], label), {})
            expected_type, expected_side = NEURONS.get(label, ('', ''))
            check('activity_channel_annotations', channel.get('type') == expected_type and channel.get('side') == expected_side
                  and channel.get('mat_channel') == ('ephys_A' if i == 0 else 'ephys_B'), f"{r['fly']} {label}")
        if r['status'] == 'usable':
            scalar([r], 'activity/inventory', numbers=tuple((k, 0, None) for k in ('available_ephys_s', 'analyzed_s', 'valid_no_stim_s')))
            if all(finite(r[k], 0) for k in ('available_ephys_s', 'analyzed_s', 'valid_no_stim_s')):
                check('activity_duration_order', float(r['valid_no_stim_s']) <= float(r['analyzed_s']) <= float(r['available_ephys_s']), r['fly'])
        if r['status'] == 'usable' and len(labels) == 2 and all(channel_by_key.get((r['fly'], n), {}).get('status') == 'usable' for n in labels):
            expected_pairs.update([(r['fly'], labels[0] + '_rate', labels[1] + '_rate')]
                                  + [(r['fly'], s, 'yaw') for s in BILATERAL_SIGNALS])
            pair_kinds[r['fly']] = 'bilateral_same_type' if labels[0][:2] == labels[1][:2] else 'same_side_cross_type'
    check('activity_record_channel_mapping', expected_channels == Counter((r['fly'], r['neuron']) for r in channels))
    check('activity_pair_identities', expected_pairs == Counter((r['fly'], r['signal'], r['target']) for r in pairs))
    check('activity_pair_kinds', all(r['kind'] == pair_kinds.get(r['fly']) for r in pairs))
    for r in channels:
        if r['status'] == 'usable':
            scalar([r], 'activity/channels', enums={'main_summary_eligible': {'True', 'False'}}, numbers=(('yaw_r150', -1, 1),))
        else:
            check('activity_exclusion_state', r.get('main_summary_eligible', '') in ('', 'False'), r['fly'])
    scalar(pairs, 'activity/pairs', enums={'main_summary_eligible': {'True', 'False'}, 'kind': {'bilateral_same_type', 'same_side_cross_type'}}, numbers=(('r150', -1, 1),))
    main = [r for r in pairs if r['fly'] in MAIN_BILATERAL_FLIES and r['signal'] in BILATERAL_SIGNALS and r['target'] == 'yaw']
    check('dna02_bilateral_summary_keys', Counter((r['fly'], r['signal'], r['target']) for r in main) == Counter(
        (p, s, 'yaw') for p in MAIN_BILATERAL_FLIES for s in BILATERAL_SIGNALS))
    check('dna02_bilateral_summary_eligible', all(r['kind'] == 'bilateral_same_type' and r['main_summary_eligible'] == 'True' for r in main)
          and all(channel_by_key.get((p, n), {}).get('main_summary_eligible') == 'True' for p in MAIN_BILATERAL_FLIES for n in ('a2_l', 'a2_r')))
    return {'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks,
            'failures': failures, 'edge_comparisons': comparisons,
            'scope': 'Explicit contracts for reproduce input tables; other provenance tables receive shape and hash checks in verify.'}
