import os
import unittest
from collections import OrderedDict
from unittest import mock
from unittest.mock import mock_open

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import memoize
from flake8_requirements.checker import parse_requirements


def mock_open_with_name(read_data="", name="file.name"):
    """Mock open call with a specified `name` attribute."""
    m = mock_open(read_data=read_data)
    m.return_value.name = name
    return m


def mock_open_multiple(files=OrderedDict()):
    """Create a mock open object for multiple files."""
    m = mock_open()
    m.side_effect = [
        mock_open_with_name(read_data=content, name=name).return_value
        for name, content in files.items()
    ]
    return m


class RequirementsTestCase(unittest.TestCase):

    def setUp(self):
        memoize.mem = {}

    def test_resolve_requirement(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("foo >= 1.0.0"),
            ["foo >= 1.0.0"],
        )

    def test_resolve_requirement_with_option(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("foo-bar.v1==1.0 --hash=md5:."),
            ["foo-bar.v1==1.0"],
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
        with mock.patch('builtins.open', mock_open()) as m:
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                [],
            )
            m.assert_called_once_with("requirements.txt")

    def test_resolve_requirement_with_file_content(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo >= 1.0.0\nbar <= 1.0.0\n"),
        )))):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                ["foo >= 1.0.0", "bar <= 1.0.0"],
            )

    def test_resolve_requirement_with_file_content_line_continuation(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo[bar] \\\n>= 1.0.0\n"),
        )))):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                ["foo[bar] >= 1.0.0"],
            )

    def test_resolve_requirement_with_file_content_line_continuation_2(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo \\\n>= 1.0.0 \\\n# comment \\\nbar \\"),
        )))):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),
                ["foo >= 1.0.0", "bar"],
            )

    def test_resolve_requirement_with_file_recursion_beyond_max_depth(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "-r requirements.txt\n"),
        )))):
            with self.assertRaises(RuntimeError):
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),

    def test_resolve_requirement_with_file_recursion(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "--requirement inner.txt\nbar <= 1.0.0\n"),
            ("inner.txt", "# inner\nbaz\n\nqux\n"),
        )))):
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 2),
                ["baz", "qux", "bar <= 1.0.0"],
            )

    def test_resolve_requirement_with_relative_include(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "-r requirements/production.txt"),
            ("requirements/production.txt", "-r node/one.txt\nfoo"),
            ("requirements/node/one.txt", "-r common.txt\n-r /abs/path.txt"),
            ("requirements/node/common.txt", "bar"),
            ("/abs/path.txt", "bis"),
        )))) as m:
            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 5),
                ["bar", "bis", "foo"],
            )
            m.assert_has_calls([
                mock.call("requirements.txt"),
                mock.call("requirements/production.txt"),
                mock.call("requirements/node/one.txt"),
                mock.call("requirements/node/common.txt"),
                mock.call("/abs/path.txt"),
            ])

    def test_init_with_no_requirements(self):
        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = IOError("No such file or directory"),
            checker = Flake8Checker(None, None)
            self.assertEqual(checker.get_requirements_txt(), ())

    def test_init_with_user_requirements(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements/base.txt", "foo >= 1.0.0\n-r inner.txt\n"),
            ("requirements/inner.txt", "bar\n"),
        )))) as m:
            try:
                Flake8Checker.requirements_file = "requirements/base.txt"
                checker = Flake8Checker(None, None)
                self.assertEqual(
                    checker.get_requirements_txt(),
                    tuple(parse_requirements([
                        "foo >= 1.0.0",
                        "bar",
                    ])),
                )
                m.assert_has_calls([
                    mock.call("requirements/base.txt"),
                    mock.call("requirements/inner.txt"),
                ])
            finally:
                Flake8Checker.requirements_file = None

    def test_init_with_simple_requirements(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo >= 1.0.0\nbar <= 1.0.0\n"),
        )))):
            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_requirements_txt(),
                tuple(parse_requirements([
                    "foo >= 1.0.0",
                    "bar <= 1.0.0",
                ])),
            )

    def test_init_with_recursive_requirements_beyond_max_depth(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"),
            ("inner.txt", "# inner\nbaz\n\nqux\n"),
        )))):
            with self.assertRaises(RuntimeError):
                try:
                    Flake8Checker.requirements_max_depth = 0
                    checker = Flake8Checker(None, None)
                    checker.get_requirements_txt()
                finally:
                    Flake8Checker.requirements_max_depth = 1

    def test_init_with_recursive_requirements(self):
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"),
            ("inner.txt", "# inner\nbaz\n\nqux\n"),
        )))):
            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_requirements_txt(),
                tuple(parse_requirements([
                    "foo >= 1.0.0",
                    "baz",
                    "qux",
                    "bar <= 1.0.0",
                ])),
            )

    def test_init_misc(self):
        curdir = os.path.abspath(os.path.dirname(__file__))
        with open(os.path.join(curdir, "test_requirements.txt")) as f:
            requirements_content = f.read()
        with mock.patch('builtins.open', mock_open_multiple(files=OrderedDict((
            ("requirements.txt", requirements_content),
        )))):
            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_requirements_txt(),
                tuple(parse_requirements([
                    "nose",
                    "apache == 0.6.9",
                    "coverage[graph,test] ~= 3.1",
                    "graph <2.0, >=1.2 ; python_version < '3.8'",
                    "foo-project >= 1.2",
                    "bar-project == 8.8",
                    "configuration",
                    "blackBox == 1.4.4",
                    "exPackage_paint == 1.4.8.dev1984+49a8814",
                    "package-one",
                    "package-two",
                    "whiteBox",
                ])),
            )
