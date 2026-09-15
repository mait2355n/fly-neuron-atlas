"""Small independently specified tables challenge identity and edge contracts.

Fixtures exercise saved-table validation only, not voltage analysis or biology.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reproduce import compute
from table_contracts import validate
from verify import verify


def write_rows(root, name, records):
    path = root / 'data' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def fixture(root):
    """Two motor targets, one studied source, three bilateral recordings."""
    tables = {
        'motor_atlas.csv': [dict(dataset='test:v1', bodyId=p, incoming_edges=1, incoming_weight=20) for p in ('1', '2')],
        'motor_groups.csv': [dict(bodyId=p, group_id='group' + p) for p in ('1', '2')],
        'shared_candidates.csv': [dict(dataset='test:v1', bodyId='10', threshold=10, preIsNeuron='True', group_count=2, selected_motor_weight=40, target_group_ids='group1|group2', breadth_category='same_leg_same_joint', full_io_state='complete_previous_same_snapshot')],
        'annotation_sensitivity.csv': [dict(bodyId='10', original_group_weights='{"group1":20,"group2":20}', retained_group_weights='{"group1":20,"group2":20}', shared_retained='True')],
        'connectivity/motor_inputs.csv.gz': [dict(bodyId_pre='10', bodyId_post=p, weight=20, weightHP=18, weightHR=20, preIsNeuron='True') for p in ('1', '2')],
        'connectivity/studied_incoming.csv.gz': [dict(bodyId_pre='10', bodyId_post='10', weight=11, weightHP=9, weightHR=11, preIsNeuron='True', postIsNeuron='True')],
        'studied_totals.csv': [dict(target_bodyId='10', direction=d, threshold=t, edge_count=1 if d == 'incoming' else 3, weight=11 if d == 'incoming' else 51) for d in ('incoming', 'outgoing') for t in (1, 3, 5, 10)],
        'activity/inventory.csv': [dict(fly=p, neurons='a2_l;a2_r', status='usable', available_ephys_s=21, analyzed_s=20.99, valid_no_stim_s=19.99) for p in ('a2_d_08', 'a2_d_12', 'a2_d_13')],
        'activity/channels.csv': [dict(fly=p, neuron=n, type='DNa02', side=s, mat_channel=c, status='usable', main_summary_eligible='True', yaw_r150=-0.3) for p in ('a2_d_08', 'a2_d_12', 'a2_d_13') for n,s,c in [('a2_l','left','ephys_A'),('a2_r','right','ephys_B')]],
        'activity/pairs.csv': [dict(fly=p, kind='bilateral_same_type', signal=s, target=t, r150=r, main_summary_eligible='True') for p in ('a2_d_08', 'a2_d_12', 'a2_d_13') for s,t,r in [('a2_l_rate','a2_r_rate',0.2),('A_minus_B','yaw',-0.6),('A_plus_B','yaw',-0.2)]],
    }
    tables['studied_cells.csv'] = [dict(tables['shared_candidates.csv'][0])]
    tables['connectivity/studied_outgoing.csv.gz'] = [dict(r, postIsNeuron='True') for r in tables['connectivity/motor_inputs.csv.gz']] + [dict(tables['connectivity/studied_incoming.csv.gz'][0])]
    for name, records in tables.items():
        write_rows(root, name, records)
    (root/'data/snapshot.json').write_text(json.dumps(dict(dataset='test:v1', excluded_annotation_only_motor_ids=[])), encoding='utf-8')
    expected = {
        'motor_count':2, 'motor_input_edges':2, 'motor_input_weight':40,
        'presynaptic_body_ids':1, 'presynaptic_neuron_labeled_ids':1,
        'selected_motor_count':2, 'selected_group_count':2,
        'shared_candidate_counts':{str(t):1 for t in (1,3,5,10)},
        'candidate_categories':{'same_leg_same_joint':1},
        'annotation_sensitivity':{'excluded_motor_count':0,'retained_candidates':1,'studied_retained':1,'studied_lost':[]},
        'studied_cells':1, 'studied_io':{'incoming':{'edges':1,'weight':11},'outgoing':{'edges':3,'weight':51}},
        'activity':{'records':3,'voltage_channels':6,'available_seconds':63.0,'aligned_seconds':62.97,'technical_valid_seconds':59.97},
        'dna02_bilateral':{p:{'A_minus_B':-0.6,'A_plus_B':-0.2} for p in ('a2_d_08','a2_d_12','a2_d_13')},
    }
    (root/'data/expected_summary.json').write_text(json.dumps(expected), encoding='utf-8')
    return tables


class TableContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tables = fixture(self.root)

    def edit(self, name, change):
        records = self.tables[name]
        change(records)
        write_rows(self.root, name, records)

    def test_independent_control_passes(self):
        self.assertEqual(compute(self.root)['status'], 'pass')

    def test_equal_total_edge_weight_compensation_rejected(self):
        def change(records):
            records[0]['weight'] = 19
            records[1]['weight'] = 21
        self.edit('connectivity/studied_outgoing.csv.gz', change)
        report = compute(self.root)
        self.assertTrue(report['checks']['outgoing_totals_at_each_threshold'])
        self.assertTrue(report['checks']['published_summary_matches_reaggregation'])
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(report['checks']['motor_inputs_studied_outgoing_edges_match'])

    def test_wrong_channel_identity_same_count_rejected(self):
        self.edit('activity/channels.csv', lambda rr: rr[0].update(neuron='a1_l'))
        report = compute(self.root)
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(report['checks']['activity_record_channel_mapping'])

    def test_wrong_pair_target_rejected(self):
        self.edit('activity/pairs.csv', lambda rr: rr[1].update(target='fwd'))
        report = compute(self.root)
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(report['checks']['activity_pair_identities'])
        self.assertNotIn('A_minus_B', report['results']['dna02_bilateral']['a2_d_08'])

    def test_missing_overlap_edge_rejected_even_if_remaining_weights_match(self):
        self.edit('connectivity/studied_outgoing.csv.gz', lambda rr: rr.pop(0))
        report = validate(self.root)
        comparison = report['edge_comparisons']['motor_inputs_studied_outgoing_edges_match']
        self.assertEqual(comparison['missing_from_right'], 1)
        self.assertEqual(comparison['weight_conflicts'], 0)
        self.assertEqual(report['status'], 'fail')

    def test_incoming_outgoing_weight_conflict_rejected(self):
        self.edit('connectivity/studied_incoming.csv.gz', lambda rr: rr[0].update(weight=12))
        report = validate(self.root)
        self.assertFalse(report['checks']['studied_incoming_studied_outgoing_edges_match'])

    def test_motor_incoming_overlap_when_target_is_studied(self):
        # Exercise the third overlap rule with an explicitly expanded target
        # scope. This contract fixture is not a biological candidate claim.
        for name in ('shared_candidates.csv', 'studied_cells.csv'):
            self.edit(name, lambda rr: rr.append(dict(rr[0], bodyId='1')))
        self.edit('connectivity/studied_incoming.csv.gz', lambda rr: rr.append(dict(rr[0], bodyId_post='1', weight=19)))
        comparison = validate(self.root)['edge_comparisons']['motor_inputs_studied_incoming_edges_match']
        self.assertEqual(comparison['left_edges'], 1)
        self.assertEqual(comparison['right_edges'], 1)
        self.assertEqual(comparison['weight_conflicts'], 1)

    def test_hp_hr_conflicts_rejected_without_total_weight_change(self):
        for field in ('weightHP', 'weightHR'):
            with self.subTest(field=field):
                records = self.tables['connectivity/studied_outgoing.csv.gz']
                original = records[0][field]
                records[0][field] = int(original) + 1
                write_rows(self.root, 'connectivity/studied_outgoing.csv.gz', records)
                self.assertFalse(validate(self.root)['checks']['motor_inputs_studied_outgoing_edges_match'])
                records[0][field] = original

    def test_motor_input_duplicate_rejected(self):
        self.edit('connectivity/motor_inputs.csv.gz', lambda rr: rr.append(dict(rr[0])))
        self.assertFalse(validate(self.root)['checks']['table_primary_keys'])

    def test_dataset_identity_substitution_rejected(self):
        self.edit('motor_atlas.csv', lambda rr: rr[0].update(dataset='different:v1'))
        self.assertFalse(validate(self.root)['checks']['table_dataset_scope'])

    def test_edge_endpoint_outside_declared_scope_rejected(self):
        self.edit('connectivity/motor_inputs.csv.gz', lambda rr: rr[0].update(bodyId_post='999'))
        self.assertFalse(validate(self.root)['checks']['edge_endpoint_references'])

    def test_unknown_weight_is_not_zero(self):
        self.edit('connectivity/motor_inputs.csv.gz', lambda rr: rr[0].update(weight=''))
        report = validate(self.root)
        self.assertFalse(report['checks']['table_scalar_values'])
        self.assertEqual(report['edge_comparisons']['motor_inputs_studied_outgoing_edges_match']['weight_conflicts'], 1)

    def test_noncanonical_integer_and_boolean_rejected(self):
        self.edit('connectivity/motor_inputs.csv.gz', lambda rr: rr[0].update(weight='20.0', preIsNeuron='maybe'))
        self.assertFalse(validate(self.root)['checks']['table_scalar_values'])

    def test_duplicate_activity_pair_rejected(self):
        self.edit('activity/pairs.csv', lambda rr: rr.append(dict(rr[0])))
        report = validate(self.root)
        self.assertFalse(report['checks']['table_primary_keys'])
        self.assertFalse(report['checks']['activity_pair_identities'])

    def test_missing_nonprincipal_pair_key_rejected(self):
        self.edit('activity/pairs.csv', lambda rr: rr.pop(0))
        self.assertFalse(validate(self.root)['checks']['activity_pair_identities'])

    def test_channel_annotation_substitution_rejected(self):
        self.edit('activity/channels.csv', lambda rr: rr[0].update(mat_channel='ephys_B'))
        self.assertFalse(validate(self.root)['checks']['activity_channel_annotations'])

    def test_nonfinite_pair_value_rejected_and_not_serialized_as_nan(self):
        self.edit('activity/pairs.csv', lambda rr: rr[1].update(r150='nan'))
        report = compute(self.root)
        self.assertFalse(report['checks']['table_scalar_values'])
        self.assertFalse(report['checks']['dna02_difference_stronger_than_sum'])
        json.dumps(report, allow_nan=False)

    def test_excluded_principal_channel_cannot_enter_main_summary(self):
        self.edit('activity/channels.csv', lambda rr: rr[0].update(status='excluded', main_summary_eligible='False'))
        report = validate(self.root)
        self.assertFalse(report['checks']['dna02_bilateral_summary_eligible'])
        self.assertFalse(report['checks']['activity_pair_identities'])

    def prepare_integrity_metadata(self):
        """Refresh fixture hashes to isolate semantics from integrity checks."""
        entries = []
        for name, records in self.tables.items():
            entries.append(dict(path='data/' + name, format='csv', columns=list(records[0]), rows=len(records), source_ids=['fixture']))
        (self.root/'data/provenance.json').write_text(json.dumps({'entries': entries}), encoding='utf-8')
        (self.root/'data/sources.json').write_text(json.dumps({'sources': [{'id':'fixture'}]}), encoding='utf-8')
        files = []
        for path in sorted((self.root/'data').rglob('*')):
            if path.is_file():
                content = path.read_bytes()
                files.append(dict(path=str(path.relative_to(self.root)), bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
        (self.root/'MANIFEST.json').write_text(json.dumps({'files': files}), encoding='utf-8')

    def test_verify_rejects_identity_fault_with_valid_fresh_hashes(self):
        self.prepare_integrity_metadata()
        self.assertEqual(verify(self.root)['status'], 'pass')
        self.edit('activity/channels.csv', lambda rr: rr[0].update(neuron='a1_l'))
        self.prepare_integrity_metadata()
        report = verify(self.root)
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(any('hash/size mismatch' in failure for failure in report['failures']))
        self.assertFalse(report['table_contracts']['checks']['activity_record_channel_mapping'])

    def test_verify_public_cli_rejects_weight_conflict_with_valid_hashes(self):
        self.edit('connectivity/studied_outgoing.csv.gz', lambda rr: rr[0].update(weight=19))
        self.prepare_integrity_metadata()
        scripts = self.root/'scripts'
        scripts.mkdir()
        for name in ('verify.py', 'table_contracts.py'):
            (scripts/name).write_bytes((ROOT/'scripts'/name).read_bytes())
        run = subprocess.run([sys.executable, str(scripts/'verify.py')], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(any('hash/size mismatch' in failure for failure in report['failures']))
        self.assertFalse(report['table_contracts']['checks']['motor_inputs_studied_outgoing_edges_match'])


if __name__ == '__main__':
    unittest.main()
