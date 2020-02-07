import unittest

from pkg_resources import parse_requirements

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import memoize

try:
    from unittest import mock
    builtins_open = 'builtins.open'
except ImportError:
    import mock
    builtins_open = '__builtin__.open'


class RequirementsTestCase(unittest.TestCase):

    def setUp(self):
        memoize.mem = {}

    def test_resolve_requirement(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("foo >= 1.0.0"),
            ["foo"],
        )

    def test_resolve_requirement_with_option(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("foo-bar.v1==1.0 --option"),
            ["foo-bar.v1"],
        )

    def test_resolve_requirement_standalone_option(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("--extra-index-url"),
            [],
        )

    def test_resolve_requirement_with_file_beyond_max_depth(self):
        with self.assertRaises(RuntimeError):
            Flake8Checker.resolve_requirement("-r requirements.txt")

    def test_resolve_requirement_with_file_empty(self):
        with mock.patch(builtins_open, mock.mock_open()) as m:
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                [],
            )
            m.assert_called_once_with("requirements.txt")

    def test_resolve_requirement_with_file_content(self):
        content = "foo >= 1.0.0\nbar <= 1.0.0\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                ["foo", "bar"],
            )

    def test_resolve_requirement_with_file_content_line_continuation(self):
        content = "foo[bar] \\\n>= 1.0.0\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                ["foo"],
            )

    def test_resolve_requirement_with_file_recursion_beyond_max_depth(self):
        content = "-r requirements.txt\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):
            with self.assertRaises(RuntimeError):
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),

    def test_resolve_requirement_with_file_recursion(self):
        content = "--requirement inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                mock.mock_open(read_data=content).return_value,
                mock.mock_open(read_data=inner_content).return_value,
            )

            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 2),
                ["baz", "qux", "bar"],
            )

    def test_init_with_no_requirements(self):
        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = IOError("No such file or directory"),
            checker = Flake8Checker(None, None)
            self.assertEqual(checker.get_requirements_txt(), ())

    def test_init_with_simple_requirements(self):
        content = "foo >= 1.0.0\nbar <= 1.0.0\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):

            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_requirements_txt(),
                tuple(parse_requirements([
                    "foo",
                    "bar",
                ])),
            )

    def test_init_with_recursive_requirements_beyond_max_depth(self):
        content = "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                mock.mock_open(read_data=content).return_value,
                mock.mock_open(read_data=inner_content).return_value,
            )

            with self.assertRaises(RuntimeError):
                try:
                    Flake8Checker.requirements_max_depth = 0
                    checker = Flake8Checker(None, None)
                    checker.get_requirements_txt()
                finally:
                    Flake8Checker.requirements_max_depth = 1

    def test_init_with_recursive_requirements(self):
        content = "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                mock.mock_open(read_data=content).return_value,
                mock.mock_open(read_data=inner_content).return_value,
            )

            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_requirements_txt(),
                tuple(parse_requirements([
                    "foo",
                    "baz",
                    "qux",
                    "bar",
                ])),
            )
