"""Synthetic contract checks: not biological spike or physiological validation."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
    from scipy import ndimage
    import matplotlib
except ImportError as exc:
    raise unittest.SkipTest("requires the pinned requirements-ephys.txt numerical environment") from exc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ephys_core as core
from ephys_fixtures import cross_epoch_prominence, synthetic_record


class RecordAvailabilityTests(unittest.TestCase):
    def run_case(self, case="finite_control", fly="a2_d_08", seconds=21, limit=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        raw, output = root / "raw", root / "out"
        output.mkdir()
        entry = synthetic_record(raw, case, fly, seconds=seconds)
        with patch.object(core, "RAW", raw), patch.object(core, "B", output):
            rows = core.run_file(entry, limit=limit)
        return rows, output

    def test_finite_control_and_complete_expected_outputs(self):
        (info, channels, pairs, _, _), out = self.run_case()
        self.assertEqual(info["processing_status"], "completed")
        self.assertEqual(info["analysis_status"], "usable")
        self.assertTrue(info["record_complete"])
        self.assertEqual(info["expected_channels"], ["a2_l", "a2_r"])
        self.assertEqual(info["observed_pair_series"],
                         ["a2_l_rate->a2_r_rate", "A_minus_B->yaw", "A_plus_B->yaw"])
        for row in channels + pairs:
            self.assertTrue(row["numerical_valid"])
            self.assertTrue(row["main_summary_eligible"])
            self.assertGreaterEqual(row["n_valid_r150"], 100)
        # Recorded before this correction with the same finite synthetic fixture.
        np.testing.assert_allclose([r["yaw_r150"] for r in channels],
                                   [.039688179874195664, .009620218728467293], rtol=0, atol=1e-14)
        with np.load(out / "aligned/a2_d_08.npz") as aligned:
            self.assertFalse(aligned["stim_unknown"].any())

    def test_all_voltage_nan_and_empty_are_excluded(self):
        for case, reason in (("all_voltage_nan", "nonfinite_voltage"), ("empty_voltage", "empty_voltage")):
            with self.subTest(case=case):
                (info, channels, pairs, _, _), _ = self.run_case(case)
                self.assertEqual(info["processing_status"], "completed")
                self.assertEqual(info["analysis_status"], "excluded")
                self.assertIn(reason, info["reasons"])
                self.assertEqual(len(channels), 2)
                self.assertFalse(pairs)
                self.assertTrue(all(not r["main_summary_eligible"] for r in channels))

    def test_missing_or_failed_second_channel_is_partial(self):
        for case in ("one_voltage_nan", "missing_voltage"):
            with self.subTest(case=case):
                (info, channels, pairs, _, _), _ = self.run_case(case)
                self.assertEqual(info["analysis_status"], "partial")
                self.assertFalse(info["record_complete"])
                self.assertEqual(info["numerically_valid_channels"], ["a2_l"])
                self.assertFalse(pairs)
                self.assertTrue(all(not r["main_summary_eligible"] for r in channels))

    def test_all_unknown_and_all_on_stimulus_are_excluded(self):
        for case in ("all_stim_nan", "all_stim_on"):
            with self.subTest(case=case):
                (info, channels, pairs, _, _), out = self.run_case(case)
                self.assertEqual(info["analysis_status"], "excluded")
                self.assertEqual(info["valid_no_stim_s"], 0)
                for row in channels + pairs:
                    self.assertFalse(row["numerical_valid"])
                    self.assertFalse(row["main_summary_eligible"])
                    self.assertEqual(row["n_valid_r150"], 0)
                with np.load(out / "aligned/a2_d_08.npz") as aligned:
                    self.assertFalse(aligned["valid"].any())
                    self.assertEqual(bool(aligned["stim_unknown"].all()), case == "all_stim_nan")

    def test_some_stimulus_unknown_has_guarded_support(self):
        (info, _, _, _, _), out = self.run_case("some_stim_nan")
        self.assertEqual(info["analysis_status"], "usable")
        self.assertEqual(info["stim_unknown_bins"], 100)
        with np.load(out / "aligned/a2_d_08.npz") as aligned:
            self.assertTrue(aligned["stim_unknown"][500:600].all())
            self.assertFalse(aligned["valid"][490:625].any())
            self.assertTrue(aligned["valid"][489])
            self.assertTrue(aligned["valid"][625])

    def test_required_yaw_and_sample_count_are_enforced(self):
        (missing, _, _, _, _), _ = self.run_case("missing_yaw")
        self.assertEqual(missing["analysis_status"], "excluded")
        (constant, channels, _, _, _), _ = self.run_case("constant_yaw")
        self.assertNotEqual(constant["analysis_status"], "usable")
        self.assertTrue(all(not r["numerical_valid"] for r in channels))
        (short, channels, _, _, _), _ = self.run_case(limit=1.8)
        self.assertEqual(short["analysis_status"], "excluded")
        self.assertTrue(all(r["n_valid_r150"] < 100 for r in channels))

    def test_author_flag_does_not_change_numerical_availability(self):
        (info, channels, pairs, _, _), _ = self.run_case(fly="a2_d_14")
        self.assertEqual(info["analysis_status"], "usable")
        for row in channels + pairs:
            self.assertTrue(row["numerical_valid"])
            self.assertFalse(row["author_reference_eligible"])
            self.assertFalse(row["main_summary_eligible"])

    def test_clock_reset_is_a_source_epoch_not_a_real_time_gap(self):
        (info, channels, pairs, _, _), out = self.run_case("clock_reset", seconds=22)
        self.assertEqual(info["source_clock_resets"], 1)
        self.assertEqual(info["analysis_status"], "usable")
        with np.load(out / "aligned/a2_d_08.npz") as aligned:
            self.assertEqual(np.unique(aligned["epoch_id"]).tolist(), [0, 1])
            self.assertFalse(aligned["valid"][1050:1150].any())
            self.assertLess(aligned["source_time_s"][1100], aligned["source_time_s"][1099])

    def test_expected_identity_and_pair_target_affect_completeness(self):
        (info, channels, pairs, _, _), _ = self.run_case()
        channels[0]["neuron"] = "wrong_label"
        core.finalize_inventory(info, channels, pairs)
        self.assertFalse(info["record_complete"])
        self.assertNotEqual(info["analysis_status"], "usable")
        self.assertTrue(all(not r["main_summary_eligible"] for r in channels + pairs))
        channels[0]["neuron"] = "a2_l"
        pairs[-1]["target"] = "wrong_target"
        core.finalize_inventory(info, channels, pairs)
        self.assertFalse(info["record_complete"])


class SourceEpochIsolationTests(unittest.TestCase):
    def test_prominence_does_not_cross_the_clock_reset(self):
        proc, bounds = cross_epoch_prominence()
        # The old joined extraction detects a false peak a full second before reset.
        self.assertEqual(core.extract_spikes(proc, 1000, 7.5, 10)[0].tolist(), [9000])
        isolated = core.extract_spikes_by_epoch(proc, 1000, 7.5, 10, bounds)
        self.assertEqual(isolated[0].tolist(), [])
        self.assertEqual(int(isolated[1].sum()), 0)

    def test_rate_smoothing_does_not_leak_into_next_epoch(self):
        proc = np.zeros(2000)
        proc[985] = 10.
        joined = core.extract_spikes(proc, 1000, 7.5, 10)[2]
        isolated = core.extract_spikes_by_epoch(proc, 1000, 7.5, 10, np.array([0, 1000, 2000]))[2]
        self.assertGreater(joined[100], 0)
        np.testing.assert_array_equal(isolated[100:], np.zeros(100))

    def test_refractory_counts_exclude_the_cross_epoch_interval(self):
        # Peaks <2 ms apart are separate-epoch observations, not one observed ISI.
        proc = np.zeros(2000)
        proc[[400, 998, 1001, 1500]] = 10.
        peaks, counts, _, frac = core.extract_spikes_by_epoch(proc, 2000, 7.5, 20, np.array([0, 1000, 2000]))
        self.assertEqual(peaks.tolist(), [400, 998, 1001, 1500])
        self.assertEqual(int(counts.sum()), 4)
        self.assertEqual(frac, 0.)
        self.assertGreater(core.extract_spikes(proc, 2000, 7.5, 20)[3], 0.)

    def test_normalization_and_vm_receive_separate_source_epochs(self):
        first = np.zeros(1000); second = np.full(1000, 100.)
        first[-10:] = 80.; second[:10] = 20.
        seen = []
        def identity(v, fs):
            seen.append(v.copy())
            return v.copy(), {"noise_scale_median_mV": 1.}
        got = core.process_voltage_epochs(np.r_[first, second], 1000, 200., 10,
                                          np.array([0, 1000, 2000]), normalizer=identity)
        self.assertEqual([len(v) for v in seen], [1000, 1000])
        self.assertEqual(got["vm"][99], 80.)
        self.assertEqual(got["vm"][100], 20.)
        old_vm = ndimage.median_filter(np.median(np.r_[first, second].reshape(-1, 10), axis=1),
                                      size=3, mode="nearest")
        self.assertEqual(old_vm[99:101].tolist(), [20., 80.])
        self.assertEqual(got["epoch_bounds"].tolist(), [0, 1000, 2000])
        self.assertEqual(got["proc"].tolist(), np.r_[first, second].tolist())

    def test_single_epoch_source_path_is_unchanged(self):
        rng = np.random.default_rng(44)
        v = rng.normal(size=5000)
        expected, noise = core.mad_process(v, 1000)
        old = core.extract_spikes(expected, 1000, 7.5, 10)
        got = core.process_voltage_epochs(v, 1000, 7.5, 10, np.array([0, len(v)]))
        np.testing.assert_array_equal(got["proc"], expected)
        for key, value in zip(("peaks", "counts", "fr"), old[:3]):
            np.testing.assert_array_equal(got[key], value)
        self.assertEqual(got["noise"], noise)

    def test_lag_count_cannot_borrow_cross_epoch_pairs(self):
        x = np.arange(220., dtype=float)
        epochs = np.repeat([0, 1], 110)
        mask = np.ones(220, bool)
        self.assertEqual(core.valid_lagged_count(x, x, mask), 205)
        self.assertEqual(core.valid_lagged_count(x, x, mask, epochs=epochs), 190)
        # Only boundary-crossing endpoints are marked valid.
        left = np.zeros(220, bool); right = np.zeros(220, bool)
        left[95:110] = True; right[110:125] = True
        self.assertEqual(core.valid_lagged_count(x, x, left, right, epochs=epochs), 0)

    def test_stim_unknown_and_known_on_support_do_not_cross_epochs(self):
        stim = np.zeros((200, 10)); stim[99, 2] = np.nan; stim[150, 0] = np.inf
        on, unknown, blocked = core.stimulus_validity(stim, np.repeat([0, 1], 100))
        self.assertFalse(on.any())
        self.assertEqual(np.flatnonzero(unknown).tolist(), [99, 150])
        self.assertTrue(blocked[89:100].all())
        self.assertFalse(blocked[100:140].any())
        self.assertTrue(blocked[140:176].all())
        stim[:] = 0; stim[99, 2] = 5.
        self.assertFalse(core.stimulus_validity(stim, np.repeat([0, 1], 100))[2][100:].any())

    def test_constant_series_is_not_a_finite_correlation_by_roundoff(self):
        x = np.arange(1000.)
        y = np.full(1000, .000395 / .000436)
        self.assertTrue(np.isnan(core.corr(x, y, np.ones(1000, bool))))

    def test_lagged_sample_minimum_is_100(self):
        x = np.arange(115.)
        self.assertAlmostEqual(core.corr(x, x, np.ones(115, bool), lag=15), 1.)
        self.assertTrue(np.isnan(core.corr(x[:-1], x[:-1], np.ones(114, bool), lag=15)))

    def test_csv_structured_cells_are_json_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rows.csv"
            core.write_csv(p, [{"reasons": ["欠測"], "counts": {"expected": 2}}])
            with p.open(encoding="utf-8", newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(json.loads(row["reasons"]), ["欠測"])
            self.assertEqual(json.loads(row["counts"]), {"expected": 2})


if __name__ == "__main__":
    unittest.main()
