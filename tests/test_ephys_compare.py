"""Independent known-bad saved-table fixtures through the public comparison CLI."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.reference = Path(self.temp.name) / 'reference'
        self.generated = Path(self.temp.name) / 'generated'
        self.reference.mkdir()
        # Fixed published reference, selected and copied before introducing faults.
        for name in ('inventory', 'channels', 'pairs', 'lag_curves'):
            with (ROOT / 'data/activity' / (name + '.csv')).open(encoding='utf-8', newline='') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = [r for r in reader if r['fly'] == 'a2_d_08']
            self.write(self.reference, name, fields, rows)
        shutil.copytree(self.reference, self.generated)

    def write(self, directory, name, fields, rows):
        with (directory / (name + '.csv')).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def edit(self, name, change, directory=None):
        directory = directory or self.generated
        with (directory / (name + '.csv')).open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        rows = change(rows)
        fields = list(dict.fromkeys(fields + [k for r in rows for k in r]))
        self.write(directory, name, fields, rows)

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/compare_ephys.py'),
                               '--generated', str(self.generated), '--reference', str(self.reference),
                               *args], capture_output=True, text=True, timeout=15)
        return proc.returncode, json.loads(proc.stdout)

    def test_reference_control(self):
        code, result = self.run_cli()
        self.assertEqual(code, 0, result)

    def test_missing_file(self):
        (self.generated / 'pairs.csv').unlink()
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result['tables']['pairs']['missing_files'], ['generated'])

    def test_missing_row(self):
        self.edit('channels', lambda rows: rows[1:])
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result['tables']['channels']['missing_rows'], [['a2_d_08', 'a2_l']])

    def test_extra_row(self):
        self.edit('channels', lambda rows: rows + [{**rows[0], 'neuron': 'unexpected'}])
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result['tables']['channels']['extra_rows'], [['a2_d_08', 'unexpected']])

    def test_extra_fly_cannot_be_hidden_by_selection(self):
        self.edit('inventory', lambda rows: rows + [{**rows[0], 'fly': 'unexpected'}])
        code, result = self.run_cli('--fly', 'a2_d_08')
        self.assertEqual(code, 1)
        self.assertEqual(result['tables']['inventory']['extra_rows'], [['unexpected']])

    def test_equal_malformed_numeric_values_fail(self):
        for directory in (self.reference, self.generated):
            self.edit('channels', lambda rows: [{**r, 'spikes': 'invalid'} for r in rows], directory)
        self.assertEqual(self.run_cli()[0], 1)

    def test_duplicate_row(self):
        self.edit('pairs', lambda rows: rows + [rows[0]])
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(len(result['tables']['pairs']['duplicate_keys']['generated']), 1)

    def test_wrong_target_same_count(self):
        self.edit('pairs', lambda rows: [{**rows[0], 'target': 'fwd'}] + rows[1:])
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(len(result['tables']['pairs']['missing_rows']), 1)
        self.assertEqual(len(result['tables']['pairs']['extra_rows']), 1)

    def test_tolerance(self):
        self.edit('channels', lambda rows: [{**r, 'yaw_r150': str(float(r['yaw_r150']) + 1e-5)} for r in rows])
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.run_cli('--atol', '0.00002')[0], 0)

    def test_per_column_nan_and_infinity(self):
        for directory in (self.reference, self.generated):
            self.edit('channels', lambda rows: [{**r, 'yaw_r150': 'nan'} for r in rows], directory)
        self.edit('channels', lambda rows: [{**r, 'yaw_r150': ''} for r in rows])
        self.assertEqual(self.run_cli()[0], 0)
        self.edit('channels', lambda rows: [{**r, 'yaw_r150': '0'} for r in rows])
        self.assertEqual(self.run_cli()[0], 1)
        for directory in (self.reference, self.generated):
            self.edit('channels', lambda rows: [{**r, 'yaw_r150': 'inf'} for r in rows], directory)
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(result['tables']['channels']['differences'][0]['reason'], 'infinity_forbidden')

    def test_nan_count_is_not_equal(self):
        for directory in (self.reference, self.generated):
            self.edit('channels', lambda rows: [{**r, 'spikes': 'nan'} for r in rows], directory)
        self.assertEqual(self.run_cli()[0], 1)

    def test_runtime_excluded(self):
        self.edit('inventory', lambda rows: [{**r, 'processing_seconds': '1234'} for r in rows])
        self.assertEqual(self.run_cli()[0], 0)

    def test_excluded_channels_are_reported(self):
        for directory in (self.reference, self.generated):
            self.edit('channels', lambda rows: [{k: r[k] if k in ('fly', 'neuron') else
                'excluded' if k == 'status' else '' for k in r} for r in rows], directory)
        code, result = self.run_cli()
        self.assertEqual(code, 0, result)
        self.assertEqual(len(result['tables']['channels']['excluded_records']['generated']), 2)

    def test_run_selection_is_explicit_and_unknown_rejected(self):
        (self.generated / 'RUN.json').write_text(json.dumps({'selected_flies': ['absent']}), encoding='utf-8')
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli('--fly', 'a2_d_08')[0], 0)

    def test_missing_scientific_column(self):
        path = self.generated / 'channels.csv'
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            fields = [f for f in reader.fieldnames if f != 'yaw_r150']
            rows = [{k: v for k, v in r.items() if k != 'yaw_r150'} for r in reader]
        self.write(self.generated, 'channels', fields, rows)
        code, result = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn('yaw_r150', result['tables']['channels']['missing_columns']['generated'])


if __name__ == '__main__':
    unittest.main()
