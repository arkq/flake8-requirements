import ast
import unittest

from pkg_resources import parse_requirements

from flake8_requirements import checker


class SetupVisitorMock:
    keywords = {
        'name': "flake8-requires",
    }

    def get_requirements(self):
        return parse_requirements((
            "foo",
            "bar",
            "hyp-hen",
            "python-boom",
            "setuptools",
            "space.module",
        ))


class Flake8Checker(checker.Flake8Checker):
    def get_setup(self):
        return SetupVisitorMock()


def check(code):
    return list(Flake8Checker(ast.parse(code), "<unknown>").run())


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

    def test_3rd_party_multi_module(self):
        errors = check("import pkg_resources")
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
