import ast
import os
import re
import site
import sys
from collections import namedtuple
from configparser import ConfigParser
from functools import wraps
from logging import getLogger

from pkg_resources import parse_requirements
from pkg_resources import yield_lines

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .modules import KNOWN_3RD_PARTIES
from .modules import STDLIB_PY3

# NOTE: Changing this number will alter package version as well.
__version__ = "2.0.2"
__license__ = "MIT"

LOG = getLogger('flake8.plugin.requirements')

ERRORS = {
    'I900': "I900 '{pkg}' not listed as a requirement",
    'I901': "I901 '{pkg}' required but not used",
}

STDLIB = set()
STDLIB.update(STDLIB_PY3)


def memoize(f):
    """Cache value returned by the function."""
    @wraps(f)
    def w(*args, **kw):
        k = (f, repr(args), repr(kw))
        if k not in memoize.mem:
            memoize.mem[k] = f(*args, **kw)
        return memoize.mem[k]
    return w


# Initialize cache memory block.
memoize.mem = {}


def modsplit(module):
    """Split module into submodules."""
    return tuple(module.split("."))


def project2modules(project):
    """Convert project name into auto-detected module names."""
    # Name unification in accordance with PEP 426.
    modules = [project.lower().replace("-", "_")]
    if modules[0].startswith("python_"):
        # Remove conventional "python-" prefix.
        modules.append(modules[0][7:])
    return modules


def joinlines(lines):
    """Join line continuations and strip comments."""
    joined_line = ""
    for line in map(lambda x: x.strip(), lines):
        comment = line.startswith("#")
        if line.endswith("\\") and not comment:
            joined_line += line[:-1]
            continue
        if not comment:
            joined_line += line
        if joined_line:
            yield joined_line
            joined_line = ""
    if joined_line:
        yield joined_line


