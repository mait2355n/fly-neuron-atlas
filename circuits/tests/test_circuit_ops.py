"""Independent finite graph oracles and exercised fault challenges.

Run from the repository root: python3 circuits/tests/test_circuit_ops.py
Generated fixtures and CLI artifacts remain beneath .local/circuit-publication/.
"""
from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

BUNDLE = Path(__file__).resolve().parents[1]
ENGINE = BUNDLE / "circuit_ops.py"
spec = importlib.util.spec_from_file_location("circuit_ops_under_test", ENGINE)
ops = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ops
spec.loader.exec_module(ops)
PREFIX = "male-cns:v1.0:"
IDS = {i: PREFIX + str(i) for i in range(1, 7)}
REF = "handwritten-evidence.json#sha256=" + "a" * 64
# Literal edge oracle: directed, asymmetric, self-edge, external remainder.
ORACLE = {
    (1, 2): (7, None, 3),
    (2, 1): (11, 5, None),
    (1, 1): (2, None, None),
    (3, 1): (13, 6, 7),
    (2, 4): (17, 8, 9),
    (3, 4): (19, 9, 10),
    (6, 1): (23, 11, 12),
    (6, 2): (29, 14, 15),
}
SNAPSHOT = {"dataset": "male-cns:v1.0", "uuid": "fixture-snapshot", "tag": "fixture-v1", "latestMutationId": "17"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fixture():
    nodes = {
        IDS[i]: {"bodyId": str(i), "entity_id": IDS[i], "type": "same-name" if i in (1, 2) else None,
                 "is_neuron": False if i == 4 else True,
                 "ref": ("same-name" if i in (1, 2) else "untyped") + "・" + IDS[i]}
        for i in range(1, 7)
    }
    edges = {(IDS[a], IDS[b]): dict(zip(("weight", "weightHP", "weightHR"), values), source_refs=[REF])
             for (a, b), values in ORACLE.items()}
    return ops.Graph(copy.deepcopy(SNAPSHOT), nodes, edges, (IDS[1], IDS[2], IDS[5]),
                     {"representation": "handwritten", "complete_biological_system": False,
                      "source": {"internal": {"status": "complete_induced"}, "incoming": {"status": "partial"},
                                 "outgoing": {"status": "not_acquired"}}})


def edge_values(graph):
    return {key: tuple(edge[name] for name in ("weight", "weightHP", "weightHR"))
            for key, edge in graph.edges.items()}


def expected_edges(keys):
    return {(IDS[a], IDS[b]): ORACLE[(a, b)] for a, b in keys}


class Cases(unittest.TestCase):
    challenges = []
    cli_observations = []

    def setUp(self):
        self.g = fixture()
        self.temp = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN_DIR))

    def reject(self, fault, call, reason):
        try:
            call()
        except ValueError as exc:
            self.assertIn(reason, str(exc), "fault rejected for an unexpected reason")
            self.challenges.append({"test": self._testMethodName, "fault": fault, "result": "detected",
                                    "error_type": type(exc).__name__, "message": str(exc)})
        else:
            self.challenges.append({"test": self._testMethodName, "fault": fault, "result": "survived"})
            self.fail("declared fault survived: " + fault)

    def cli(self, *args, exit_code=0, reason=None):
        p = subprocess.run([sys.executable, str(ENGINE), *map(str, args)], cwd=BUNDLE, text=True, encoding="utf-8",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.cli_observations.append({"test": self._testMethodName, "argv": list(map(str, args)),
                                      "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr})
        self.assertEqual(p.returncode, exit_code)
        message = json.loads(p.stdout if exit_code == 0 else p.stderr)
        self.assertEqual(message["status"], "ok" if exit_code == 0 else "error")
        self.assertEqual(p.stderr if exit_code == 0 else p.stdout, "")
        if reason:
            self.assertIn(reason, message["error"]["message"])
        return message

    def source_fixture(self):
        source = self.temp / "source"
        source.mkdir()
        raw = source / "handwritten-evidence.json"
        save_json(raw, {"provenance": "independently handwritten synthetic input", "edges": [list(k) + list(v) for k, v in ORACLE.items()]})
        save_json(source / "sources.json", [{"id": "raw", "path": str(raw.relative_to(BUNDLE.parent)),
                                            "sha256": sha(raw), "size_bytes": raw.stat().st_size, "role": "fixture"}])
        save_json(source / "nodes.json", [{"bodyId": str(i), "type": "same-name" if i in (1, 2) else None,
                                          "is_neuron": True} for i in (1, 2, 5)])
        with gzip.open(source / "edges.csv.gz", "wt", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["bodyId_pre", "bodyId_post", "weight", "weightHP", "weightHR", "pre_is_neuron", "post_is_neuron", "source_ids"])
            for (a, b), (w, hp, hr) in ORACLE.items():
                if (a, b) == (3, 4):
                    continue  # Source contract is incident-only; API fixture covers the remainder.
                writer.writerow([a, b, w, hp, hr, "false" if a == 4 else "true", "false" if b == 4 else "true", '["raw"]'])
        save_json(source / "set_manifest.json", {
            "schema_version": "circuit-source-set/v1", "name": "handwritten_fixture", "dataset": SNAPSHOT["dataset"],
            "snapshot": {k: v for k, v in SNAPSHOT.items() if k != "dataset"}, "selected_ids": ["1", "2", "5"],
            "edges_file": "edges.csv.gz", "nodes_file": "nodes.json", "sources_file": "sources.json",
            "coverage": {"internal": {"status": "complete_induced", "basis": "literal finite fixture"},
                         "incoming": {"status": "partial", "basis": "synthetic sample"},
                         "outgoing": {"status": "not_acquired", "basis": "synthetic unknown coverage marker"}},
            "notes": ["This is not a biological observation."]})
        return source / "set_manifest.json"

    def test_fixture_oracle_and_partition(self):
        self.assertEqual(edge_values(ops.validate(self.g)), expected_edges(ORACLE))
        s = ops.stats(self.g)
        self.assertEqual((s["nodes"], s["selected"], s["edges"], s["weight"]), (6, 3, 8, 121))
        self.assertEqual(s["partition"], {"internal": {"edges": 3, "weight": 20},
                                         "incoming": {"edges": 3, "weight": 65},
                                         "outgoing": {"edges": 1, "weight": 17},
                                         "other": {"edges": 1, "weight": 19}})

    def test_cut_literal_oracle_and_reconnect(self):
        r = ops.cut(self.g, (IDS[1], IDS[2], IDS[5]))
        self.assertEqual(set(r["inside"].nodes), {IDS[1], IDS[2], IDS[5]})
        self.assertEqual(edge_values(r["inside"]), expected_edges([(1, 2), (2, 1), (1, 1)]))
        self.assertEqual(set(r["boundary"].nodes), set(IDS.values()))
        self.assertEqual(edge_values(r["boundary"]), expected_edges([(3, 1), (2, 4), (3, 4), (6, 1), (6, 2)]))
        restored = ops.reconnect(r)
        self.assertEqual(edge_values(restored), expected_edges(ORACLE))
        self.assertEqual(restored.nodes, self.g.nodes)
        self.assertEqual(restored.selected_ids, self.g.selected_ids)
        self.assertEqual(restored.coverage, self.g.coverage)

    def test_empty_and_whole_cuts_preserve_isolate(self):
        for ids in ([], list(IDS.values())):
            r = ops.cut(self.g, ids)
            self.assertEqual(len(r["inside"].edges), 0 if not ids else 8)
            self.assertEqual(edge_values(ops.reconnect(r)), expected_edges(ORACLE))
            self.assertIn(IDS[5], ops.reconnect(r).nodes)

    def test_merge_shared_identity_and_same_label(self):
        a = ops.cut(self.g, [IDS[1], IDS[2], IDS[5]])["inside"]
        b = ops.cut(self.g, [IDS[2], IDS[4]])["inside"]
        merged = ops.merge([a, b])
        self.assertEqual(set(merged.nodes), {IDS[1], IDS[2], IDS[4], IDS[5]})
        self.assertEqual(edge_values(merged), expected_edges([(1, 2), (2, 1), (1, 1), (2, 4)]))
        self.assertEqual(merged.nodes[IDS[1]]["type"], merged.nodes[IDS[2]]["type"])
        self.assertNotEqual(merged.nodes[IDS[1]]["entity_id"], merged.nodes[IDS[2]]["entity_id"])

    def test_merge_combines_independent_provenance(self):
        b = copy.deepcopy(self.g)
        b.edges[(IDS[1], IDS[2])]["source_refs"] = ["second.json#sha256=" + "b" * 64]
        merged = ops.merge([self.g, b])
        self.assertEqual(edge_values(merged), expected_edges(ORACLE))
        self.assertEqual(merged.edges[(IDS[1], IDS[2])]["source_refs"], sorted([REF, "second.json#sha256=" + "b" * 64]))

    def test_clone_shared_node_literal_oracle(self):
        cloned, changes = ops.clone_node(self.g, IDS[6], "shared-copy")
        clone = changes["clone"]
        self.assertEqual(set(cloned.nodes), set(IDS.values()) | {clone})
        self.assertEqual(edge_values(cloned), {**expected_edges(ORACLE), (clone, IDS[1]): (23, 11, 12), (clone, IDS[2]): (29, 14, 15)})
        self.assertEqual(cloned.nodes[clone]["derived_from"], IDS[6])
        self.assertFalse(cloned.nodes[clone]["biological_instance"])
        self.assertNotEqual(cloned.nodes[clone]["ref"], self.g.nodes[IDS[6]]["ref"])
        self.assertEqual(len(changes["added_edges"]), 2)
        self.assertEqual(changes["removed"], [])
        self.assertEqual(ops.clone_node(self.g, IDS[6], "shared-copy")[1]["clone"], clone)

    def test_clone_self_edge_and_selected_identity(self):
        cloned, changes = ops.clone_node(self.g, IDS[1], "self-copy")
        clone = changes["clone"]
        extra = {(clone, IDS[2]): (7, None, 3), (IDS[2], clone): (11, 5, None),
                 (clone, clone): (2, None, None), (IDS[3], clone): (13, 6, 7), (IDS[6], clone): (23, 11, 12)}
        self.assertEqual(edge_values(cloned), {**expected_edges(ORACLE), **extra})
        self.assertIn(clone, cloned.selected_ids)
        self.assertNotIn((clone, IDS[1]), cloned.edges)
        self.assertNotIn((IDS[1], clone), cloned.edges)

    def test_drop_literal_oracle_and_change_receipt(self):
        dropped, changes = ops.drop_edges(self.g, lambda pair, edge: edge["weight"] < 10)
        self.assertEqual(edge_values(dropped), expected_edges([(2, 1), (3, 1), (2, 4), (3, 4), (6, 1), (6, 2)]))
        self.assertEqual({(r["pre"], r["post"]) for r in changes["removed"]}, {(IDS[1], IDS[1]), (IDS[1], IDS[2])})
        self.assertEqual(set(dropped.nodes), set(IDS.values()))
        self.assertFalse(changes["biological_function_verified"])

    def test_swap_literal_oracle_weights_follow_source(self):
        changed, receipt = ops.swap_targets(self.g, (IDS[6], IDS[2]), (IDS[3], IDS[4]))
        expected = expected_edges([(1, 2), (2, 1), (1, 1), (3, 1), (2, 4), (6, 1)])
        expected.update({(IDS[6], IDS[4]): (29, 14, 15), (IDS[3], IDS[2]): (19, 9, 10)})
        self.assertEqual(edge_values(changed), expected)
        self.assertEqual(sum(e["weight"] for e in changed.edges.values()), 121)
        self.assertEqual(len(receipt["removed"]), 2)
        self.assertEqual(len(receipt["added_edges"]), 2)

    def test_reconnect_rejects_missing_edge(self):
        r = copy.deepcopy(ops.cut(self.g, self.g.selected_ids))
        del r["boundary"].edges[(IDS[6], IDS[2])]
        self.reject("one shared boundary edge removed", lambda: ops.reconnect(r), "does not restore original structure")

    def test_reconnect_rejects_changed_weight(self):
        for name in ("weight", "weightHP", "weightHR"):
            r = copy.deepcopy(ops.cut(self.g, self.g.selected_ids))
            r["inside"].edges[(IDS[1], IDS[2])][name] = 999
            self.reject(name + " altered", lambda: ops.reconnect(r), "does not restore original structure")

    def test_reconnect_rejects_coverage_changed(self):
        r = copy.deepcopy(ops.cut(self.g, self.g.selected_ids))
        r["original_coverage"]["complete_biological_system"] = True
        self.reject("partial coverage promoted to complete", lambda: ops.reconnect(r), "does not restore original structure")

    def test_reconnect_rejects_shared_identity_split(self):
        r = copy.deepcopy(ops.cut(self.g, self.g.selected_ids))
        r["boundary"], _ = ops.clone_node(r["boundary"], IDS[6], "accidental-split")
        self.reject("shared original silently duplicated", lambda: ops.reconnect(r), "does not restore original structure")

    def test_merge_rejects_snapshot_mixture(self):
        for name in ("uuid", "tag", "latestMutationId"):
            b = copy.deepcopy(self.g)
            b.snapshot[name] += "-changed"
            self.reject("mixed snapshot " + name, lambda: ops.merge([self.g, b]), "snapshot mismatch")

    def test_merge_rejects_weight_and_annotation_conflicts(self):
        b = copy.deepcopy(self.g)
        b.edges[(IDS[1], IDS[2])]["weightHP"] = 0
        self.reject("unknown HP replaced with measured zero", lambda: ops.merge([self.g, b]), "edge weight conflict")
        b = copy.deepcopy(self.g)
        b.nodes[IDS[2]]["type"] = "other"
        self.reject("same identity conflicting annotation", lambda: ops.merge([self.g, b]), "node annotation conflict")

    def test_missing_source_refs_rejected(self):
        self.g.edges[(IDS[1], IDS[2])]["source_refs"] = []
        self.reject("edge provenance removed", lambda: ops.validate(self.g), "source provenance missing")

    def test_double_clone_rejected(self):
        g, _ = ops.clone_node(self.g, IDS[6], "same-tag")
        self.reject("same clone tag applied twice", lambda: ops.clone_node(g, IDS[6], "same-tag"), "clone tag already applied")

    def test_clone_original_raw_identity_rejected(self):
        g, change = ops.clone_node(self.g, IDS[6], "bad-identity")
        g.nodes[change["clone"]]["ref"] = IDS[6]
        self.reject("clone ref changed to original raw ID", lambda: ops.validate(g), "compact ref identity mismatch")

    def test_clone_original_label_ref_rejected(self):
        g, change = ops.clone_node(self.g, IDS[6], "bad-label-ref")
        g.nodes[change["clone"]]["ref"] = self.g.nodes[IDS[6]]["ref"]
        self.reject("clone ref changed to original label and ID", lambda: ops.validate(g), "compact ref identity mismatch")

    def test_clone_lineage_matches_original_body_id(self):
        for wrong in ("male-cns:v1.0:nonexistent", IDS[2]):
            g, change = ops.clone_node(self.g, IDS[6], "bad-lineage")
            g.nodes[change["clone"]]["derived_from"] = wrong
            self.reject("clone lineage changed to " + wrong, lambda: ops.validate(g), "clone biological lineage mismatch")

    def test_clone_only_cut_retains_external_lineage(self):
        g, change = ops.clone_node(self.g, IDS[6], "isolated-clone-cut")
        clone = change["clone"]
        inside = ops.cut(g, [clone])["inside"]
        self.assertEqual(set(inside.nodes), {clone})
        self.assertEqual(inside.nodes[clone]["derived_from"], IDS[6])
        self.assertNotIn(IDS[6], inside.nodes)
        ops.validate(inside)

    def test_swap_rejects_collision_or_shared_endpoint(self):
        self.reject("swap would overwrite existing edge", lambda: ops.swap_targets(self.g, (IDS[3], IDS[1]), (IDS[2], IDS[4])), "collides with existing edge")
        self.reject("swap shares an endpoint", lambda: ops.swap_targets(self.g, (IDS[1], IDS[2]), (IDS[2], IDS[4])), "four distinct endpoints")

    def test_saved_graph_independent_decode_and_relocation(self):
        out = self.temp / "export"
        ops.write_graph(self.g, out)
        doc = json.loads((out / "graph.json").read_text(encoding='utf-8'))
        self.assertEqual(set(doc["nodes"]), set(IDS.values()))
        with gzip.open(out / "edges.csv.gz", "rt", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        decoded = {(r["bodyId_pre"], r["bodyId_post"]): tuple(None if r[n] == "" else int(r[n]) for n in ("weight", "weightHP", "weightHR")) for r in rows}
        self.assertEqual(decoded, expected_edges(ORACLE))
        self.assertTrue(all(json.loads(r["source_refs"]) == [REF] for r in rows))
        relocated = self.temp / "different-parent" / "moved-export"
        relocated.parent.mkdir()
        shutil.copytree(out, relocated)
        shutil.rmtree(out)
        restored = ops.read_graph(relocated)
        self.assertEqual(edge_values(restored), expected_edges(ORACLE))
        self.cli("verify-graph", relocated)

    def test_export_corruption_detected_by_file_and_semantic_hash(self):
        for mode in ("graph-bytes", "edge-bytes", "manifest-laundered-weight"):
            out = self.temp / mode
            ops.write_graph(self.g, out)
            if mode == "graph-bytes":
                with (out / "graph.json").open("a", encoding="utf-8") as f:
                    f.write(" ")
                reason = "export file hash mismatch"
            elif mode == "edge-bytes":
                with (out / "edges.csv.gz").open("ab") as f:
                    f.write(b"corrupt")
                reason = "export file hash mismatch"
            else:
                with gzip.open(out / "edges.csv.gz", "rt", encoding="utf-8") as f:
                    text = f.read()
                text = text.replace(PREFIX + "1," + PREFIX + "2,7,", PREFIX + "1," + PREFIX + "2,99,")
                with gzip.open(out / "edges.csv.gz", "wt", encoding="utf-8") as f:
                    f.write(text)
                manifest = json.loads((out / "manifest.json").read_text(encoding='utf-8'))
                manifest["files"]["edges.csv.gz"] = sha(out / "edges.csv.gz")
                save_json(out / "manifest.json", manifest)
                reason = "export semantic fingerprint mismatch"
            self.reject(mode, lambda: ops.read_graph(out), reason)

    def test_cli_input_demo_and_existing_output(self):
        source = self.source_fixture()
        inspection = self.cli("inspect", source)["result"]
        self.assertEqual((inspection["nodes"], inspection["edges"], inspection["weight"]), (6, 7, 102))
        self.assertEqual(self.cli("verify-inputs", source)["result"]["sources_checked"], 1)
        out = self.temp / "demo"
        result = self.cli("demo", source, "--out", out)["result"]
        self.assertTrue(result["roundtrip_exact"])
        self.assertEqual(result["shared_external_input_ids"], 1)
        self.assertFalse(result["two_target_swap_available"])
        restored = ops.read_graph(out / "reconnected")
        self.assertEqual(edge_values(restored), expected_edges([k for k in ORACLE if k != (3, 4)]))
        old = sha(out / "RESULT.json")
        self.cli("demo", source, "--out", out, exit_code=2, reason="output already exists")
        self.assertEqual(sha(out / "RESULT.json"), old)

    def test_cli_broken_json_missing_file_and_source_hash(self):
        broken = self.temp / "broken.json"
        broken.write_text("{bad JSON", encoding="utf-8")
        self.cli("inspect", broken, exit_code=2, reason="property name")
        self.cli("inspect", self.temp / "absent.json", exit_code=2, reason="No such file")
        source = self.source_fixture()
        self.cli("verify-inputs", source)
        (source.parent / "handwritten-evidence.json").write_text("changed", encoding="utf-8")
        self.cli("verify-inputs", source, exit_code=2, reason="source hash mismatch")

    def test_cli_truncated_gzip_is_input_error(self):
        source = self.source_fixture()
        self.cli("inspect", source)
        edge_file = source.parent / "edges.csv.gz"
        edge_file.write_bytes(edge_file.read_bytes()[:-8])
        self.cli("inspect", source, exit_code=2, reason="end-of-stream")

    def test_operation_outputs_do_not_alias_original(self):
        # A caller can edit a returned graph while retaining the original as a baseline.
        # These mutations are deliberately on the result, after the operation has returned.
        for name in ("cut", "clone", "drop", "swap"):
            g = fixture()
            baseline = copy.deepcopy(g)
            if name == "cut":
                out = ops.cut(g, g.selected_ids)["inside"]
            elif name == "clone":
                out, _ = ops.clone_node(g, IDS[6], "independent-copy")
            elif name == "drop":
                out, _ = ops.drop_edges(g, lambda k, e: e["weight"] > 20)
            else:
                out, _ = ops.swap_targets(g, (IDS[6], IDS[2]), (IDS[3], IDS[4]))
            out.edges[(IDS[1], IDS[2])]["weight"] = 777
            with self.subTest(operation=name):
                self.assertEqual(g, baseline, "output edge mutation changed retained original")

    def test_operation_node_outputs_do_not_alias_original(self):
        for name in ("cut", "clone", "drop", "swap"):
            g = fixture()
            g.nodes[IDS[1]]["annotation"] = {"nested": ["preserved"]}
            baseline = copy.deepcopy(g)
            if name == "cut":
                out = ops.cut(g, g.selected_ids)["inside"]
            elif name == "clone":
                out, _ = ops.clone_node(g, IDS[6], "independent-node-copy")
            elif name == "drop":
                out, _ = ops.drop_edges(g, lambda k, e: e["weight"] > 20)
            else:
                out, _ = ops.swap_targets(g, (IDS[6], IDS[2]), (IDS[3], IDS[4]))
            out.nodes[IDS[1]]["annotation"]["nested"].append("mutated-result")
            with self.subTest(operation=name):
                self.assertEqual(g, baseline, "output nested node mutation changed retained original")


class JSONResult(unittest.TextTestResult):
    observations = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.observations.append({"test": test.id(), "status": "pass"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.observations.append({"test": test.id(), "status": "fail", "detail": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.observations.append({"test": test.id(), "status": "error", "detail": self._exc_info_to_string(err, test)})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.observations.append({"test": subtest.id(), "status": "fail", "detail": self._exc_info_to_string(err, test)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BUNDLE.parent / ".local" / "circuit-publication" / "synthetic.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fixture_root = BUNDLE.parent / ".local" / "circuit-publication"
    fixture_root.mkdir(parents=True, exist_ok=True)
    RUN_DIR = Path(tempfile.mkdtemp(prefix="fixtures-", dir=fixture_root))
    before_hash = sha(ENGINE)
    result = unittest.TextTestRunner(verbosity=2, resultclass=JSONResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
    receipt = {"schema_version": "circuit-independent-verification/v1", "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "engine_sha256": before_hash, "engine_sha256_after": sha(ENGINE), "test_script_sha256": sha(__file__),
               "environment": {"platform": platform.platform(), "python": sys.version, "executable": sys.executable},
               "fixture_directory": str(RUN_DIR.relative_to(BUNDLE.parent)), "tests_run": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors), "success": result.wasSuccessful(),
               "tests": result.observations, "detection_challenges": Cases.challenges, "cli_observations": Cases.cli_observations,
               "oracle": "handwritten six-node, eight-edge finite directed graph with literal expected node and weight tuples",
               "unverified": ["neural activity", "plasticity", "behavior", "artificial subject utility", "concurrent writers", "interrupted process recovery", "installed package"]}
    save_json(args.output, receipt)
    print(json.dumps({"receipt": str(args.output), "success": result.wasSuccessful(), "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors)}, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
