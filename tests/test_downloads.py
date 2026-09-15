"""Recovery uses owned temporary bytes and never destroys an existing file."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reanalyze', ROOT / 'scripts/reanalyze_ephys.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DownloadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'fixed synthetic source bytes'
        self.entry = {'fly':'test', 'bytes':len(self.payload),
                      'md5':hashlib.md5(self.payload).hexdigest(), 'url':'https://example.invalid/test.mat'}
        self.path = self.root / 'test.mat'

    def opener(self, *args, **kwargs):
        return io.BytesIO(self.payload)

    def test_stale_partial_is_preserved_and_does_not_block_retry(self):
        stale = self.root / 'test.mat.part'
        stale.write_bytes(b'interrupted old attempt')
        note = module.download_verified(self.entry, self.path, self.opener)
        self.assertTrue(note['legacy_partial_preserved'])
        self.assertEqual(self.path.read_bytes(), self.payload)
        self.assertEqual(stale.read_bytes(), b'interrupted old attempt')
        self.assertEqual(list(self.root.glob('.test.mat.*.part')), [])

    def test_mid_stream_failure_cleans_up_then_retry_succeeds(self):
        class Interrupted(io.BytesIO):
            def read(self, size=-1):
                if self.tell(): raise OSError('simulated interrupted stream')
                return super().read(4)
        with self.assertRaisesRegex(OSError, 'interrupted'):
            module.download_verified(self.entry, self.path, lambda *a, **k: Interrupted(self.payload))
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.glob('*.part')), [])
        module.download_verified(self.entry, self.path, self.opener)
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_wrong_hash_does_not_leave_a_reusable_file(self):
        wrong = {**self.entry, 'md5':'0'*32}
        with self.assertRaisesRegex(ValueError, 'MD5 differs'):
            module.download_verified(wrong, self.path, self.opener)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.glob('*.part')), [])

    def test_existing_destination_is_not_overwritten(self):
        self.path.write_bytes(b'existing user bytes')
        with self.assertRaisesRegex(ValueError, 'existing destination differs'):
            module.download_verified(self.entry, self.path, self.opener)
        self.assertEqual(self.path.read_bytes(), b'existing user bytes')


if __name__ == '__main__':
    unittest.main()
