import argparse
import unittest

import _pathfix  # noqa: F401
import standard_lane_args


class RegisterTests(unittest.TestCase):
    def _parse(self, argv):
        parser = argparse.ArgumentParser()
        standard_lane_args.register(parser.add_subparsers(dest="cmd"))
        return parser.parse_args(argv)

    def test_begin_requires_intent_and_takes_shared_options(self):
        args = self._parse(["standard", "begin", "--intent", "fix it", "--paths", "a.py", "--change", "c1"])
        self.assertEqual((args.standard_action, args.intent, args.paths, args.change, args.path),
                         ("begin", "fix it", "a.py", "c1", "."))

    def test_red_and_green_take_a_test_command(self):
        for action in ("red", "green"):
            args = self._parse(["standard", action, "--test-command", "make test"])
            self.assertEqual((args.standard_action, args.test_command), (action, "make test"))

    def test_registering_does_not_import_the_lane_logic(self):
        self.assertNotIn("verify_pre", standard_lane_args.__dict__)
        self.assertNotIn("tdd_gates", standard_lane_args.__dict__)


if __name__ == "__main__":
    unittest.main()
