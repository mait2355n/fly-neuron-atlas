"""Exercise the public CLI with isolated missing/duplicate research records.

These checks target table completeness after curation, independently of file
checksums. They do not change the published data or validate biological claims.
"""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReproductionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'data', self.root / 'data')
        (self.root / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/reproduce.py', self.root / 'scripts/reproduce.py')

    def edit_table(self, name, transform):
        path = self.root / 'data' / name
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, records = reader.fieldnames, list(reader)
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(transform(records))

    def run_cli(self):
        run = subprocess.run(
            [sys.executable, str(self.root / 'scripts/reproduce.py')],
            cwd=self.root, capture_output=True, text=True, timeout=90,
        )
        return run, json.loads(run.stdout or run.stderr)

    def assert_check_rejected(self, check):
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'fail')
        self.assertIs(report['checks'][check], False)

    def test_complete_snapshot_passes(self):
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'pass')

    def test_missing_threshold_denominator_is_rejected(self):
        self.edit_table('studied_totals.csv', lambda rows: rows[1:])
        self.assert_check_rejected('studied_denominator_grid_complete')

    def test_duplicate_threshold_denominator_is_rejected(self):
        self.edit_table('studied_totals.csv', lambda rows: rows + [rows[0]])
        self.assert_check_rejected('studied_denominator_grid_complete')

    def test_missing_annotation_candidate_is_rejected(self):
        self.edit_table('annotation_sensitivity.csv', lambda rows: rows[1:])
        self.assert_check_rejected('annotation_sensitivity_candidate_set')

    def test_missing_studied_cell_is_rejected(self):
        self.edit_table('studied_cells.csv', lambda rows: rows[1:])
        self.assert_check_rejected('studied_cell_selection_matches_candidates')

    def test_changed_studied_cell_annotation_is_rejected(self):
        def change(records):
            records[0]['preType'] = 'incorrect-type-for-this-bodyId'
            return records
        self.edit_table('studied_cells.csv', change)
        self.assert_check_rejected('studied_cell_selection_matches_candidates')

    def test_duplicate_candidate_identity_is_rejected(self):
        self.edit_table('shared_candidates.csv', lambda rows: rows + [rows[0]])
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'error')
        self.assertIn('duplicate bodyId in shared_candidates.csv', report['message'])


if __name__ == '__main__':
    unittest.main()
