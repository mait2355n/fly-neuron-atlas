"""Published-input checks: missing evidence must never become verified evidence."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication_ops', HERE / 'circuit_ops.py')
ops = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ops
spec.loader.exec_module(ops)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


class PublishedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'set'
        self.path.mkdir()
        save(self.path / 'nodes.json', [{'bodyId': '1', 'type': '合成神経', 'is_neuron': True}])
        with gzip.open(self.path / 'edges.csv.gz', 'wt', encoding='utf-8') as stream:
            stream.write('bodyId_pre,bodyId_post,weight,weightHP,weightHR,pre_is_neuron,post_is_neuron,source_ids\n')
        self.sources = [{'id': 'archive', 'path': 'nonexistent_archive/raw.json', 'sha256': 'a' * 64,
                         'size_bytes': 100, 'role': 'synthetic', 'availability': 'archival_not_shipped',
                         'path_basis': 'original_research_root'}]
        save(self.path / 'sources.json', self.sources)
        self.manifest = {'schema_version': 'circuit-source-set/v1', 'name': 'synthetic',
                         'dataset': 'male-cns:v1.0', 'snapshot': {'uuid': 'fixture', 'tag': 'v1.0', 'latestMutationId': 1},
                         'selected_ids': ['1'], 'coverage': {}, 'nodes_file': 'nodes.json',
                         'edges_file': 'edges.csv.gz', 'sources_file': 'sources.json',
                         'publication': {'schema_version': 'circuit-published-inputs/v1',
                                         'archival_sources_verified': False, 'files': {}}}
        self.refresh()

    def refresh(self):
        self.manifest['publication']['files'] = {
            name: {'sha256': hashlib.sha256((self.path / name).read_bytes()).hexdigest(),
                   'size_bytes': (self.path / name).stat().st_size}
            for name in ('nodes.json', 'edges.csv.gz', 'sources.json')}
        save(self.path / 'set_manifest.json', self.manifest)

    def verify(self):
        return ops.verify_inputs(self.path / 'set_manifest.json')

    def test_relocation_without_original_archive_preserves_explicit_limit(self):
        destination = Path(self.temp.name) / 'different-parent' / 'moved-input'
        shutil.copytree(self.path, destination)
        shutil.rmtree(self.path)
        self.path = destination
        result = self.verify()
        self.assertEqual(result['published_files_checked'], 3)
        self.assertEqual(result['sources_checked'], 0)
        self.assertFalse(result['archival_sources_verified'])
        self.assertFalse(result['original_retrieval_replay_available'])
        self.assertEqual(ops.stats(ops.load_source(self.path / 'set_manifest.json'))['selected'], 1)
        environment = {**os.environ, 'LC_ALL': 'C', 'PYTHONUTF8': '0', 'PYTHONCOERCECLOCALE': '0'}
        run = subprocess.run([sys.executable, str(HERE / 'circuit_ops.py'), 'inspect',
                              str(self.path / 'set_manifest.json')], env=environment,
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['result']['selected'], 1)

    def test_each_shipped_file_corruption_is_rejected(self):
        for name in ('nodes.json', 'edges.csv.gz', 'sources.json'):
            with self.subTest(name=name):
                path = self.path / name
                before = path.read_bytes()
                path.write_bytes(before + b' ')
                with self.assertRaisesRegex(ValueError, 'published input hash mismatch'):
                    self.verify()
                path.write_bytes(before)

    def test_missing_digest_cannot_weaken_coverage(self):
        del self.manifest['publication']['files']['nodes.json']
        save(self.path / 'set_manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            self.verify()

    def test_nonlocal_filename_is_rejected(self):
        self.manifest['nodes_file'] = '../nodes.json'
        inventory = self.manifest['publication']['files']
        inventory['../nodes.json'] = inventory.pop('nodes.json')
        save(self.path / 'set_manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'filename must be local'):
            self.verify()

    def test_archival_source_cannot_claim_verified(self):
        self.manifest['publication']['archival_sources_verified'] = True
        save(self.path / 'set_manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'must not claim archival'):
            self.verify()

    def test_undeclared_source_availability_is_rejected(self):
        del self.sources[0]['availability']
        save(self.path / 'sources.json', self.sources)
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'archival availability'):
            self.verify()

    def test_duplicate_source_id_is_rejected(self):
        self.sources.append(dict(self.sources[0]))
        save(self.path / 'sources.json', self.sources)
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'duplicate source id'):
            self.verify()

    def test_invalid_archival_hash_is_rejected(self):
        self.sources[0]['sha256'] = 'unknown'
        save(self.path / 'sources.json', self.sources)
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'invalid archival source digest'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
