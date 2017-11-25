import ast
import sys
from itertools import chain

from pkg_resources import parse_requirements

from .modules import KNOWN_3RD_PARTIES
from .modules import STDLIB_PY2
from .modules import STDLIB_PY3

# NOTE: Changing this number will alter package version as well.
__version__ = "1.0.0"
__license__ = "MIT"

ERRORS = {
    'I900': "I900 '{pkg}' not listed as a requirement",
    'I901': "I901 '{pkg}' required but not used",
}

STDLIB = set()
if sys.version_info[0] == 2:
    STDLIB.update(STDLIB_PY2)
if sys.version_info[0] == 3:
    STDLIB.update(STDLIB_PY3)


class ImportVisitor(ast.NodeVisitor):
    """Import statement visitor."""

    def __init__(self, tree):
        """Initialize import statement visitor."""
        self.imports = []
        self.visit(tree)

    def visit_Import(self, node):
        self.imports.append((node, node.names[0].name))

    def visit_ImportFrom(self, node):
        if node.level != 0:
            # Omit relative imports (local modules).
            return
        self.imports.append((node, node.module))


class SetupVisitor(ast.NodeVisitor):
    """Package setup visitor.

    Warning:
    This visitor class executes given Abstract Syntax Tree!

    """

    # Set of keywords used by the setup() function.
    attributes = {
        'required': {
            'name',
            'version',
        },
        'one-of': {
            'ext_modules',
            'packages',
            'py_modules',
        },
        'optional': {
            'author',
            'author_email',
            'classifiers',
            'cmdclass',
            'configuration',
            'convert_2to3_doctests',
            'dependency_links',
            'description',
            'download_url',
            'eager_resources',
            'entry_points',
            'exclude_package_data',
            'extras_require',
            'features',
            'include_package_data',
            'install_requires',
            'keywords',
            'license',
            'long_description',
            'maintainer',
            'maintainer_email',
            'message_extractors',
            'namespace_packages',
            'package_data',
            'package_dir',
            'platforms',
            'python_requires',
            'scripts',
            'setup_requires',
            'test_loader',
            'test_suite',
            'tests_require',
            'url',
            'use_2to3',
            'use_2to3_fixers',
            'zip_safe',
        },
    }

    def __init__(self, tree):
        """Initialize package setup visitor."""
        self.redirected = False
        self.keywords = {}

        # Find setup() call and redirect it.
        self.visit(tree)

        if not self.redirected:
            return

        def setup(**kw):
            self.keywords = kw

        eval(
            compile(ast.fix_missing_locations(tree), "<str>", mode='exec'),
            {'__file__': "setup.py", '__f8r_setup': setup},
        )

    def get_requirements(self, install=True, extras=True):
        """Get package requirements."""
        requires = []
        if install:
            requires.extend(parse_requirements(
                self.keywords.get('install_requires', ()),
            ))
        if extras:
            for r in self.keywords.get('extras_require', {}).values():
                requires.extend(parse_requirements(r))
        return requires

    def visit_Call(self, node):
        """Call visitor - used for finding setup() call."""
        self.generic_visit(node)

        # Setuptools setup() is a keywords only function.
        if not (not node.args and (node.keywords or node.kwargs)):
            return

        keywords = {x.arg for x in node.keywords}
        if node.kwargs:
            keywords.update(x.s for x in node.kwargs.keys)

        if not keywords.issuperset(self.attributes['required']):
            return
        if not keywords.intersection(self.attributes['one-of']):
            return
        if not keywords.issubset(chain(*self.attributes.values())):
            return

        # Redirect call to our setup() tap function.
        node.func = ast.Name(id='__f8r_setup', ctx=node.func.ctx)
        self.redirected = True


class Flake8Checker(object):
    """Package requirements checker."""

    name = "flake8-requires"
    version = __version__

    def __init__(self, tree, filename, lines=None):
        """Initialize requirements checker."""
        self.setup = self.get_setup()
        self.tree = tree

    def get_setup(self):
        """Get package setup."""
        with open("setup.py") as f:
            return SetupVisitor(ast.parse(f.read()))

    def run(self):
        """Run checker."""

        def modcmp(mod1=(), mod2=()):
            """Compare import modules."""
            return all(a == b for a, b in zip(mod1, mod2))

        requirements = set()

        # Get module names based on requirements.
        for requirement in self.setup.get_requirements():
            project = requirement.project_name.lower()
            modules = [project.replace("-", "_")]
            if project in KNOWN_3RD_PARTIES:
                modules = KNOWN_3RD_PARTIES[project]
            requirements.update(tuple(x.split(".")) for x in modules)

        for node, module in ImportVisitor(self.tree).imports:
            _module = module.split(".")
            if any([_module[0] == x for x in STDLIB]):
                continue
            if any([modcmp(_module, x) for x in requirements]):
                continue
            yield (
                node.lineno,
                node.col_offset,
                ERRORS['I900'].format(pkg=module),
                Flake8Checker,
            )
