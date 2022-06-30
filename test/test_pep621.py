import unittest

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import ModuleSet
from flake8_requirements.checker import memoize

try:
    from unittest import mock
    builtins_open = 'builtins.open'
except ImportError:
    import mock
    builtins_open = '__builtin__.open'


class Pep621TestCase(unittest.TestCase):

    content = """
    [project]
    name="test"
    dependencies=["tools==1.0"]

    [project.optional-dependencies]
    dev = ["dev-tools==1.0"]
    """

    def setUp(self):
        memoize.mem = {}

    def test_get_pyproject_toml_pep621(self):
        with mock.patch(builtins_open, mock.mock_open(read_data=self.content)):
            pep621 = Flake8Checker.get_pyproject_toml_pep621()
            expected = {
                "name": "test",
                "dependencies": ["tools==1.0"],
                "optional-dependencies": {
                    "dev": ["dev-tools==1.0"]
                },
            }
            self.assertDictEqual(pep621, expected)

    def test_1st_party(self):
        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock.mock_open(read_data=self.content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_1st_party()
            self.assertEqual(mods, ModuleSet({"test": {}}))

    def test_3rd_party(self):
        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock.mock_open(read_data=self.content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_3rd_party()
            self.assertEqual(mods, ModuleSet({"tools": {}, "dev_tools": {}}))
