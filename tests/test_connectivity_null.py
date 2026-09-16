import importlib.util
from collections import Counter
from pathlib import Path
import random
import unittest

spec = importlib.util.spec_from_file_location('null_model',Path(__file__).resolve().parents[1]/'scripts/shared_connectivity_null.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class DegreeNullTests(unittest.TestCase):
    def test_degrees_and_unique_edges_survive_actual_swaps(self):
        edges=[('a','1'),('a','2'),('b','2'),('b','3'),('c','3'),('c','4'),('d','4'),('d','1')]
        result, accepted=module.rewire(edges,random.Random(42),1000)
        self.assertGreater(accepted,0)
        self.assertEqual(Counter(a for a,b in result),Counter(a for a,b in edges))
        self.assertEqual(Counter(b for a,b in result),Counter(b for a,b in edges))
        self.assertEqual(len(set(result)),len(edges))
        self.assertEqual(module.rewire(edges,random.Random(42),1000),(result,accepted))

    def test_multiple_motor_targets_in_one_group_are_not_shared(self):
        self.assertEqual(module.group_counts([('a','1'),('a','2'),('b','2'),('b','3')],
                                            {'1':'x','2':'x','3':'y'}),{'a':1,'b':2})

    def test_duplicate_input_edge_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            module.rewire([('a','1'),('a','1')],random.Random(1),10)


if __name__ == '__main__':
    unittest.main()
