import ast
import unittest

from flake8_requirements import checker


class SetupVisitorMock(checker.SetupVisitor):

    def __init__(self):
        self.redirected = True
        self.keywords = {
            'name': "flake8-requires",
            'install_requires': [
                "foo",
                "bar",
                "hyp-hen",
                "python-boom",
                "pillow",
                "space.module",
            ],
        }


class Flake8Checker(checker.Flake8Checker):

    @classmethod
    def get_setup(cls):
        return SetupVisitorMock()

    @property
    def processing_setup_py(self):
        return self.filename == "setup.py"


def check(code, filename="<unknown>"):
    return list(Flake8Checker(ast.parse(code), filename).run())


class Flake8CheckerTestCase(unittest.TestCase):

    def test_stdlib(self):
        errors = check("import os\nfrom unittest import TestCase")
        self.assertEqual(len(errors), 0)

    def test_stdlib_case(self):
        errors = check("from cProfile import Profile")
        self.assertEqual(len(errors), 0)
        errors = check("from cprofile import Profile")
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0][2],
            "I900 'cprofile' not listed as a requirement",
        )

    def test_1st_party(self):
        errors = check("import flake8_requires")
        self.assertEqual(len(errors), 0)

    def test_3rd_party(self):
        errors = check("import foo\nfrom bar import Bar")
        self.assertEqual(len(errors), 0)

    def test_3rd_party_python_prefix(self):
        errors = check("from boom import blast")
        self.assertEqual(len(errors), 0)

    def test_3rd_party_missing(self):
        errors = check("import os\nfrom cat import Cat")
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0][2],
            "I900 'cat' not listed as a requirement",
        )

    def test_3rd_party_hyphen(self):
        errors = check("from hyp_hen import Hyphen")
        self.assertEqual(len(errors), 0)

    def test_3rd_party_known_module(self):
        errors = check("import PIL")
        self.assertEqual(len(errors), 0)

    def test_non_top_level_import(self):
        errors = check("def function():\n import cat")
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0][2],
            "I900 'cat' not listed as a requirement",
        )

    def test_namespace(self):
        errors = check("import space.module")
        self.assertEqual(len(errors), 0)
        errors = check("from space import module")
        self.assertEqual(len(errors), 0)
        errors = check("import space")
        self.assertEqual(len(errors), 1)

    def test_relative(self):
        errors = check("from . import local")
        self.assertEqual(len(errors), 0)
        errors = check("from ..local import local")
        self.assertEqual(len(errors), 0)

    def test_custom_mapping_parser(self):
        class Flake8Options:
            known_modules = ":[pydrmcodec],mylib:[mylib.drm,mylib.ex]"
            requirements_max_depth = 0
        Flake8Checker.parse_options(Flake8Options)
        self.assertEqual(
            Flake8Checker.known_modules,
            {"": ["pydrmcodec"], "mylib": ["mylib.drm", "mylib.ex"]},
        )

    def test_custom_mapping(self):
        class Flake8Options:
            known_modules = "flake8-requires:[flake8req]"
            requirements_max_depth = 0
        Flake8Checker.parse_options(Flake8Options)
        errors = check("from flake8req import mymodule")
        self.assertEqual(len(errors), 0)

    def test_setup_py(self):
        errors = check("from setuptools import setup", "setup.py")
        self.assertEqual(len(errors), 0)
        errors = check("from setuptools import setup", "xxx.py")
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0][2],
            "I900 'setuptools' not listed as a requirement",
        )
