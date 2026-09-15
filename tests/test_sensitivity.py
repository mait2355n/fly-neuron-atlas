"""Public CLI sensitivity tests with synthetic raw voltages and explicit oracles.

The core creates the required base-run fixture. Independent NumPy correlations
and manually formed masks check output interpretation; this is not validation
of raw biological recordings or an independent detector implementation.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import numpy as np
    from scipy.io import savemat
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import ephys_core as core
except ImportError:
    np = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(np is None, 'requires requirements-ephys.txt numerical environment')
class SensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.base_temp.cleanup)
        cls.base = Path(cls.base_temp.name)
        raw, run = cls.base / 'raw', cls.base / 'run'
        raw.mkdir()
        run.mkdir()
        fs, bs, duration = 1000, 100, 32
        t = np.arange(duration * fs) / fs
        tb = np.arange(duration * bs) / bs
        rng = np.random.default_rng(945)
        a = -35 + 5 * np.sin(t / 3) + rng.normal(0, .35, len(t))
        b = -37 + 5 * np.cos(t / 4) + rng.normal(0, .35, len(t))
        a[rng.choice(np.arange(20, len(t) - 20), 320, replace=False)] += 12
        b[rng.choice(np.arange(20, len(t) - 20), 240, replace=False)] += 11
        raw_file = raw / 'synthetic.mat'
        savemat(raw_file, {'ephys_SR': fs, 'ball_SR': bs, 'ephys_A': a, 'ephys_B': b,
            't_ephys': t % 16, 't_ball': tb % 16, 'stim': np.zeros(len(t)),
            'yaw': rng.normal(size=len(tb)), 'fwd': np.sin(tb), 'lat': np.cos(tb)})
        content = raw_file.read_bytes()
        md5 = hashlib.md5(content).hexdigest()
        source = {'fly': 'a2_d_08', 'status': 'verified', 'bytes': len(content),
                  'md5': md5, 'sha256': hashlib.sha256(content).hexdigest()}
        raw_file.with_suffix('.mat.receipt.json').write_text(json.dumps(source), encoding='utf-8')
        entry = {'directoryLabel': '/ephys_data_a2_d_08', 'dataFile': {'filename': raw_file.name,
                 'id': 1, 'filesize': len(content), 'checksum': {'value': md5}}}
        previous = core.B, core.RAW
        try:
            core.B, core.RAW = run, raw
            computed = core.run_file(entry)
        finally:
            core.B, core.RAW = previous
        if computed[0]['status'] != 'usable':
            raise AssertionError(computed[0])
        core.write_csv(run / 'inventory.csv', [computed[0]])
        core.write_csv(run / 'channels.csv', computed[1])
        (run / 'RUN.json').write_text(json.dumps({'schema_version': 'fly-neuron-atlas-ephys-run/v2',
            'status': 'pass', 'processing_status': 'completed', 'analysis_status': 'usable',
            'selected_flies': ['a2_d_08'], 'source_hashes': [source]}), encoding='utf-8')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(self.base / 'raw', self.root / 'raw')
        shutil.copytree(self.base / 'run', self.root / 'run')

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/reproduce_sensitivity.py'),
            '--raw-dir', str(self.root / 'raw'), '--run-dir', str(self.root / 'run'),
            '--output', str(self.root / 'output'), *args], cwd=self.root,
            capture_output=True, text=True, timeout=60)
        return result.returncode, json.loads(result.stdout)

    def rows(self, name):
        with (self.root / 'output' / (name + '.csv')).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))

    def edit_table(self, filename, transform):
        path = self.root / 'run' / filename
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(transform(rows))

    def test_cli_grid_and_independent_correlations_and_masks(self):
        code, report = self.cli()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['rows'], {'threshold_lag_sensitivity': 12,
            'paired_threshold_sensitivity': 6, 'pair_sensitivity': 6,
            'voltage_sensitivity': 5, 'clock_boundary_sensitivity': 12,
            'source_example_comparison': 2})
        self.assertEqual(report['method_version'], 'epoch-isolated-sensitivity/v2')
        with np.load(self.root / 'run/aligned/a2_d_08.npz') as z:
            m = z['a2_l_valid'] & z['a2_r_valid']
            pairmask = m[:-15] & m[15:] & (z['epoch_id'][:-15] == z['epoch_id'][15:])
            baseline = next(r for r in self.rows('pair_sensitivity') if float(r['prominence']) == 7.5)
            for field, x in [('difference_r150', z['a2_l_fr'] - z['a2_r_fr']),
                             ('sum_r150', z['a2_l_fr'] + z['a2_r_fr'])]:
                expected = np.corrcoef(x[:-15][pairmask], z['yaw'][15:][pairmask])[0, 1]
                self.assertAlmostEqual(float(baseline[field]), expected, places=12)
            voltage = next(r for r in self.rows('voltage_sensitivity') if r['signal'] == 'A_minus_B')
            q = m & (z['a2_l_vm'] <= -33) & (z['a2_r_vm'] <= -33)
            self.assertEqual(int(voltage['vm_cutoff_valid_bins']), int(q.sum()))
            boundary = next(r for r in self.rows('clock_boundary_sensitivity')
                if float(r['guard_s']) == 5.5 and r['signal'] == 'a2_l_fr' and r['target'] == 'yaw')
            expected_mask = z['a2_l_valid'] & (abs(z['time_s'] - 16) >= 5.5)
            self.assertAlmostEqual(float(boundary['valid_s']), expected_mask.sum() / 100)
        for label in ('a2_l', 'a2_r'):
            counts = [int(r['spikes']) for r in self.rows('threshold_lag_sensitivity') if r['neuron'] == label]
            self.assertEqual(counts, sorted(counts, reverse=True))

    def test_raw_change_fails_with_no_successful_rows(self):
        with (self.root / 'raw/synthetic.mat').open('ab') as stream:
            stream.write(b'changed')
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertIn('raw MD5/size differs', report['errors'][0]['message'])
        self.assertEqual(report['processed_flies'], [])

    def test_duplicate_inventory_fails_preflight(self):
        self.edit_table('inventory.csv', lambda rows: rows + rows)
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('duplicate or empty inventory', report['message'])

    def test_missing_selected_record_fails_preflight(self):
        self.edit_table('inventory.csv', lambda rows: [])
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('population differs', report['message'])

    def test_legacy_run_is_not_corrected(self):
        path = self.root / 'run/RUN.json'
        run = json.loads(path.read_text(encoding='utf-8'))
        run['schema_version'] = 'fly-neuron-atlas-ephys-run/v1'
        path.write_text(json.dumps(run), encoding='utf-8')
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('ephys-run/v2', report['message'])

    def test_baseline_count_mismatch_is_reported(self):
        path = self.root / 'run/aligned/a2_d_08.npz'
        with np.load(path) as archive:
            z = {k: archive[k] for k in archive.files}
        z['a2_l_counts'][100] += 1
        np.savez_compressed(path, **z)
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertIn('baseline counts differ', report['errors'][0]['message'])

    def test_reference_only_eligibility_is_preserved(self):
        self.edit_table('channels.csv', lambda rows: [{**r, 'main_summary_eligible': 'False'} for r in rows])
        code, report = self.cli()
        self.assertEqual(code, 0, report)
        self.assertTrue(all(r['main_file_eligible'] == 'False' for r in self.rows('pair_sensitivity')))
        self.assertTrue(all(r['main_summary_eligible'] == 'False' for r in self.rows('voltage_sensitivity')))

    def test_nonempty_output_is_preserved(self):
        (self.root / 'output').mkdir()
        (self.root / 'output/keep').write_text('prior result', encoding='utf-8')
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual((self.root / 'output/keep').read_text(encoding='utf-8'), 'prior result')

    def replace_base_run(self, fly, no_reset=False):
        raw, run_dir = self.root / 'raw', self.root / 'run'
        raw_file = raw / 'synthetic.mat'
        if no_reset:
            data = core.loadmat(raw_file, squeeze_me=True)
            data = {k: v for k, v in data.items() if not k.startswith('__')}
            data['t_ephys'] = np.arange(len(data['t_ephys'])) / int(data['ephys_SR'])
            data['t_ball'] = np.arange(len(data['t_ball'])) / int(data['ball_SR'])
            savemat(raw_file, data)
        content = raw_file.read_bytes()
        source = {'fly': fly, 'status': 'verified', 'bytes': len(content),
                  'md5': hashlib.md5(content).hexdigest(), 'sha256': hashlib.sha256(content).hexdigest()}
        raw_file.with_suffix('.mat.receipt.json').write_text(json.dumps(source), encoding='utf-8')
        entry = {'directoryLabel': '/ephys_data_' + fly, 'dataFile': {'filename': raw_file.name,
                 'id': 1, 'filesize': len(content), 'checksum': {'value': source['md5']}}}
        previous = core.B, core.RAW
        try:
            core.B, core.RAW = run_dir, raw
            computed = core.run_file(entry)
        finally:
            core.B, core.RAW = previous
        core.write_csv(run_dir / 'inventory.csv', [computed[0]])
        core.write_csv(run_dir / 'channels.csv', computed[1])
        (run_dir / 'RUN.json').write_text(json.dumps({'schema_version': 'fly-neuron-atlas-ephys-run/v2',
            'status': 'pass', 'processing_status': 'completed', 'analysis_status': 'usable',
            'selected_flies': [fly], 'source_hashes': [source]}), encoding='utf-8')

    def test_cross_type_uses_three_shared_thresholds_and_two_directional_lags(self):
        self.replace_base_run('a1_a2_d_01')
        code, report = self.cli()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['rows']['threshold_lag_sensitivity'], 9)
        self.assertEqual(report['rows']['paired_threshold_sensitivity'], 5)
        self.assertEqual(report['rows']['pair_sensitivity'], 0)
        lag_rows = [r for r in self.rows('paired_threshold_sensitivity') if r['kind'] == 'DNa02_to_DNa01_lag']
        self.assertEqual(len(lag_rows), 2)
        self.assertTrue(all(np.isnan(float(r['difference_r150'])) for r in lag_rows))

    def test_single_channel_without_resets_writes_empty_pair_and_clock_headers(self):
        self.replace_base_run('a1_s_02', no_reset=True)
        code, report = self.cli()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['rows']['threshold_lag_sensitivity'], 3)
        self.assertEqual(report['rows']['voltage_sensitivity'], 1)
        self.assertEqual(report['rows']['clock_boundary_sensitivity'], 0)
        self.assertEqual(self.rows('pair_sensitivity'), [])


if __name__ == '__main__':
    unittest.main()
