import ast
import os
import unittest
from unittest import mock
from unittest.mock import mock_open

from flake8_requirements.checker import Flake8Checker
from flake8_requirements.checker import SetupVisitor
from flake8_requirements.checker import parse_requirements


class SetupTestCase(unittest.TestCase):

    def test_detect_setup(self):
        code = "setup({})".format(",".join((
            "name='A'",
            "version='1'",
            "author='A'",
            "packages=['']",
            "url='URL'",
        )))
        setup = SetupVisitor(ast.parse(code), "")
        self.assertEqual(setup.redirected, True)
        self.assertDictEqual(setup.keywords, {
            'name': 'A',
            'version': '1',
            'packages': [''],
            'author': 'A',
            'url': 'URL',
        })

        code = "setup({})".format(",".join(
            "{}='{}'".format(x, x)
            for x in SetupVisitor.attributes
        ))
        setup = SetupVisitor(ast.parse(code), "")
        self.assertEqual(setup.redirected, True)
        self.assertDictEqual(setup.keywords, {
            x: x for x in SetupVisitor.attributes
        })

        code = "setup({})".format(",".join((
            "name='A'",
            "version='1'",
            "package='ABC'",
            "processing=True",
            "verbose=True",
        )))
        setup = SetupVisitor(ast.parse(code), "")
        self.assertEqual(setup.redirected, False)

    def test_detect_setup_wrong_num_of_args(self):
        setup = SetupVisitor(ast.parse("setup(name='A')"), "")
        self.assertEqual(setup.redirected, False)

    def test_detect_setup_wrong_function(self):
        setup = SetupVisitor(ast.parse("setup(1, name='A')"), "")
        self.assertEqual(setup.redirected, False)

    def test_detect_setup_oops(self):
        setup = SetupVisitor(ast.parse("\n".join((
            "from .myModule import setup",
            "setup({})".format(",".join((
                "name='A'",
                "version='1'",
                "author='A'",
                "packages=['']",
                "url='URL'",
            ))),
        ))), "")
        self.assertEqual(setup.redirected, False)

    def test_get_requirements(self):
        setup = SetupVisitor(ast.parse("setup(**{})".format(str({
            'name': 'A',
            'version': '1',
            'packages': [''],
            'install_requires': ["ABC > 1.0.0", "bar.cat > 2, < 3"],
            'extras_require': {
                'extra': ["extra < 10"],
            },
        }))), "")
        self.assertEqual(setup.redirected, True)
        self.assertEqual(
            sorted(setup.get_requirements(), key=lambda x: x.name),
            sorted(parse_requirements([
                "ABC > 1.0.0",
                "bar.cat > 2, < 3",
                "extra < 10",
            ]), key=lambda x: x.name),
        )

    def test_get_setup_cfg_requirements(self):
        curdir = os.path.abspath(os.path.dirname(__file__))
        with open(os.path.join(curdir, "test_setup.cfg")) as f:
            content = f.read()
        with mock.patch('builtins.open', mock_open(read_data=content)):
            checker = Flake8Checker(None, None)
            self.assertEqual(
                checker.get_setup_cfg_requirements(False),
                list(parse_requirements([
                    "requests",
                    "importlib; python_version == \"2.6\"",
                    "pytest",
                    "ReportLab>=1.2",
                    "docutils>=0.3",
                ])),
            )
