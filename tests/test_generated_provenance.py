"""Generated-table semantics remain enforced after row/hash metadata refresh."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_table_contracts import fixture, write_rows

ROOT = Path(__file__).resolve().parents[1]


class GeneratedProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tables = fixture(self.root)
        self.generated = [dict(r) for r in self.tables['activity/channels.csv']]
        self.generated_entries = [
            {'path':'data/reanalysis/channels.csv', 'format':'csv',
             'columns':list(self.generated[0]), 'rows':len(self.generated),
             'source_ids':['fixture'], 'primary_key':['fly','neuron'],
             'identity_reference':'data/activity/channels.csv', 'finite_columns':['yaw_r150']},
            {'path':'data/reanalysis/RUN.json', 'format':'json',
             'top_level_keys':['status','records'], 'source_ids':['fixture']},
        ]
        scripts = self.root/'scripts'
        scripts.mkdir()
        for name in ('verify.py','table_contracts.py'):
            shutil.copy2(ROOT/'scripts'/name, scripts/name)
        (self.root/'data/reanalysis').mkdir()
        (self.root/'data/reanalysis/RUN.json').write_text(
            json.dumps({'status':'pass','records':len(self.generated)})+'\n', encoding='utf-8')

    def refresh_metadata(self, with_generated=True):
        """Model recuration: hashes and row counts agree with the changed input."""
        entries = [dict(path='data/'+name, format='csv', columns=list(records[0]),
                        rows=len(records), source_ids=['fixture'])
                   for name,records in self.tables.items()]
        (self.root/'data/provenance.json').write_text(json.dumps({'entries':entries}), encoding='utf-8')
        (self.root/'data/sources.json').write_text(json.dumps({'sources':[{'id':'fixture'}]}), encoding='utf-8')
        write_rows(self.root, 'reanalysis/channels.csv', self.generated)
        self.generated_entries[0]['rows'] = len(self.generated)
        self.generated_entries[0]['columns'] = list(self.generated[0])
        if with_generated:
            (self.root/'data/reanalysis/PROVENANCE.json').write_text(
                json.dumps({'entries':self.generated_entries}), encoding='utf-8')
        files = []
        for path in sorted((self.root/'data').rglob('*')):
            if path.is_file():
                body = path.read_bytes()
                files.append(dict(path=str(path.relative_to(self.root)), bytes=len(body),
                                  sha256=hashlib.sha256(body).hexdigest()))
        (self.root/'MANIFEST.json').write_text(json.dumps({'files':files}), encoding='utf-8')

    def run_cli(self):
        run = subprocess.run([sys.executable, str(self.root/'scripts/verify.py')],
                             cwd=self.root, capture_output=True, text=True,
                             encoding='utf-8', timeout=30)
        return run, json.loads(run.stdout or run.stderr)

    def assert_contract_failure(self, message):
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'fail')
        self.assertFalse(any('hash/size mismatch' in f or 'table shape:' in f for f in report['failures']))
        self.assertTrue(any(message in f for f in report['failures']), report['failures'])
        self.assertEqual(report['tables'], len(self.tables))
        self.assertEqual(report['generated_artifacts'], 2)

    def test_legacy_fixture_without_generated_metadata_still_passes(self):
        self.refresh_metadata(with_generated=False)
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['tables'], len(self.tables))
        self.assertEqual(report['generated_artifacts'], 0)

    def test_generated_control_preserves_original_table_count(self):
        self.refresh_metadata()
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['tables'], len(self.tables))
        self.assertEqual(report['generated_artifacts'], 2)

    def test_duplicate_key_rejected_after_rows_and_hashes_are_refreshed(self):
        self.generated.append(dict(self.generated[0]))
        self.refresh_metadata()
        self.assert_contract_failure('duplicate primary key')

    def test_different_fly_rejected_with_same_count_and_fresh_hashes(self):
        self.generated[0]['fly'] = 'a2_d_14'
        self.refresh_metadata()
        self.assert_contract_failure('identity reference mismatch')

    def test_nonfinite_required_values_rejected_with_fresh_hashes(self):
        for value in ('nan','inf',''):
            with self.subTest(value=value):
                self.generated[0]['yaw_r150'] = value
                self.refresh_metadata()
                self.assert_contract_failure('nonfinite required column')

    def test_empty_primary_key_is_rejected(self):
        self.generated[0]['fly'] = ' '
        self.refresh_metadata()
        self.assert_contract_failure('empty primary key')

    def test_primary_key_only_does_not_require_unclaimed_finite_metrics(self):
        self.generated[0]['yaw_r150'] = ''
        self.generated_entries[0].pop('finite_columns')
        self.generated_entries[0].pop('identity_reference')
        self.refresh_metadata()
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'pass')

    def test_generated_json_shape_uses_existing_validation(self):
        (self.root/'data/reanalysis/RUN.json').write_text(
            json.dumps({'status':'pass','other':6}), encoding='utf-8')
        self.refresh_metadata()
        self.assert_contract_failure('JSON top-level shape')

    def test_generated_json_and_csv_source_ids_use_existing_validation(self):
        for entry in self.generated_entries:
            entry['source_ids'] = ['unknown-source']
        self.refresh_metadata()
        run, report = self.run_cli()
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(sum('unknown source id' in f for f in report['failures']), 2)
        self.assertFalse(any('hash/size mismatch' in f for f in report['failures']))


if __name__ == '__main__':
    unittest.main()
