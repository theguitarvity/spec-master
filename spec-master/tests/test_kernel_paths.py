import unittest

import _pathfix  # noqa: F401
from kernel import paths


class PathTests(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(paths.norm("./././src/a.py"), "src/a.py")
        self.assertEqual(paths.norm("  src/a.py "), "src/a.py")
        self.assertEqual(paths.norm(None), "")

    def test_test_paths_by_directory_and_by_name(self):
        for path in ("tests/test_x.py", "src/test/java/CalcTest.java", "web/src/Button.test.tsx",
                     "web/src/Button.spec.ts", "pkg/calc_test.go", "Foo.Tests/CalcTests.cs", "a/__tests__/x.js"):
            with self.subTest(path=path):
                self.assertTrue(paths.is_test_path(path))
        for path in ("src/latest.py", "src/contest.py", "src/attestation.py", "src/protest/handler.py"):
            with self.subTest(path=path):
                self.assertFalse(paths.is_test_path(path))

    def test_docs_manifests_and_harness_files(self):
        self.assertTrue(paths.is_doc_path("docs/guide.md"))
        self.assertTrue(paths.is_doc_path("CHANGELOG.rst"))
        self.assertFalse(paths.is_doc_path("src/docs.py"))
        self.assertTrue(paths.is_manifest("requirements-dev.txt"))
        self.assertTrue(paths.is_manifest("web/package.json"))
        self.assertFalse(paths.is_manifest("src/package.py"))
        self.assertTrue(paths.is_harness(".spec-master/changes/c1.md"))
        self.assertTrue(paths.is_harness("specs/001-x/spec.md"))

    def test_production_files_and_modules(self):
        self.assertEqual(paths.production_files(["src/a.py", "tests/test_a.py", "README.md", ".spec-master/x.json",
                                                 "./src/b.py", ""]), ["src/a.py", "src/b.py"])
        self.assertEqual(paths.module_of("src/pkg/a.py"), "src/pkg")
        self.assertEqual(paths.module_of("setup.py"), ".")


if __name__ == "__main__":
    unittest.main()
