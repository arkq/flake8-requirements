import unittest
from unittest import mock
from unittest.mock import mock_open

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import ModuleSet
from flake8_requirements.checker import memoize


class PoetryTestCase(unittest.TestCase):

    def setUp(self):
        memoize.mem = {}

    def test_get_pyproject_toml_poetry(self):
        content = b"[tool.poetry]\nname='x'\n[tool.poetry.tag]\nx=0\n"
        with mock.patch('builtins.open', mock_open(read_data=content)):
            poetry = Flake8Checker.get_pyproject_toml_poetry()
            self.assertDictEqual(poetry, {'name': "x", 'tag': {'x': 0}})

    def test_1st_party(self):
        content = b"[tool.poetry]\nname='book'\n"

        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock_open(read_data=content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_1st_party()
            self.assertEqual(mods, ModuleSet({"book": {}}))

    def test_3rd_party(self):
        content = b"[tool.poetry.dependencies]\ntools='1.0'\n"
        content += b"[tool.poetry.dev-dependencies]\ndev-tools='1.0'\n"

        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock_open(read_data=content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_3rd_party(False)
            self.assertEqual(mods, ModuleSet({"tools": {}, "dev_tools": {}}))

    def test_3rd_party_groups(self):
        content = b"[tool.poetry.dependencies]\ntools='1.0'\n"
        content += b"[tool.poetry.group.dev.dependencies]\ndev-tools='1.0'\n"

        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock_open(read_data=content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_3rd_party(False)
            self.assertEqual(mods, ModuleSet({"tools": {}, "dev_tools": {}}))
