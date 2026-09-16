#!/usr/bin/env python3
"""Compare two fixed normalization rules on three prespecified DNa02 records.

Raw inputs are read-only and must already have verified core receipts. This is
a sensitivity analysis, not a normalization-selection or spike-label benchmark.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import signal
from scipy.io import loadmat

import ephys_core as core

ROOT = Path(__file__).resolve().parents[1]
FLIES = ("a2_d_08", "a2_d_12", "a2_d_13")
METHODS = ("source_reshape_mad", "contiguous_half_second_mad")


def source_highpass(voltage, fs):
    """Same 120/30-second detrend and designed highpass as core.mad_process."""
    if len(voltage) % fs:
        raise ValueError("source normalization requires integer seconds")
    detrended = np.zeros_like(voltage, dtype=float)
    for duration in (120, 30):
        detrended += signal.detrend(voltage, bp=np.arange(0, len(voltage) - 1, duration * fs)) * .5
    order, wn = signal.buttord(wp=100, ws=.05, gpass=3, gstop=30, fs=fs)
    b, a = signal.butter(order, wn, btype="high", fs=fs)
    return signal.filtfilt(b, a, detrended)


def contiguous_mad_arrays(highpass, fs):
    """Nonoverlapping contiguous half-second windows, linear center interpolation."""
    if fs % 2:
        raise ValueError("half-second MAD requires an even sample rate")
    width = fs // 2
    if not len(highpass) or len(highpass) % width:
        raise ValueError("half-second MAD requires complete windows")
    blocks = highpass.reshape(-1, width)
    medians = np.median(blocks, axis=1)
    scales = np.median(np.abs(blocks - medians[:, None]), axis=1) * 1.4826
    if not np.isfinite(scales).all() or np.any(scales <= 0):
        raise ValueError("nonpositive or nonfinite contiguous normalization MAD")
    centers = (np.arange(len(blocks)) + .5) * width - .5
    samples = np.arange(len(highpass))
    # np.interp holds the nearest window center at the two source-epoch ends.
    return np.interp(samples, centers, medians), np.interp(samples, centers, scales), scales


def contiguous_half_second_mad(voltage, fs):
    hp = source_highpass(voltage, fs)
    median, scale, windows = contiguous_mad_arrays(hp, fs)
    info = {"noise_scale_median_mV": float(np.median(windows)),
            "noise_scale_p05_mV": float(np.percentile(windows, 5)), "zero_mad_blocks": 0}
    return (hp - median) / scale, info


def file_hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(chunk); sha.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha.hexdigest(), "bytes": Path(path).stat().st_size}


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def comparison_rows(results):
    channels, pairs = [], []
    for fly in FLIES:
        if any((method, fly) not in results for method in METHODS):
            continue
        source = results[METHODS[0], fly]
        source_channels = {row["neuron"]: row for row in source[1]}
        source_pairs = {(row["signal"], row["target"]): row for row in source[2]}
        for method in METHODS:
            info, ch, pp, _, _ = results[method, fly]
            for row in ch:
                base = source_channels[row["neuron"]]
                fields = ("spikes", "rate_mean_Hz", "rate_no_stim_mean_Hz", "yaw_r0", "yaw_r150", "n_valid_r150")
                got = {"method": method, "fly": fly, "neuron": row["neuron"],
                       "analysis_status": info["analysis_status"],
                       "numerical_valid": row["numerical_valid"], "main_summary_eligible": row["main_summary_eligible"]}
                for field in fields:
                    got[field] = row.get(field, np.nan)
                    got["delta_" + field + "_from_source"] = got[field] - base.get(field, np.nan)
                channels.append(got)
            for row in pp:
                base = source_pairs[row["signal"], row["target"]]
                got = {"method": method, "fly": fly, "signal": row["signal"], "target": row["target"],
                       "numerical_valid": row["numerical_valid"], "main_summary_eligible": row["main_summary_eligible"]}
                for field in ("r0", "r150", "n_valid_r150"):
                    got[field] = row[field]
                    got["delta_" + field + "_from_source"] = row[field] - base[field]
                pairs.append(got)
    return channels, pairs


def compare_reference(reference, results):
    """Independently reread completed baseline CSV values; do not edit reference."""
    required = [reference / name for name in ("RUN.json", "channels.csv", "pairs.csv")]
    if not all(p.exists() for p in required):
        return {"status": "not_verified", "reason": "reference_run_or_tables_not_available", "path": str(reference)}
    report = json.loads(required[0].read_text(encoding="utf-8"))
    if report.get("processing_status") != "completed":
        return {"status": "not_verified", "reason": "reference_processing_not_completed", "path": str(reference)}
    refs = [read_csv(path) for path in required[1:]]
    checks, identity_checks = [], []
    for fly in FLIES:
        if (METHODS[0], fly) not in results:
            continue
        for index, kind, keys, fields in (
            (1, "channel", ("neuron",), ("spikes", "rate_mean_Hz", "rate_no_stim_mean_Hz", "yaw_r0", "yaw_r150")),
            (2, "pair", ("signal", "target"), ("r0", "r150")),
        ):
            rows = [row for row in refs[index - 1] if row["fly"] == fly]
            expected_keys = sorted(tuple(row[key] for key in keys) for row in results[METHODS[0], fly][index])
            observed_keys = sorted(tuple(row[key] for key in keys) for row in rows)
            identity_checks.append({"fly": fly, "kind": kind, "matches": expected_keys == observed_keys,
                                    "expected": expected_keys, "observed": observed_keys})
            for row in results[METHODS[0], fly][index]:
                matched = [ref for ref in rows if all(row[key] == ref[key] for key in keys)]
                ok = len(matched) == 1
                deltas = {}
                if ok:
                    for field in fields:
                        actual, saved = float(row[field]), float(matched[0][field])
                        deltas[field] = actual - saved
                        ok &= bool(np.isclose(actual, saved, rtol=0, atol=1e-12, equal_nan=True))
                checks.append({"fly": fly, "kind": kind, "key": [row[key] for key in keys], "matches": ok, "deltas": deltas})
    return {"status": "pass" if checks and all(row["matches"] for row in checks + identity_checks) else "fail",
            "path": str(reference), "checked_fields_atol": 1e-12, "checks": checks, "identity_checks": identity_checks,
            "artifacts": {p.name: file_hashes(p) for p in required}}


def fixed_waveform(raw, output, entries):
    fly = "a2_d_12"
    d = loadmat(raw / entries[fly]["filename"], squeeze_me=True,
                variable_names=["ephys_A", "ephys_B", "t_ephys", "ephys_SR"])
    fs = int(d["ephys_SR"])
    tt = np.asarray(d["t_ephys"]) - float(np.asarray(d["t_ephys"])[0])
    # This prespecified window is in the first source epoch.
    sample_end = np.flatnonzero(np.diff(tt) <= 0)
    if len(sample_end):
        end = sample_end[0] + 1
        tt = tt[:end]
    visible = (tt >= .8) & (tt <= 1.3)
    fig, axes = core.plt.subplots(2, 1, figsize=(11, 6.3), sharex=True)
    colors = {METHODS[0]: "#d75e2c", METHODS[1]: "#077f8c"}
    for ax, channel, lab in zip(axes, ("ephys_A", "ephys_B"), ("a2_l", "a2_r")):
        voltage = np.asarray(d[channel])[:len(tt)]
        ax.plot(tt[visible], voltage[visible], color="#24364b", linewidth=.7, label="raw voltage")
        for method in METHODS:
            with np.load(output / method / "spikes" / (fly + ".npz")) as spikes:
                st = spikes[lab]; st = st[(st >= .8) & (st <= 1.3)]
            kwargs = {"facecolors": "none", "edgecolors": colors[method]} if method == METHODS[0] else {"color": colors[method]}
            ax.scatter(st, np.interp(st, tt, voltage), marker="o" if method == METHODS[0] else "x",
                       s=42 if method == METHODS[0] else 26, linewidths=1.1,
                       label=f"{method} ({len(st)} peaks)", **kwargs)
        ax.set_ylabel(lab + " / mV"); ax.grid(alpha=.2)
        ax.legend(fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=3, frameon=False)
    axes[-1].set_xlabel("Seconds from first source-epoch start")
    axes[-1].set_xlim(.8, 1.3)
    fig.suptitle("a2_d_12 | fixed 0.8–1.3 s window | same filtering, two MAD rules")
    fig.text(.5, .005, "Prespecified example; no human spike labels. Waveform appearance is a proxy only.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .95), h_pad=2.)
    path = output / "figures" / "a2_d_12_0.8-1.3s.png"
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=180); core.plt.close(fig)
    return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".local/raw")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/normalization-v2")
    parser.add_argument("--reference", type=Path, default=ROOT / ".local/ephys-v2")
    args = parser.parse_args()
    raw, output, reference = args.raw_dir.resolve(), args.output.resolve(), args.reference.resolve()
    if output == ROOT or any(output == ROOT / p or ROOT / p in output.parents for p in ("data", "docs", "scripts", "licenses", ".git")):
        parser.error("output overlaps published files; choose .local or an external new directory")
    if output == raw or raw in output.parents or output in raw.parents:
        parser.error("output must not overlap raw inputs")
    if output.exists() and any(output.iterdir()):
        parser.error("output must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "data/activity/download_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {e["fly"]: e for e in manifest["files"] if e["fly"] in FLIES}
    results, inputs, errors = {}, [], []
    start = time.time()
    core.RAW = raw
    for method in METHODS:
        core.B = output / method; core.B.mkdir()
        sinks = [[], [], [], [], []]
        for fly in FLIES:
            try:
                entry = entries[fly]; path = raw / entry["filename"]
                if path.is_symlink():
                    raise ValueError("raw input is a symlink")
                hashes = file_hashes(path)
                if hashes["bytes"] != entry["bytes"] or hashes["md5"] != entry["md5"]:
                    raise ValueError("raw input size or MD5 differs from manifest")
                inputs.append({"method": method, "fly": fly, "filename": entry["filename"], **hashes})
                core_entry = {"directoryLabel": "/ephys_data_" + fly,
                              "dataFile": {"filename": entry["filename"], "id": entry["file_id"],
                                           "filesize": entry["bytes"], "checksum": {"value": entry["md5"]}}}
                print("Analyzing " + fly + " with " + method, file=sys.stderr, flush=True)
                computed = core.run_file(core_entry, normalizer=None if method == METHODS[0] else contiguous_half_second_mad)
                results[method, fly] = computed
                for sink, value in zip(sinks, computed):
                    sink.extend(value if isinstance(value, list) else [value])
                if computed[0]["analysis_status"] != "usable":
                    errors.append({"code": "analysis_not_usable", "method": method, "fly": fly,
                                   "message": computed[0]["reason"], "details": computed[0]["analysis_status"]})
            except (OSError, ValueError, KeyError) as exc:
                errors.append({"code": "record_failed", "method": method, "fly": fly, "message": str(exc)})
        for name, rows in zip(("inventory", "channels", "pairs", "lag_curves", "sensitivity"), sinks):
            core.write_csv(core.B / (name + ".csv"), rows)
    channels, pairs = comparison_rows(results)
    core.write_csv(output / "channels.csv", channels); core.write_csv(output / "pairs.csv", pairs)
    reference_check = compare_reference(reference, results)
    # Machine-local paths belong in a separate execution receipt, not the public run artifact.
    local_context = {"raw_dir": str(raw), "output": str(output), "reference": str(reference),
                     "command": [sys.executable, *sys.argv], "cwd": str(Path.cwd())}
    core.dump(output / "local_context.json", local_context)
    reference_check.pop("path", None)
    reference_check["reference_role"] = "independently_saved_corrected_source_run"
    if reference_check["status"] != "pass":
        errors.append({"code": "source_reference_not_verified" if reference_check["status"] == "not_verified" else "source_reference_mismatch",
                       "message": "completed, identity-complete source reference must match",
                       "details": reference_check.get("reason", reference_check["status"])})
    figure = None
    if all((method, "a2_d_12") in results and results[method, "a2_d_12"][0]["analysis_status"] == "usable" for method in METHODS):
        try:
            figure = fixed_waveform(raw, output, entries)
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"code": "fixed_waveform_failed", "message": str(exc)})
    if figure:
        figure = str(Path(figure).relative_to(output))
    same_inputs = all(len({(row["md5"], row["sha256"], row["bytes"]) for row in inputs if row["fly"] == fly}) == 1
                      and len([row for row in inputs if row["fly"] == fly]) == 2 for fly in FLIES)
    report = {"schema_version": "fly-neuron-atlas-normalization-sensitivity/v1",
              "status": "pass" if not errors and len(results) == 6 and same_inputs else "fail",
              "processing_status": "completed" if len(results) == 6 and all(row[0]["processing_status"] == "completed" for row in results.values()) else "partial",
              "selected_flies": list(FLIES), "methods": list(METHODS), "same_inputs_verified": same_inputs,
              "inputs": inputs, "settings": {"detrend_breakpoints_seconds": [120, 30], "detrend_weights": [.5, .5],
              "buttord": {"wp": 100, "ws": .05, "gpass": 3, "gstop": 30}, "filter": "butter high; filtfilt",
              "source_mad": "original C-order reshape(fs,-1), shifted source scale, signal.resample",
              "alternative_mad": "contiguous nonoverlapping0.5s windows; median and MAD*1.4826; linear window-center interpolation, constant edge extension",
              "height": 2.5, "prominence": 7.5, "peak_wlen_seconds": 10, "rate_hz": 100,
              "epoch_handling": "source clock epochs processed separately by corrected core",
              "primary_lag_ms": 150, "normalization_selection": "none"},
              "code_hashes": {str(p.relative_to(ROOT)): file_hashes(p) for p in (Path(__file__).resolve(), Path(core.__file__).resolve(), manifest_path)},
              "dependencies": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": core.scipy.__version__, "matplotlib": core.matplotlib.__version__},
              "source_reference": reference_check, "fixed_waveform": figure, "errors": errors,
              "elapsed_seconds": time.time() - start,
              "scope": "Sensitivity on three prespecified DNa02 bilateral recordings only; no population inference, winner selection, human spike-label validation or certified model calibration."}
    core.dump(output / "RUN.json", report)
    print(json.dumps({"status": report["status"], "report": str(output / "RUN.json"), "errors": errors}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
