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


class PoetryTestCase(unittest.TestCase):

    def setUp(self):
        memoize.mem = {}

    def test_get_pyproject_toml_poetry(self):
        content = "[tool.poetry]\nname='x'\n[tool.poetry.tag]\nx=0\n"
        with mock.patch(builtins_open, mock.mock_open(read_data=content)):
            poetry = Flake8Checker.get_pyproject_toml_poetry()
            self.assertDictEqual(poetry, {'name': "x", 'tag': {'x': 0}})

    def test_1st_party(self):
        content = "[tool.poetry]\nname='book'\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                mock.mock_open(read_data=content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_1st_party()
            self.assertEqual(mods, ModuleSet({"book": {}}))

    def test_3rd_party(self):
        content = "[tool.poetry.dependencies]\ntools='1.0'\n"
        content += "[tool.poetry.dev-dependencies]\ndev-tools='1.0'\n"

        with mock.patch(builtins_open, mock.mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                mock.mock_open(read_data=content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_3rd_party()
            self.assertEqual(mods, ModuleSet({"tools": {}, "dev_tools": {}}))
