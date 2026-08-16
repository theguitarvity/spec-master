import unittest

import _pathfix  # noqa: F401
import feature_model


class FeatureModelTests(unittest.TestCase):
    def test_independent_features_keep_input_order(self):
        features = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": []},
            {"id": "c", "dependencies": []},
        ]
        self.assertEqual(feature_model.order_features(features), ["a", "b", "c"])

    def test_dependency_forces_order(self):
        features = [
            {"id": "c", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
            {"id": "a", "dependencies": []},
        ]
        order = feature_model.order_features(features)
        self.assertLess(order.index("a"), order.index("b"))
        self.assertLess(order.index("b"), order.index("c"))

    def test_diamond_dependency_resolves_once(self):
        features = [
            {"id": "a", "dependencies": []},
            {"id": "b", "dependencies": ["a"]},
            {"id": "c", "dependencies": ["a"]},
            {"id": "d", "dependencies": ["b", "c"]},
        ]
        order = feature_model.order_features(features)
        self.assertEqual(sorted(order), ["a", "b", "c", "d"])
        self.assertEqual(order.index("a"), 0)
        self.assertEqual(order.index("d"), 3)

    def test_cycle_is_detected_not_infinite_loop(self):
        features = [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ]
        with self.assertRaises(feature_model.CycleError):
            feature_model.order_features(features)

    def test_unknown_dependency_ignored_gracefully(self):
        features = [{"id": "a", "dependencies": ["ghost"]}]
        self.assertEqual(feature_model.order_features(features), ["a"])


if __name__ == "__main__":
    unittest.main()