class ImportVisitor(ast.NodeVisitor):
    """Import statement visitor."""

    # Convenience structure for storing import statement.
    Import = namedtuple('Import', ('line', 'offset', 'module'))

    def __init__(self, tree):
        """Initialize import statement visitor."""
        self.imports = []
        self.visit(tree)

    def visit_Import(self, node):
        self.imports.append(ImportVisitor.Import(
            node.lineno,
            node.col_offset,
            modsplit(node.names[0].name),
        ))

    def visit_ImportFrom(self, node):
        if node.level != 0:
            # Omit relative imports (local modules).
            return
        self.imports.append(ImportVisitor.Import(
            node.lineno,
            node.col_offset,
            # Module name which covers:
            # > from namespace import module
            modsplit(node.module) + modsplit(node.names[0].name),
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

    def __init__(self, tree, cwd):
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
        sys.path.insert(0, cwd)

        try:
            tree = ast.fix_missing_locations(tree)
            eval(compile(tree, "<str>", mode='exec'), {
                '__name__': "__main__",
                '__file__': os.path.join(cwd, "setup.py"),
                '__f8r_setup': setup,
            })
        except BaseException as e:
            # XXX: Exception during setup.py evaluation might not necessary
            #      mean "fatal error". This exception might occur if e.g.
            #      we have hijacked local setup() function (due to matching
            #      heuristic for function arguments). Anyway, we shall not
            #      break flake8 execution due to our eval() usage.
            LOG.error("Couldn't evaluate setup.py: %r", e)
            self.redirected = False

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


class ModuleSet(dict):
    """Radix-tree-like structure for modules lookup."""

    requirement = None

    def add(self, module, requirement):
        for mod in module:
            self = self.setdefault(mod, ModuleSet())
        self.requirement = requirement

    def __contains__(self, module):
        for mod in module:
            self = self.get(mod)
            if self is None:
                return False
            if self.requirement is not None:
                return True
        return False


class Flake8Checker(object):
    """Package requirements checker."""

    name = "flake8-requirements"
    version = __version__

    # Build-in mapping for known 3rd party modules.
    known_3rd_parties = {
        k: v
        for k, v in KNOWN_3RD_PARTIES.items()
        for k in project2modules(k)
    }

    # Host-based mapping for 3rd party modules.
    known_host_3rd_parties = {}

    # Collect and report I901 errors
    error_I901_enabled = False

    # User defined project->modules mapping.
    known_modules = {}

    # User provided requirements file.
    requirements_file = None

    # Max depth to resolve recursive requirements.
    requirements_max_depth = 1

    # Root directory of the project.
    root_dir = ""

    def __init__(self, tree, filename, lines=None):
        """Initialize requirements checker."""
        self.tree = tree
        self.filename = filename
        self.lines = lines

    @classmethod
    def add_options(cls, manager):
        """Register plug-in specific options."""
        manager.add_option(
            "--known-modules",
            action='store',
            default="",
            parse_from_config=True,
            help=(
                "User defined mapping between a project name and a list of"
                " provided modules. For example: ``--known-modules=project:"
                "[Project],extra-project:[extras,utilities]``."
            ))
        manager.add_option(
            "--requirements-file",
            action='store',
            parse_from_config=True,
            help=(
                "Specify the name (location) of the requirements text file. "
                "Unless an absolute path is given, the file will be searched "
                "relative to the project's root directory. If this option is "
                "not specified, the plugin look up for requirements in "
                "(1) setup.py, (2) setup.cfg, (3) pyproject.toml, and (4) "
                "requirements.txt. If specified, look up will not take place."
            ))
        manager.add_option(
            "--requirements-max-depth",
            type=int,
            default=1,
            parse_from_config=True,
            help=(
                "Max depth to resolve recursive requirements. Defaults to 1 "
                "(one level of recursion allowed)."
            ))
        manager.add_option(
            "--scan-host-site-packages",
            action='store_true',
            parse_from_config=True,
            help=(
                "Scan host's site-packages directory for 3rd party projects, "
                "which provide more than one module or the name of the module"
                " is different than the project name itself."
            ))

    @classmethod
    def parse_options(cls, options):
        """Parse plug-in specific options."""
        if isinstance(options.known_modules, dict):
            # Support for nicer known-modules using flake8-pyproject.
            cls.known_modules = {
                k: v
                for k, v in options.known_modules.items()
                for k in project2modules(k)
            }
        else:
            cls.known_modules = {
                k: v.split(",")
                for k, v in [
                    x.split(":[")
                    for x in re.split(r"],?", options.known_modules)[:-1]]
                for k in project2modules(k)
            }
        cls.requirements_file = options.requirements_file
        cls.requirements_max_depth = options.requirements_max_depth
        if options.scan_host_site_packages:
            cls.known_host_3rd_parties = cls.discover_host_3rd_party_modules()
        cls.root_dir = cls.discover_project_root_dir(os.getcwd())

    @staticmethod
    def discover_host_3rd_party_modules():
        """Scan host site-packages for 3rd party modules."""
        mapping = {}
        try:
            site_packages_dirs = site.getsitepackages()
            site_packages_dirs.append(site.getusersitepackages())
        except AttributeError as e:
            LOG.error("Couldn't get site packages: %s", e)
            return mapping
        for site_dir in site_packages_dirs:
            try:
                dir_entries = os.listdir(site_dir)
            except IOError:
                continue
            for egg in (x for x in dir_entries if x.endswith(".egg-info")):
                pkg_info_path = os.path.join(site_dir, egg, "PKG-INFO")
                modules_path = os.path.join(site_dir, egg, "top_level.txt")
                if not os.path.isfile(pkg_info_path):
                    continue
                with open(pkg_info_path) as f:
                    name = next(iter(
                        line.split(":")[1].strip()
                        for line in yield_lines(f.readlines())
                        if line.lower().startswith("name:")
                    ), "")
                with open(modules_path) as f:
                    modules = list(yield_lines(f.readlines()))
                for name in project2modules(name):
                    mapping[name] = modules
        return mapping

    @staticmethod
    def discover_project_root_dir(path):
        """Discover project's root directory starting from given path."""
        root_files = ["pyproject.toml", "requirements.txt", "setup.py"]
        while path != os.path.abspath(os.sep):
            paths = [os.path.join(path, x) for x in root_files]
            if any(map(os.path.exists, paths)):
                LOG.info("Discovered root directory: %s", path)
                return path
            path = os.path.abspath(os.path.join(path, ".."))
        return ""

    @staticmethod
    def is_project_setup_py(project_root_dir, filename):
        """Determine whether given file is project's setup.py file."""
        project_setup_py = os.path.join(project_root_dir, "setup.py")
        try:
            return os.path.samefile(filename, project_setup_py)
        except OSError:
            return False

    _requirement_match_option = re.compile(
        r"(-[\w-]+)(.*)").match

    _requirement_match_extras = re.compile(
        r"(.*?)\s*(\[[^]]+\])").match

    _requirement_match_spec = re.compile(
        r"(.*?)\s+--(global-option|install-option|hash)").match

    _requirement_match_archive = re.compile(
        r"(.*)(\.(tar(\.(bz2|gz|lz|lzma|xz))?|tbz|tgz|tlz|txz|whl|zip))",
        re.IGNORECASE).match
    _requirement_match_archive_spec = re.compile(
        r"(\w+)(-[^-]+)?").match

    _requirement_match_vcs = re.compile(
        r"(git|hg|svn|bzr)\+(.*)").match
    _requirement_match_vcs_spec = re.compile(
        r".*egg=([\w\-\.]+)").match

    @classmethod
    def resolve_requirement(cls, requirement, max_depth=0, path=None):
        """Resolves flags like -r in an individual requirement line."""

        option = None
        option_match = cls._requirement_match_option(requirement)
        if option_match is not None:
            option = option_match.group(1)
            requirement = option_match.group(2).lstrip()

        editable = False
        if option in ("-e", "--editable"):
            editable = True
            # We do not care about installation mode.
            option = None

        if option in ("-r", "--requirement"):
            # Error out if we need to recurse deeper than allowed.
            if max_depth <= 0:
                msg = (
                    "Cannot resolve {}: "
                    "Beyond max depth (--requirements-max-depth={})")
                raise RuntimeError(msg.format(
                    requirement, cls.requirements_max_depth))
            resolved = []
            # Error out if requirements file cannot be opened.
            with open(os.path.join(path or cls.root_dir, requirement)) as f:
                for line in joinlines(f.readlines()):
                    resolved.extend(cls.resolve_requirement(
                        line, max_depth - 1, os.path.dirname(f.name)))
            return resolved

        if option:
            # Skip whole line if option was not processed earlier.
            return []

        # Check for a requirement given as a VCS link.
        vcs_match = cls._requirement_match_vcs(requirement)
        vcs_spec_match = cls._requirement_match_vcs_spec(
            vcs_match.group(2) if vcs_match is not None else "")
        if vcs_spec_match is not None:
            return [vcs_spec_match.group(1)]

        # Check for a requirement given as a local archive file.
        archive_ext_match = cls._requirement_match_archive(requirement)
        if archive_ext_match is not None:
            base = os.path.basename(archive_ext_match.group(1))
            archive_spec_match = cls._requirement_match_archive_spec(base)
            if archive_spec_match is not None:
                name, version = archive_spec_match.groups()
                return [
                    name if not version else
                    "{} == {}".format(name, version[1:])
                ]

        # Editable installation is made either from local path or from VCS
        # URL. In case of VCS, the URL should be already handled in the if
        # block above. Here we shall get a local project path.
        if editable:
            requirement = os.path.basename(requirement)
            if requirement.split()[0] == ".":
                requirement = ""
            # It seems that the parse_requirements() function does not like
            # ".[foo,bar]" syntax (current directory with extras).
            extras_match = cls._requirement_match_extras(requirement)
            if extras_match is not None and extras_match.group(1) == ".":
                requirement = ""

        # Extract requirement specifier (skip in-line options).
        spec_match = cls._requirement_match_spec(requirement)
        if spec_match is not None:
            requirement = spec_match.group(1)

        return [requirement.strip()]

    @classmethod
    @memoize
    def get_pyproject_toml(cls):
        """Try to load PEP 518 configuration file."""
        pyproject_config_path = os.path.join(cls.root_dir, "pyproject.toml")
        try:
            with open(pyproject_config_path, mode="rb") as f:
                return tomllib.load(f)
        except (IOError, tomllib.TOMLDecodeError) as e:
            LOG.debug("Couldn't load project setup: %s", e)
            return {}

    @classmethod
    def get_pyproject_toml_pep621(cls):
        """Try to get PEP 621 metadata."""
        cfg_pep518 = cls.get_pyproject_toml()
        return cfg_pep518.get('project', {})

    @classmethod
    def get_pyproject_toml_pep621_requirements(cls):
        """Try to get PEP 621 metadata requirements."""
        pep621 = cls.get_pyproject_toml_pep621()
        requirements = []
        requirements.extend(parse_requirements(
            pep621.get("dependencies", ())))
        for r in pep621.get("optional-dependencies", {}).values():
            requirements.extend(parse_requirements(r))
        return requirements

    @classmethod
    def get_pyproject_toml_poetry(cls):
        """Try to get poetry configuration."""
        cfg_pep518 = cls.get_pyproject_toml()
        return cfg_pep518.get('tool', {}).get('poetry', {})

    @classmethod
    def get_pyproject_toml_poetry_requirements(cls):
        """Try to get poetry configuration requirements."""
        poetry = cls.get_pyproject_toml_poetry()
        requirements = []
        requirements.extend(parse_requirements(
            poetry.get('dependencies', ())))
        requirements.extend(parse_requirements(
            poetry.get('dev-dependencies', ())))
        # Collect dependencies from groups (since poetry-1.2).
        for _, group in poetry.get('group', {}).items():
            requirements.extend(parse_requirements(
                group.get('dependencies', ())))
        return requirements

    @classmethod
    def get_requirements_txt(cls):
        """Try to load requirements from text file."""
        path = cls.requirements_file or "requirements.txt"
        if not os.path.isabs(path):
            path = os.path.join(cls.root_dir, path)
        try:
            return tuple(parse_requirements(cls.resolve_requirement(
                "-r {}".format(path), cls.requirements_max_depth + 1)))
        except IOError as e:
            LOG.error("Couldn't load requirements: %s", e)
            return ()

    @classmethod
    @memoize
    def get_setup_cfg(cls):
        """Try to load standard configuration file."""
        config = ConfigParser()
        config.read_dict({
            'metadata': {'name': ""},
            'options': {
                'install_requires': "",
                'setup_requires': "",
                'tests_require': ""},
            'options.extras_require': {},
        })
        if not config.read(os.path.join(cls.root_dir, "setup.cfg")):
            LOG.debug("Couldn't load setup configuration: setup.cfg")
        return config

    @classmethod
    def get_setup_cfg_requirements(cls, is_setup_py):
        """Try to load standard configuration file requirements."""
        config = cls.get_setup_cfg()
        requirements = []
        requirements.extend(parse_requirements(
            config.get('options', 'install_requires')))
        requirements.extend(parse_requirements(
            config.get('options', 'tests_require')))
        for _, r in config.items('options.extras_require'):
            requirements.extend(parse_requirements(r))
        setup_requires = config.get('options', 'setup_requires')
        if setup_requires and is_setup_py:
            requirements.extend(parse_requirements(setup_requires))
        return requirements

    @classmethod
    @memoize
    def get_setup_py(cls):
        """Try to load standard setup file."""
        try:
            with open(os.path.join(cls.root_dir, "setup.py")) as f:
                return SetupVisitor(ast.parse(f.read()), cls.root_dir)
        except IOError as e:
            LOG.debug("Couldn't load project setup: %s", e)
            return SetupVisitor(ast.parse(""), cls.root_dir)

    @classmethod
    def get_setup_py_requirements(cls, is_setup_py):
        """Try to load standard setup file requirements."""
        setup = cls.get_setup_py()
        if not setup.redirected:
            return []
        return setup.get_requirements(
            setup=is_setup_py,
            tests=True,
        )

    @classmethod
    @memoize
    def get_mods_1st_party(cls):
        mods_1st_party = ModuleSet()
        # Get 1st party modules (used for absolute imports).
        modules = project2modules(
            cls.get_setup_py().keywords.get('name') or
            cls.get_setup_cfg().get('metadata', 'name') or
            cls.get_pyproject_toml_pep621().get('name') or
            cls.get_pyproject_toml_poetry().get('name') or
            "")
        # Use known module mappings to correct auto-detected name. Please note
        # that we're using the first module name only, since all mappings shall
        # contain all possible auto-detected module names.
        if modules[0] in cls.known_modules:
            modules = cls.known_modules[modules[0]]
        for module in modules:
            mods_1st_party.add(modsplit(module), True)
        return mods_1st_party

    @classmethod
    @memoize
    def get_mods_3rd_party(cls, is_setup_py):
        mods_3rd_party = ModuleSet()
        # Get 3rd party module names based on requirements.
        for requirement in cls.get_mods_3rd_party_requirements(is_setup_py):
            modules = project2modules(requirement.project_name)
            # Use known module mappings to correct auto-detected module name.
            if modules[0] in cls.known_modules:
                modules = cls.known_modules[modules[0]]
            elif modules[0] in cls.known_3rd_parties:
                modules = cls.known_3rd_parties[modules[0]]
            elif modules[0] in cls.known_host_3rd_parties:
                modules = cls.known_host_3rd_parties[modules[0]]
            for module in modules:
                mods_3rd_party.add(modsplit(module), requirement)
        return mods_3rd_party

    @classmethod
    def get_mods_3rd_party_requirements(cls, is_setup_py):
        """Get list of 3rd party requirements."""
        # Use user provided requirements text file.
        if cls.requirements_file:
            return cls.get_requirements_txt()
        return (
            # Use requirements from setup if available.
            cls.get_setup_py_requirements(is_setup_py) or
            # Check setup configuration file for requirements.
            cls.get_setup_cfg_requirements(is_setup_py) or
            # Check PEP 621 metadata for requirements.
            cls.get_pyproject_toml_pep621_requirements() or
            # Check project configuration for requirements.
            cls.get_pyproject_toml_poetry_requirements() or
            # Fall-back to requirements.txt in our root directory.
            cls.get_requirements_txt()
        )

    def check_I900(self, node):
        """Run missing requirement checker."""
        if node.module[0] in STDLIB:
            return None
        is_setup_py = self.is_project_setup_py(self.root_dir, self.filename)
        if node.module in self.get_mods_3rd_party(is_setup_py):
            return None
        if node.module in self.get_mods_1st_party():
            return None
        # When processing setup.py file, forcefully add setuptools to the
        # project requirements. Setuptools might be required to build the
        # project, even though it is not listed as a requirement - this
        # package is required to run setup.py, so listing it as a setup
        # requirement would be pointless.
        if (is_setup_py and
                node.module[0] in KNOWN_3RD_PARTIES["setuptools"]):
            return None
        return ERRORS['I900'].format(pkg=node.module[0])

    def check_I901(self, node):
        """Run not-used requirement checker."""
        if node.module[0] in STDLIB:
            return None
        # TODO: Implement this check.
        return None

    def run(self):
        """Run checker."""

        checkers = []
        checkers.append(self.check_I900)
        if self.error_I901_enabled:
            checkers.append(self.check_I901)

        for node in ImportVisitor(self.tree).imports:
            for err in filter(None, map(lambda c: c(node), checkers)):
                yield node.line, node.offset, err, type(self)
