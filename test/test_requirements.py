from unittest import TestCase

from pkg_resources import parse_requirements

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import memoize

try:
    from unittest import mock
    builtins_open = 'builtins.open'
except ImportError:
    import mock
    builtins_open = '__builtin__.open'


class RequirementsTestCase(TestCase):

    def test_resolve_requirement_with_blank(self):
        self.assertEqual(Flake8Checker.resolve_requirement(""), [])

    def test_resolve_requirement_with_comment(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("#-r requirements.txt"),
            [],
        )

    def test_resolve_requirement_with_simple(self):
        self.assertEqual(
            Flake8Checker.resolve_requirement("foo >= 1.0.0"),
            ["foo >= 1.0.0"],
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
                ["foo >= 1.0.0", "bar <= 1.0.0"],
            )

    def test_resolve_requirement_with_file_recursion_beyond_max_depth(self):
        content = "-r requirements.txt\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):
            with self.assertRaises(RuntimeError):
                Flake8Checker.resolve_requirement("-r requirements.txt", 1),

    def test_resolve_requirement_with_file_recursion(self):
        content = "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                mock.mock_open(read_data=content).return_value,
                mock.mock_open(read_data=inner_content).return_value,
            )

            self.assertEqual(
                Flake8Checker.resolve_requirement("-r requirements.txt", 2),
                ["foo >= 1.0.0", "baz", "qux", "bar <= 1.0.0"],
            )

    def test_init_with_no_requirements(self):
        with mock.patch("os.path.exists", return_value=False) as exists:
            memoize.mem = {}
            checker = Flake8Checker(None, None)
            requirements = checker.get_requirements()
            self.assertEqual(requirements, ())
            exists.assert_called_once_with("requirements.txt")

    def test_init_with_simple_requirements(self):
        content = "foo >= 1.0.0\nbar <= 1.0.0\n"
        setup_content = ""

        with mock.patch("os.path.exists", return_value=True):
            with mock.patch(builtins_open, mock.mock_open()) as m:
                m.side_effect = (
                    mock.mock_open(read_data=content).return_value,
                    mock.mock_open(read_data=setup_content).return_value,
                )

                memoize.mem = {}
                checker = Flake8Checker(None, None)
                requirements = checker.get_requirements()

                self.assertEqual(
                    sorted(requirements, key=lambda x: x.project_name),
                    sorted(parse_requirements([
                        "foo >= 1.0.0",
                        "bar <= 1.0.0",
                    ]), key=lambda x: x.project_name),
                )

    def test_init_with_recursive_requirements_beyond_max_depth(self):
        content = "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"
        setup_content = ""

        with mock.patch("os.path.exists", return_value=True):
            with mock.patch(builtins_open, mock.mock_open()) as m:
                m.side_effect = (
                    mock.mock_open(read_data=content).return_value,
                    mock.mock_open(read_data=inner_content).return_value,
                    mock.mock_open(read_data=setup_content).return_value,
                )

                with self.assertRaises(RuntimeError):
                    try:
                        memoize.mem = {}
                        Flake8Checker.requirements_max_depth = 0
                        Flake8Checker(None, None)
                    finally:
                        Flake8Checker.requirements_max_depth = 1

    def test_init_with_recursive_requirements(self):
        content = "foo >= 1.0.0\n-r inner.txt\nbar <= 1.0.0\n"
        inner_content = "# inner\nbaz\n\nqux\n"
        setup_content = ""

        with mock.patch("os.path.exists", return_value=True):
            with mock.patch(builtins_open, mock.mock_open()) as m:
                m.side_effect = (
                    mock.mock_open(read_data=content).return_value,
                    mock.mock_open(read_data=inner_content).return_value,
                    mock.mock_open(read_data=setup_content).return_value,
                )

                memoize.mem = {}
                checker = Flake8Checker(None, None)
                requirements = checker.get_requirements()

                self.assertEqual(
                    sorted(requirements, key=lambda x: x.project_name),
                    sorted(parse_requirements([
                        "foo >= 1.0.0",
                        "baz",
                        "qux",
                        "bar <= 1.0.0",
                    ]), key=lambda x: x.project_name),
                )
