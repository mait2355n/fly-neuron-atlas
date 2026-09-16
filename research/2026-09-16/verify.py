#!/usr/bin/env python3
"""Verify the published summary, not raw biological or model reproduction.

Copyright (c) 2026 mait2355n. MIT License; see ../../LICENSE.
"""

import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, name):
    require(math.isfinite(actual) and math.isfinite(expected), f"nonfinite: {name}")
    require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
            f"mismatch: {name}: {actual} != {expected}")


def concentration(angles):
    return math.hypot(statistics.mean(map(math.cos, angles)),
                      statistics.mean(map(math.sin, angles)))


def longest_run(values):
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def verify(root):
    provenance = json.loads((root / "PROVENANCE.json").read_text(encoding="utf-8"))
    require(provenance["schema"] == "fly-neuron-atlas/research-publication/v1", "provenance schema")
    paths = set()
    for artifact in provenance["artifacts"]:
        relative = artifact["path"]
        path = root / relative
        require(relative not in paths, f"duplicate artifact: {relative}")
        require(path.resolve().is_relative_to(root.resolve()), "artifact escapes publication")
        require(not path.is_symlink(), f"symlink artifact: {relative}")
        paths.add(relative)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"],
                f"sha256: {relative}")
    require({p.name for p in root.iterdir() if p.is_file()} == paths | {"PROVENANCE.json"},
            "undeclared or missing publication files")
    records = {x["id"] for x in provenance["source_records"]}
    sources = {x["id"] for x in provenance["public_sources"]}
    require(len(records) == len(provenance["source_records"]), "duplicate source record")
    require(len(sources) == len(provenance["public_sources"]), "duplicate public source")
    for artifact in provenance["artifacts"]:
        require(set(artifact["source_record_ids"]) <= records, "unknown source record")
        require(set(artifact["public_source_ids"]) <= sources, "unknown public source")

    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    with (root / "basnak_components.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        expected_fields = ["subject", "heading_early_R", "heading_late_R", "cue_proxy_early_R",
                           "cue_proxy_late_R", "heading_change", "cue_proxy_change", "difference_change"]
        require(reader.fieldnames == expected_fields, "component columns")
        rows = list(reader)
    require(len(rows) == 14, "subject count")
    require({r["subject"] for r in rows} == {f"sub-{i}_gain" for i in range(16, 30)},
            "subject identities")
    for row in rows:
        for key in expected_fields[1:]:
            row[key] = float(row[key])
            require(math.isfinite(row[key]), f"nonfinite: {row['subject']} {key}")
            if key.endswith("_R"):
                require(0 <= row[key] <= 1, f"R range: {row['subject']} {key}")
        for reference in ("heading", "cue_proxy"):
            close(row[f"{reference}_late_R"] - row[f"{reference}_early_R"],
                  row[f"{reference}_change"], f"{row['subject']} {reference} change")
        close(row["heading_change"] - row["cue_proxy_change"], row["difference_change"],
              f"{row['subject']} difference identity")
    epg = summary["basnak_epg"]
    require(epg["n_subjects"] == len(rows), "summary n")
    for reference in ("heading", "cue_proxy"):
        component = epg["components"][reference]
        for stage in ("early", "late"):
            close(statistics.mean(r[f"{reference}_{stage}_R"] for r in rows),
                  component[f"{stage}_mean"], f"{reference} {stage} mean")
        close(statistics.mean(r[f"{reference}_change"] for r in rows),
              component["change"]["mean"], f"{reference} change mean")
        require(sum(r[f"{reference}_change"] > 0 for r in rows) == component["change"]["increased"],
                f"{reference} increase count")
        require(sum(r[f"{reference}_change"] < 0 for r in rows) == component["change"]["decreased"],
                f"{reference} decrease count")
    close(statistics.mean(r["difference_change"] for r in rows), epg["difference_change"]["mean"],
          "difference mean")
    require(sum(r["difference_change"] > 0 for r in rows) == epg["difference_change"]["increased"],
            "difference increase count")
    require(sum(r["heading_change"] > 0 and r["cue_proxy_change"] < 0 for r in rows)
            == epg["both_heading_increase_and_cue_decrease"], "joint count")
    counter = next(r for r in rows if r["subject"] == "sub-27_gain")
    require(counter["heading_change"] < 0 < counter["difference_change"], "sub-27 counterexample")

    baseline = summary["artificial_baseline"]
    n = baseline["common_confirmation"]["n"]
    for result in baseline["selected_totals"]:
        require(0 <= result["correct"] <= result["n"], "baseline count bounds")
    pairs = baseline["common_confirmation"]["normal_to_specified"]
    require(sum(pairs[k] for k in ["both_correct", "both_wrong", "recovered", "damaged"]) == n,
            "paired baseline denominator")
    require(pairs["both_correct"] + pairs["damaged"] == baseline["common_confirmation"]["normal_correct"],
            "normal baseline count")
    require(pairs["both_correct"] + pairs["recovered"] == baseline["common_confirmation"]["specified_correct"],
            "specified baseline count")

    intermittent = [i % 5 == 0 for i in range(100)]
    sustained = [i < 20 for i in range(100)]
    synthetic = summary["synthetic_counterexample"]
    for name, values in [("intermittent", intermittent), ("sustained", sustained)]:
        angles = [math.pi if value else 0 for value in values]
        close(concentration(angles), synthetic["R"], f"synthetic {name} R")
        close(concentration([a + 0.7 for a in angles]), synthetic["R"], "rotation invariance")
        close(longest_run(values) / synthetic["samples_per_second"],
              synthetic[f"{name}_longest_seconds"], f"synthetic {name} duration")
    return {"status": "pass", "artifacts_hashed": len(paths), "subjects_reaggregated": len(rows),
            "checks": ["references", "component_means_and_counts", "difference_identities",
                       "sub27_counterexample", "baseline_count_arithmetic", "synthetic_time_order"],
            "not_reproduced": ["raw_fluorescence_phase_fits", "bootstrap_intervals",
                               "upstream_notebook_processing", "original_model_predictions",
                               "biological_or_artificial_function"]}


if __name__ == "__main__":
    try:
        result = verify(Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
