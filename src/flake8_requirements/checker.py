import ast
import os
import re
import sys
from collections import namedtuple
from functools import wraps
from logging import getLogger

import flake8
from pkg_resources import parse_requirements

from .modules import KNOWN_3RD_PARTIES
from .modules import STDLIB_PY2
from .modules import STDLIB_PY3

# NOTE: Changing this number will alter package version as well.
__version__ = "1.2.0"
__license__ = "MIT"

LOG = getLogger('flake8.plugin.requirements')

ERRORS = {
    'I900': "I900 '{pkg}' not listed as a requirement",
    'I901': "I901 '{pkg}' required but not used",
}

STDLIB = set()
if sys.version_info[0] == 2:
    STDLIB.update(STDLIB_PY2)
if sys.version_info[0] == 3:
    STDLIB.update(STDLIB_PY3)


def memoize(f):
    """Cache value returned by the function."""
    @wraps(f)
    def w(*args, **kw):
        memoize.mem[f] = v = f(*args, **kw)
        return v
    return w


# Initialize cache memory block.
memoize.mem = {}


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
        # Attributes present in almost every setup(), however
        # due to very generic name the score is not very high.
        'name': 0.7,
        'version': 0.7,
        # One of these attributes is present in every setup(),
        # scoring depends on the name uniqueness.
        'ext_modules': 1.0,
        'packages': 0.8,
        'py_modules': 1.0,
        # Mostly used (hence listed here) optional attributes.
        'author': 0.5,
        'author_email': 0.6,
        'classifiers': 0.6,
        'cmdclass': 0.6,
        'convert_2to3_doctests': 1.0,
        'dependency_links': 0.7,
        'description': 0.5,
        'download_url': 0.5,
        'eager_resources': 0.7,
        'entry_points': 0.7,
        'exclude_package_data': 0.9,
        'extras_require': 0.7,
        'include_package_data': 0.9,
        'install_requires': 0.7,
        'keywords': 0.5,
        'license': 0.5,
        'long_description': 0.5,
        'maintainer': 0.5,
        'maintainer_email': 0.6,
        'namespace_packages': 0.6,
        'package_data': 0.6,
        'package_dir': 0.6,
        'platforms': 0.5,
        'python_requires': 0.7,
        'scripts': 0.5,
        'setup_requires': 0.7,
        'test_loader': 0.6,
        'test_suite': 0.6,
        'tests_require': 0.7,
        'url': 0.5,
        'use_2to3': 0.9,
        'use_2to3_fixers': 1.0,
        'zip_safe': 0.6,
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
            """Setup() arguments hijacking."""
            self.keywords = kw

        # XXX: If evaluated script (setup.py) depends on local modules we
        #      have to add its root directory to the import search path.
        #      Note however, that this hack might break further imports
        #      for OUR Python instance (we're changing our own sys.path)!
        sys.path.insert(0, os.getcwd())

        try:
            tree = ast.fix_missing_locations(tree)
            eval(compile(tree, "<str>", mode='exec'), {
                '__name__': "__main__",
                '__file__': "setup.py",
                '__f8r_setup': setup,
            })
        except Exception as e:
            # XXX: Exception during setup.py evaluation might not necessary
            #      mean "fatal error". This exception might occur if e.g.
            #      we have hijacked local setup() function (due to matching
            #      heuristic for function arguments). Anyway, we shall not
            #      break flake8 execution due to out eval() usage.
            LOG.exception("Couldn't evaluate setup.py: %s", e)

        # Restore import search path.
        sys.path.pop(0)

    def get_requirements(
            self, install=True, extras=True, setup=False, tests=False):
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
        if tests:
            requires.extend(parse_requirements(
                self.keywords.get('tests_require', ()),
            ))
        return requires

    def visit_Call(self, node):
        """Call visitor - used for finding setup() call."""
        self.generic_visit(node)

        # Setup() is a keywords-only function.
        if node.args:
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

        # The bare minimum number of arguments seems to be around five, which
        # includes author, name, version, module/package and something extra.
        if len(keywords) < 5:
            return

        score = sum(
            self.attributes.get(x, 0)
            for x in keywords
        ) / len(keywords)

        if score < 0.5:
            LOG.debug(
                "Scoring for setup%r below 0.5: %.2f",
                tuple(keywords),
                score)
            return

        # Redirect call to our setup() tap function.
        node.func = ast.Name(id='__f8r_setup', ctx=node.func.ctx)
        self.redirected = True


class Flake8Checker(object):
    """Package requirements checker."""

    name = "flake8-requirements"
    version = __version__

    # User defined project->modules mapping.
    known_modules = {}

    # max depth to resolve recursive requirements
    requirements_max_depth = 1

    def __init__(self, tree, filename, lines=None):
        """Initialize requirements checker."""
        self.tree = tree
        self.filename = filename
        self.lines = lines
        self.requirements = self.get_requirements()
        self.setup = self.get_setup()

    @classmethod
    def add_options(cls, manager):
        """Register plug-in specific options."""
        kw = {}
        if flake8.__version__ >= '3.0.0':
            kw['parse_from_config'] = True
        manager.add_option(
            "--known-modules",
            action='store',
            default="",
            help=(
                "User defined mapping between a project name and a list of"
                " provided modules. For example: ``--known-modules=project:"
                "[Project],extra-project:[extras,utilities]``."
            ),
            **kw
        )
        manager.add_option(
            "--requirements-max-depth",
            type="int",
            default=1,
            help=(
                "Max depth to resolve recursive requirements. Defaults to 1 "
                "(one level of recursion allowed)."
            ),
            **kw
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
        cls.requirements_max_depth = options.requirements_max_depth

    @classmethod
    @memoize
    def get_requirements(cls):
        """Get package requirements."""
        if not os.path.exists("requirements.txt"):
            LOG.debug("No requirements.txt file")
            return ()
        return tuple(parse_requirements(cls.resolve_requirement(
            "-r requirements.txt", cls.requirements_max_depth + 1)))

    @classmethod
    def resolve_requirement(cls, requirement, max_depth=0):
        """Resolves flags like -r in an individual requirement line."""
        requirement = requirement.strip()

        if requirement.startswith("#") or not requirement:
            return []

        if requirement.startswith("-r "):
            # Error out if we need to recurse deeper than allowed.
            if max_depth <= 0:
                msg = "Cannot resolve {}: beyond max depth"
                raise RuntimeError(msg.format(requirement.strip()))

            resolved = []
            # Error out if requirements file cannot be opened.
            with open(requirement[3:].lstrip()) as f:
                for line in f.readlines():
                    resolved.extend(cls.resolve_requirement(
                        line, max_depth - 1))
            return resolved

        return [requirement]

    @classmethod
    @memoize
    def get_setup(cls):
        """Get package setup."""
        try:
            with open("setup.py") as f:
                return SetupVisitor(ast.parse(f.read()))
        except IOError as e:
            LOG.warning("Couldn't open setup file: %s", e)
            return SetupVisitor(ast.parse(""))

    @property
    def processing_setup_py(self):
        """Determine whether we are processing setup.py file."""
        try:
            return os.path.samefile(self.filename, "setup.py")
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

        requirements = self.requirements
        if self.setup.redirected:
            # Use requirements from setup if available.
            requirements = self.setup.get_requirements(
                setup=self.processing_setup_py,
                tests=True,
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
