import unittest
from unittest import mock
from unittest.mock import mock_open
from unittest.mock import patch

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import ModuleSet
from flake8_requirements.checker import memoize
from flake8_requirements.checker import parse_requirements


class Flake8Options:
    known_modules = ""
    requirements_file = None
    requirements_max_depth = 1
    scan_host_site_packages = False


class Pep621TestCase(unittest.TestCase):

    content = b"""
    [project]
    name="test"
    dependencies=["tools==1.0"]

    [project.optional-dependencies]
    dev = ["dev-tools==1.0"]
    """

    def setUp(self):
        memoize.mem = {}

    def tearDown(self):
        Flake8Checker.root_dir = ""

    def test_pyproject_custom_mapping_parser(self):
        class Options(Flake8Options):
            known_modules = {"mylib": ["mylib.drm", "mylib.ex"]}
        Flake8Checker.parse_options(Options)
        self.assertEqual(
            Flake8Checker.known_modules,
            {"mylib": ["mylib.drm", "mylib.ex"]},
        )

    def test_get_pyproject_toml_pep621(self):
        with mock.patch('builtins.open', mock_open(read_data=self.content)):
            pep621 = Flake8Checker.get_pyproject_toml_pep621()
            expected = {
                "name": "test",
                "dependencies": ["tools==1.0"],
                "optional-dependencies": {
                    "dev": ["dev-tools==1.0"]
                },
            }
            self.assertDictEqual(pep621, expected)

    def test_get_pyproject_toml_invalid(self):
        content = self.content + b"invalid"
        with mock.patch('builtins.open', mock_open(read_data=content)):
            self.assertDictEqual(Flake8Checker.get_pyproject_toml_pep621(), {})

    def test_1st_party(self):
        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock_open(read_data=self.content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_1st_party()
            self.assertEqual(mods, ModuleSet({"test": {}}))

    def test_3rd_party(self):
        with mock.patch('builtins.open', mock_open()) as m:
            m.side_effect = (
                IOError("No such file or directory: 'setup.py'"),
                IOError("No such file or directory: 'setup.cfg'"),
                mock_open(read_data=self.content).return_value,
            )

            checker = Flake8Checker(None, None)
            mods = checker.get_mods_3rd_party(False)
            self.assertEqual(mods, ModuleSet({"tools": {}, "dev_tools": {}}))

    def test_dynamic_requirements(self):
        requirements_content = "package1\npackage2>=2.0"
        data = {
            "project": {"dynamic": ["dependencies"]},
            "tool": {
                "setuptools": {
                    "dynamic": {"dependencies": {"file": ["requirements.txt"]}}
                }
            },
        }
        with patch(
            'flake8_requirements.checker.Flake8Checker.get_pyproject_toml',
            return_value=data,
        ):
            with patch(
                'builtins.open', mock_open(read_data=requirements_content)
            ):
                result = Flake8Checker.get_setuptools_dynamic_requirements()
                expected_results = ['package1', 'package2>=2.0']
                parsed_results = [str(req) for req in result]
                self.assertEqual(parsed_results, expected_results)

    def test_dynamic_optional_dependencies(self):
        data = {
            "project": {"dynamic": ["dependencies", "optional-dependencies"]},
            "tool": {
                "setuptools": {
                    "dynamic": {
                        "dependencies": {"file": ["requirements.txt"]},
                        "optional-dependencies": {
                            "test": {"file": ["optional-requirements.txt"]}
                        },
                    }
                }
            },
        }
        requirements_content = """
        package1
        package2>=2.0
        """
        optional_requirements_content = "package3[extra] >= 3.0"
        with mock.patch(
            'flake8_requirements.checker.Flake8Checker.get_pyproject_toml',
            return_value=data,
        ):
            with mock.patch('builtins.open', mock.mock_open()) as mocked_file:
                mocked_file.side_effect = [
                    mock.mock_open(
                        read_data=requirements_content
                    ).return_value,
                    mock.mock_open(
                        read_data=optional_requirements_content
                    ).return_value,
                ]
                result = Flake8Checker.get_setuptools_dynamic_requirements()
                expected = list(parse_requirements(
                    requirements_content.splitlines()))
                expected += list(parse_requirements(
                    optional_requirements_content.splitlines()))

                self.assertEqual(len(result), len(expected))
                for i in range(len(result)):
                    self.assertEqual(result[i], expected[i])

    def test_missing_requirements_file(self):
        data = {
            "project": {"dynamic": ["dependencies"]},
            "tool": {
                "setuptools": {
                    "dynamic": {
                        "dependencies": {
                            "file": ["nonexistent-requirements.txt"]
                        }
                    }
                }
            },
        }
        with mock.patch(
            'flake8_requirements.checker.Flake8Checker.get_pyproject_toml',
            return_value=data,
        ):
            result = Flake8Checker.get_setuptools_dynamic_requirements()
            self.assertEqual(result, [])
