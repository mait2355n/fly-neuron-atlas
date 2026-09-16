"""Fixed-method diagnostic checks; no biological detection oracle is implied."""
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
    from scipy import signal
    import matplotlib
except ImportError as exc:
    raise unittest.SkipTest("requires the pinned requirements-ephys.txt numerical environment") from exc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ephys_core as core
import normalization_sensitivity as normalization


class NormalizationMethodTests(unittest.TestCase):
    def test_filter_inputs_and_output_exactly_match_source(self):
        voltage = np.random.default_rng(80).normal(size=5000)
        original = signal.filtfilt
        calls = []
        def capture(b, a, data):
            result = original(b, a, data)
            calls.append((b.copy(), a.copy(), data.copy(), result.copy()))
            return result
        with patch.object(signal, "filtfilt", side_effect=capture):
            core.mad_process(voltage, 1000)
            result = normalization.source_highpass(voltage, 1000)
        self.assertEqual(len(calls), 2)
        for source, alternative in zip(calls[0], calls[1]):
            np.testing.assert_array_equal(source, alternative)
        np.testing.assert_array_equal(result, calls[0][3])

    def test_contiguous_windows_track_a_local_noise_gain(self):
        # Independent construction: the same centered noise samples, then gain4.
        base = np.random.default_rng(9).normal(size=500)
        hp = np.r_[np.tile(base, 4), np.tile(base * 4, 4)]
        _, scale, windows = normalization.contiguous_mad_arrays(hp, 1000)
        np.testing.assert_allclose(windows[4:], windows[:4] * 4, rtol=1e-14)
        self.assertAlmostEqual(scale[3250] / scale[750], 4.)
        self.assertGreater(scale[2000], windows[0])
        self.assertLess(scale[2000], windows[-1])

    def test_median_mad_and_center_interpolation_match_hand_values(self):
        hp = np.array([-3., -1., 1., 3., 4., 8., 12., 16.])
        median, scale, windows = normalization.contiguous_mad_arrays(hp, 8)
        np.testing.assert_allclose(windows, [2 * 1.4826, 4 * 1.4826])
        np.testing.assert_allclose(median, [0., 0., 1.25, 3.75, 6.25, 8.75, 10., 10.])
        self.assertAlmostEqual(scale[3], (2 + 2 * .375) * 1.4826)
        self.assertEqual(scale[0], windows[0])
        self.assertEqual(scale[-1], windows[-1])

    def test_zero_noise_and_incomplete_windows_are_explicit_errors(self):
        with self.assertRaisesRegex(ValueError, "nonpositive"):
            normalization.contiguous_mad_arrays(np.ones(1000), 1000)
        with self.assertRaisesRegex(ValueError, "complete windows"):
            normalization.contiguous_mad_arrays(np.arange(501.), 1000)

    def test_alternative_uses_the_shared_epoch_hook(self):
        first = np.random.default_rng(2).normal(size=2000)
        second = np.random.default_rng(3).normal(size=2000) * 4
        captured = []
        def observe(voltage, fs):
            captured.append(voltage.copy())
            return normalization.contiguous_half_second_mad(voltage, fs)
        processed = core.process_voltage_epochs(np.r_[first, second], 1000, 7.5, 10,
                                               np.array([0, 2000, 4000]), normalizer=observe)
        self.assertEqual(len(captured), 2)
        np.testing.assert_array_equal(captured[0], first)
        np.testing.assert_array_equal(captured[1], second)
        self.assertEqual(processed["epoch_bounds"].tolist(), [0, 2000, 4000])


class ReferenceContractTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        reference = Path(temporary.name)
        results, channels, pairs = {}, [], []
        for fly in normalization.FLIES:
            ch = [{"fly": fly, "neuron": lab, "spikes": 10, "rate_mean_Hz": 2.,
                   "rate_no_stim_mean_Hz": 1.5, "yaw_r0": .2, "yaw_r150": .3}
                  for lab in ("a2_l", "a2_r")]
            pp = [{"fly": fly, "signal": signal_name, "target": target, "r0": .1, "r150": .2}
                  for signal_name, target in (("a2_l_rate", "a2_r_rate"), ("A_minus_B", "yaw"), ("A_plus_B", "yaw"))]
            results[normalization.METHODS[0], fly] = ({}, ch, pp, [], [])
            channels.extend(ch); pairs.extend(pp)
        (reference / "RUN.json").write_text(json.dumps({"processing_status": "completed"}), encoding="utf-8")
        self.write_rows(reference / "channels.csv", channels)
        self.write_rows(reference / "pairs.csv", pairs)
        return reference, results, channels, pairs

    def write_rows(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    def test_exact_subset_identities_and_values_pass(self):
        reference, results, _, _ = self.fixture()
        check = normalization.compare_reference(reference, results)
        self.assertEqual(check["status"], "pass")
        self.assertEqual(len(check["checks"]), 15)
        self.assertEqual(len(check["identity_checks"]), 6)

    def test_missing_or_incomplete_reference_cannot_be_verified(self):
        reference, results, _, _ = self.fixture()
        (reference / "RUN.json").unlink()
        self.assertEqual(normalization.compare_reference(reference, results)["status"], "not_verified")
        (reference / "RUN.json").write_text(json.dumps({"processing_status": "partial"}), encoding="utf-8")
        self.assertEqual(normalization.compare_reference(reference, results)["status"], "not_verified")

    def test_extra_or_duplicate_channel_rows_are_rejected(self):
        reference, results, channels, _ = self.fixture()
        for extra in (dict(channels[0]), {**channels[0], "neuron": "unexpected_channel"}):
            with self.subTest(extra=extra["neuron"]):
                self.write_rows(reference / "channels.csv", channels + [extra])
                check = normalization.compare_reference(reference, results)
                self.assertEqual(check["status"], "fail")
                self.assertTrue(any(not row["matches"] for row in check["identity_checks"]))

    def test_extra_or_wrong_target_pair_rows_are_rejected(self):
        reference, results, _, pairs = self.fixture()
        self.write_rows(reference / "pairs.csv", pairs + [dict(pairs[0])])
        self.assertEqual(normalization.compare_reference(reference, results)["status"], "fail")
        altered = [dict(row) for row in pairs]
        altered[-1]["target"] = "wrong_target"
        self.write_rows(reference / "pairs.csv", altered)
        self.assertEqual(normalization.compare_reference(reference, results)["status"], "fail")

    def test_cli_missing_or_incomplete_reference_returns_failure(self):
        # Replay already-computed numerical rows to exercise the CLI decision.
        # Raw computation and hashing are substituted here; real runs cover those.
        reference, results, _, _ = self.fixture()
        manifest = json.loads((normalization.ROOT / "data/activity/download_manifest.json").read_text(encoding="utf-8"))
        entries = {e["filename"]: e for e in manifest["files"] if e["fly"] in normalization.FLIES}
        for computed in results.values():
            computed[0].update(analysis_status="usable", processing_status="completed", reason="")
            for row in computed[1] + computed[2]:
                row.update(numerical_valid=True, main_summary_eligible=True, n_valid_r150=200)
        raw = reference / "raw"; raw.mkdir()
        actual_hashes = normalization.file_hashes
        def hashes(path):
            if Path(path).parent == raw:
                entry = entries[Path(path).name]
                return {"bytes": entry["bytes"], "md5": entry["md5"], "sha256": "synthetic-replayed-input"}
            return actual_hashes(path)
        def compute(entry, normalizer=None):
            fly = entry["directoryLabel"].split("ephys_data_")[1]
            return results[normalization.METHODS[0], fly]
        (reference / "RUN.json").write_text(json.dumps({"processing_status": "partial"}), encoding="utf-8")
        for index, ref in enumerate((reference / "missing", reference)):
            output = reference / ("out" + str(index))
            argv = ["normalization_sensitivity.py", "--raw-dir", str(raw), "--output", str(output), "--reference", str(ref)]
            with patch.object(sys, "argv", argv), patch.object(normalization, "file_hashes", side_effect=hashes), \
                 patch.object(core, "run_file", side_effect=compute), patch.object(core, "B", core.B), \
                 patch.object(core, "RAW", core.RAW), patch.object(normalization, "fixed_waveform", return_value=str(output / "example.png")), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(normalization.main(), 1)
            report = json.loads((output / "RUN.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["source_reference"]["status"], "not_verified")
            self.assertIn("source_reference_not_verified", [error["code"] for error in report["errors"]])


if __name__ == "__main__":
    unittest.main()
