import ast
import unittest

from pkg_resources import parse_requirements

from flake8_requirements.checker import SetupVisitor


class Flake8CheckerTestCase(unittest.TestCase):

    def test_detect_setup(self):
        code = "setup({})".format(",".join((
            "name='A'",
            "version='1'",
            "author='A'",
            "packages=['']",
            "url='URL'",
        )))
        setup = SetupVisitor(ast.parse(code))
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
        setup = SetupVisitor(ast.parse(code))
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
        setup = SetupVisitor(ast.parse(code))
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
        }))))
        self.assertEqual(setup.redirected, True)
        self.assertEqual(
            sorted(setup.get_requirements(), key=lambda x: x.project_name),
            sorted(parse_requirements([
                "ABC > 1.0.0",
                "bar.cat > 2, < 3",
                "extra < 10",
            ]), key=lambda x: x.project_name),
        )
