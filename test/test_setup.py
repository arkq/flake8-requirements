import ast
import unittest
from itertools import chain

from pkg_resources import parse_requirements

from flake8_requirements.checker import SetupVisitor


class Flake8CheckerTestCase(unittest.TestCase):

    def test_detect_setup(self):
        code = "setup(name='A', version='1', packages=[''])"
        setup = SetupVisitor(ast.parse(code))
        self.assertEqual(setup.redirected, True)
        self.assertDictEqual(setup.keywords, {
            'name': 'A',
            'version': '1',
            'packages': [''],
        })

        code = "setup({})".format(",".join(
            "{}='{}'".format(x, x)
            for x in chain(*SetupVisitor.attributes.values())
        ))
        setup = SetupVisitor(ast.parse(code))
        self.assertEqual(setup.redirected, True)
        self.assertDictEqual(setup.keywords, {
            x: x for x in chain(*SetupVisitor.attributes.values())
        })

        code = "setup(name='A', version='1')"
        setup = SetupVisitor(ast.parse(code))
        self.assertEqual(setup.redirected, False)

        code = "setup(name='A', packages=[''])"
        setup = SetupVisitor(ast.parse(code))
        self.assertEqual(setup.redirected, False)

        code = "setup('A', name='A', version='1', packages=[''])"
        setup = SetupVisitor(ast.parse(code))
        self.assertEqual(setup.redirected, False)

        code = "setup(name='A', version='1', packages=[''], xxx=False)"
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
