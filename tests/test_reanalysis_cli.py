"""Public raw-reanalysis CLI checks with artificial, local-only MATLAB records.

The fixtures and injected core-result faults test availability reporting and
wrapper rejection. They do not establish biological spike-detection accuracy.
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import numpy as np
    import scipy
    import matplotlib
    from scipy.io import loadmat, savemat
except ImportError as exc:
    raise unittest.SkipTest("requires the pinned requirements-ephys.txt numerical environment") from exc

from ephys_fixtures import synthetic_record

ROOT = Path(__file__).resolve().parents[1]
BASE_TABLE_KEYS = {
    'inventory': {'fly'},
    'channels': {'fly', 'neuron'},
    'pairs': {'fly', 'signal', 'target'},
    'lag_curves': {'fly', 'signal', 'target', 'lag_ms', 'r'},
    'sensitivity': {'fly', 'neuron', 'prominence_multiplier'},
}
PAIR_KEYS = {
    ('a2_d_08', 'a2_l_rate', 'a2_r_rate'),
    ('a2_d_08', 'A_minus_B', 'yaw'),
    ('a2_d_08', 'A_plus_B', 'yaw'),
}


def prepare_cli_case(root, case, source_scripts=ROOT / 'scripts'):
    """Build an isolated checkout and genuine small MAT plus matching manifest."""
    root = Path(root)
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    for name in ('ephys_core.py', 'reanalyze_ephys.py'):
        shutil.copy2(source_scripts / name, scripts / name)
    raw, output = root / 'raw', root / 'output'
    entry = synthetic_record(raw, 'all_stim_on' if case == 'too_few_valid_samples' else case)
    source = raw / entry['dataFile']['filename']
    if case == 'too_few_valid_samples':
        # A long voltage recording has only a one-second known-off interval.
        # Stimulus guards and the 150 ms lag leave fewer than 100 valid pairs.
        values = {k: v for k, v in loadmat(source).items() if not k.startswith('__')}
        values['stim'].reshape(-1)[5000:6000] = 0.
        savemat(source, values)
    file_info = entry['dataFile']
    selected = {
        'fly': 'a2_d_08', 'filename': file_info['filename'],
        'file_id': file_info['id'], 'bytes': source.stat().st_size,
        'md5': hashlib.md5(source.read_bytes()).hexdigest(),
        'url': 'https://example.invalid/synthetic-input-must-not-be-downloaded',
    }
    metadata = root / 'data/activity'
    metadata.mkdir(parents=True)
    (metadata / 'download_manifest.json').write_text(
        json.dumps({'files': [selected]}) + '\n', encoding='utf-8')
    return raw, output


def execute_cli(root, raw, output, mpl_config=None):
    env = dict(os.environ, MPLBACKEND='Agg')
    # A test run may share its own plotting cache; no shared-home writes occur.
    env['MPLCONFIGDIR'] = str(mpl_config or root / 'matplotlib-cache')
    return subprocess.run(
        [sys.executable, str(root / 'scripts/reanalyze_ephys.py'),
         '--fly', 'a2_d_08', '--raw-dir', str(raw), '--output', str(output)],
        cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90,
    )


def read_table(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def inject_core_result_fault(root, fault):
    # Modify only the copied core in the temporary fixture checkout.
    path = root / 'scripts/ephys_core.py'
    with path.open('a', encoding='utf-8') as stream:
        stream.write('\n_original_run_file = run_file\ndef run_file(entry):\n'
                     '    result = _original_run_file(entry)\n'
                     '    ' + fault + '\n    return result\n')


class ReanalysisCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plotting_cache = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.plotting_cache.cleanup)

    def run_case(self, case='finite_control', fault=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        raw, output = prepare_cli_case(root, case)
        if fault is not None:
            # The source checkout stays unchanged. This fault enters at the
            # core-result boundary while the actual CLI remains unmodified.
            inject_core_result_fault(root, fault)
        run = execute_cli(root, raw, output, Path(self.plotting_cache.name))
        self.assertTrue((output / 'RUN.json').is_file(), run.stdout + run.stderr)
        report = json.loads((output / 'RUN.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads(run.stdout), report)
        self.assertEqual(report['schema_version'], 'fly-neuron-atlas-ephys-run/v2')
        self.assertEqual(report['selected_records'], 1)
        self.assertEqual(report['selected_flies'], ['a2_d_08'])
        self.assertEqual(report['processed_records'], 1)
        self.assertEqual(report['processing_status'], 'completed')
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['code_hashes'], {
            'scripts/' + name: hashlib.sha256((root / 'scripts' / name).read_bytes()).hexdigest()
            for name in ('ephys_core.py', 'reanalyze_ephys.py')
        })
        self.assertEqual(report['source_hashes'][0]['sha256'], hashlib.sha256((raw / 'a2_d_08.mat').read_bytes()).hexdigest())
        tables = {}
        for name, keys in BASE_TABLE_KEYS.items():
            path = output / (name + '.csv')
            self.assertTrue(path.is_file(), name)
            fields, tables[name] = read_table(path)
            self.assertIsNotNone(fields, name + ' must have a header even with no rows')
            self.assertTrue(keys <= set(fields), (name, fields))
        self.assertEqual(len(tables['inventory']), 1)
        self.assertEqual(tables['inventory'][0]['processing_status'], 'completed')
        return run, report, tables

    def assert_not_main_summary(self, tables):
        self.assertEqual(tables['inventory'][0]['analysis_complete'], 'False')
        self.assertEqual(tables['inventory'][0]['main_summary_eligible'], 'False')
        for row in tables['channels'] + tables['pairs']:
            self.assertEqual(row['main_summary_eligible'], 'False')

    def test_finite_control_produces_complete_usable_pair_identities(self):
        run, report, tables = self.run_case()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['analysis_status'], 'usable')
        self.assertEqual((report['usable_records'], report['partial_records'], report['excluded_records']), (1, 0, 0))
        self.assertEqual(tables['inventory'][0]['analysis_complete'], 'True')
        self.assertEqual(tables['inventory'][0]['main_summary_eligible'], 'True')
        self.assertEqual({(r['fly'], r['neuron']) for r in tables['channels']}, {('a2_d_08', 'a2_l'), ('a2_d_08', 'a2_r')})
        self.assertEqual(len(tables['channels']), 2)
        self.assertEqual({(r['fly'], r['signal'], r['target']) for r in tables['pairs']}, PAIR_KEYS)
        self.assertEqual(len(tables['pairs']), 3)
        for name, metric in (('channels', 'yaw_r150'), ('pairs', 'r150')):
            for row in tables[name]:
                self.assertEqual(row['numerical_valid'], 'True')
                self.assertGreaterEqual(int(row['n_valid_r150']), 100)
                self.assertTrue(math.isfinite(float(row[metric])))
                self.assertEqual(row['main_summary_eligible'], 'True')

    def test_all_invalid_voltage_or_stimulus_is_excluded(self):
        for case in ('all_voltage_nan', 'all_stim_nan', 'all_stim_on'):
            with self.subTest(case=case):
                run, report, tables = self.run_case(case)
                self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(report['analysis_status'], 'excluded')
                self.assertEqual((report['usable_records'], report['partial_records'], report['excluded_records']), (0, 0, 1))
                self.assertEqual(tables['inventory'][0]['analysis_status'], 'excluded')
                self.assert_not_main_summary(tables)
                if case == 'all_voltage_nan':
                    self.assertEqual(tables['pairs'], [])
                    self.assertEqual(tables['lag_curves'], [])
                else:
                    for row in tables['channels'] + tables['pairs']:
                        self.assertEqual(row['numerical_valid'], 'False')
                        self.assertEqual(int(row['n_valid_r150']), 0)

    def test_one_invalid_voltage_channel_is_partial(self):
        run, report, tables = self.run_case('one_voltage_nan')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['analysis_status'], 'partial')
        self.assertEqual((report['usable_records'], report['partial_records'], report['excluded_records']), (0, 1, 0))
        self.assertEqual(tables['inventory'][0]['analysis_status'], 'partial')
        self.assertEqual(tables['pairs'], [])
        self.assertEqual([r['neuron'] for r in tables['channels'] if r.get('numerical_valid') == 'True'], ['a2_l'])
        self.assert_not_main_summary(tables)

    def test_fewer_than_100_valid_lagged_samples_is_excluded(self):
        run, report, tables = self.run_case('too_few_valid_samples')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['analysis_status'], 'excluded')
        self.assertTrue(tables['channels'])
        for row in tables['channels'] + tables['pairs']:
            self.assertLess(int(row['n_valid_r150']), 100)
            self.assertEqual(row['numerical_valid'], 'False')
        self.assert_not_main_summary(tables)

    def test_constant_yaw_cannot_supply_finite_required_correlations(self):
        run, report, tables = self.run_case('constant_yaw')
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertEqual(report['analysis_status'], 'excluded')
        self.assertTrue(all(r['numerical_valid'] == 'False' for r in tables['channels']))
        self.assert_not_main_summary(tables)

    def test_wrapper_rejects_invalid_core_result_despite_record_complete(self):
        faults = {
            'wrong_pair_target': "result[2][1]['target'] = 'fwd'",
            'wrong_channel_fly': "result[1][0]['fly'] = 'a2_d_12'",
            'wrong_pair_fly': "result[2][1]['fly'] = 'a2_d_12'",
            'wrong_pair_kind': "result[2][1]['kind'] = 'same_side_cross_type'",
            'nonfinite_metric': "result[1][0]['yaw_r150'] = float('nan')",
            'nonfinite_r0': "result[1][0]['yaw_r0'] = float('nan')",
            'insufficient_support': "result[1][0]['n_valid_r150'] = 99",
            'invalid_numerical_flag': "result[1][0]['numerical_valid'] = False",
        }
        for name, fault in faults.items():
            with self.subTest(fault=name):
                run, report, tables = self.run_case(fault=fault)
                self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(report['analysis_status'], 'partial')
                # Core completeness is retained as evidence; the wrapper makes
                # an independent analysis-completeness decision.
                self.assertEqual(tables['inventory'][0]['record_complete'], 'True')
                self.assert_not_main_summary(tables)

    def test_wrong_record_identity_cannot_count_as_processed_selected_input(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        raw, output = prepare_cli_case(root, 'finite_control')
        inject_core_result_fault(root, "result[0]['fly'] = 'a2_d_12'")
        run = execute_cli(root, raw, output, Path(self.plotting_cache.name))
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        report = json.loads((output / 'RUN.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['processing_status'], 'failed')
        self.assertEqual(report['analysis_status'], 'excluded')
        self.assertEqual(report['selected_flies'], ['a2_d_08'])
        self.assertEqual(report['processed_records'], 0)
        self.assertIn('identity differs', report['errors'][0]['message'])
        for name, keys in BASE_TABLE_KEYS.items():
            fields, rows = read_table(output / (name + '.csv'))
            self.assertTrue(keys <= set(fields))
            self.assertEqual(rows, [])


if __name__ == '__main__':
    unittest.main()
