import ast
import re
import sys
from collections import namedtuple
from itertools import chain
from logging import getLogger
from os import path

from pkg_resources import parse_requirements

from .modules import KNOWN_3RD_PARTIES
from .modules import STDLIB_PY2
from .modules import STDLIB_PY3

# NOTE: Changing this number will alter package version as well.
__version__ = "1.0.0"
__license__ = "MIT"

LOG = getLogger('flake8.plugin.requires')

ERRORS = {
    'I900': "I900 '{pkg}' not listed as a requirement",
    'I901': "I901 '{pkg}' required but not used",
}

STDLIB = set()
if sys.version_info[0] == 2:
    STDLIB.update(STDLIB_PY2)
if sys.version_info[0] == 3:
    STDLIB.update(STDLIB_PY3)


def project2module(project):
    """Convert project name into a module name."""
    # Name unification in accordance with PEP 426.
    project = project.lower().replace("-", "_")
    if project.startswith("python_"):
        # Remove conventional "python-" prefix.
        project = project[7:]
    return project


class ImportVisitor(ast.NodeVisitor):
    """Import statement visitor."""

    # Convenience structure for storing import statement.
    Import = namedtuple('Import', ('line', 'offset', 'mod', 'alt'))

    def __init__(self, tree):
        """Initialize import statement visitor."""
        self.imports = []
        self.visit(tree)

    def visit_Import(self, node):
        self.imports.append(ImportVisitor.Import(
            node.lineno,
            node.col_offset,
            node.names[0].name,
            node.names[0].name,
        ))

    def visit_ImportFrom(self, node):
        if node.level != 0:
            # Omit relative imports (local modules).
            return
        self.imports.append(ImportVisitor.Import(
            node.lineno,
            node.col_offset,
            node.module,
            # Alternative module name which covers:
            # > from namespace import module
            ".".join((node.module, node.names[0].name)),
        ))


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

    def get_requirements(self, install=True, extras=True, setup=False):
        """Get package requirements."""
        requires = []
        if install:
            requires.extend(parse_requirements(
                self.keywords.get('install_requires', ()),
            ))
        if extras:
            for r in self.keywords.get('extras_require', {}).values():
                requires.extend(parse_requirements(r))
        if setup:
            requires.extend(parse_requirements(
                self.keywords.get('setup_requires', ()),
            ))
        return requires

    def visit_Call(self, node):
        """Call visitor - used for finding setup() call."""
        self.generic_visit(node)

        # Setuptools setup() is a keywords only function.
        if not (not node.args and
                (node.keywords or getattr(node, 'kwargs', ()))):
            return

        keywords = set()
        for k in node.keywords:
            if k.arg is not None:
                keywords.add(k.arg)
            # Simple case for dictionary expansion for Python >= 3.5.
            if k.arg is None and isinstance(k.value, ast.Dict):
                keywords.update(x.s for x in k.value.keys)
        # Simple case for dictionary expansion for Python <= 3.4.
        if getattr(node, 'kwargs', ()) and isinstance(node.kwargs, ast.Dict):
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

    # User defined project->modules mapping.
    known_modules = {}

    def __init__(self, tree, filename, lines=None):
        """Initialize requirements checker."""
        self.tree = tree
        self.filename = filename
        self.setup = self.get_setup()

    @classmethod
    def add_options(cls, manager):
        """Register plug-in specific options."""
        manager.add_option(
            "--known-modules",
            action='store',
            parse_from_config=True,
            default="",
            help=(
                "User defined mapping between a project name and a list of"
                " provided modules. For example: ``--known-modules=project:"
                "[Project],extra-project:[extras,utilities]``."
            ),
        )

    @classmethod
    def parse_options(cls, options):
        """Parse plug-in specific options."""
        cls.known_modules = {
            project2module(k): v.split(",")
            for k, v in [
                x.split(":[")
                for x in re.split(r"],?", options.known_modules)[:-1]
            ]
        }

    @classmethod
    def get_setup(cls):
        """Get package setup."""
        if not getattr(cls, '_setup', None):
            try:
                with open("setup.py") as f:
                    cls._setup = SetupVisitor(ast.parse(f.read()))
            except IOError as e:
                LOG.warning("Couldn't open setup file: %s", e)
                cls._setup = SetupVisitor(ast.parse(""))
        return cls._setup

    @property
    def processing_setup_py(self):
        """Determine whether we are processing setup.py file."""
        try:
            return path.samefile(self.filename, "setup.py")
        except OSError:
            return False

    def run(self):
        """Run checker."""

        def split(module):
            """Split module into submodules."""
            return tuple(module.split("."))

        def modcmp(lib=(), test=()):
            """Compare import modules."""
            if len(lib) > len(test):
                return False
            return all(a == b for a, b in zip(lib, test))

        mods_1st_party = set()
        mods_3rd_party = set()

        # Get 1st party modules (used for absolute imports).
        modules = [project2module(self.setup.keywords.get('name', ""))]
        if modules[0] in self.known_modules:
            modules = self.known_modules[modules[0]]
        mods_1st_party.update(split(x) for x in modules)

        requirements = self.setup.get_requirements(
            setup=self.processing_setup_py,
        )

        # Get 3rd party module names based on requirements.
        for requirement in requirements:
            modules = [project2module(requirement.project_name)]
            if modules[0] in KNOWN_3RD_PARTIES:
                modules = KNOWN_3RD_PARTIES[modules[0]]
            if modules[0] in self.known_modules:
                modules = self.known_modules[modules[0]]
            mods_3rd_party.update(split(x) for x in modules)

        # When processing setup.py file, forcefully add setuptools to the
        # project requirements. Setuptools might be required to build the
        # project, even though it is not listed as a requirement - this
        # package is required to run setup.py, so listing it as a setup
        # requirement would be pointless.
        if self.processing_setup_py:
            mods_3rd_party.add(split("setuptools"))

        for node in ImportVisitor(self.tree).imports:
            _mod = split(node.mod)
            _alt = split(node.alt)
            if any([_mod[0] == x for x in STDLIB]):
                continue
            if any([modcmp(x, _mod) or modcmp(x, _alt)
                    for x in mods_1st_party]):
                continue
            if any([modcmp(x, _mod) or modcmp(x, _alt)
                    for x in mods_3rd_party]):
                continue
            yield (
                node.line,
                node.offset,
                ERRORS['I900'].format(pkg=node.mod),
                Flake8Checker,
            )