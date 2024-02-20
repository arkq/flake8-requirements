Package requirements checker
============================

This module provides a plug-in for `flake8 <http://flake8.pycqa.org>`_, which checks/validates
package import requirements. It reports missing and/or not used project direct dependencies.

This plug-in adds new flake8 warnings:

- ``I900``: Package is not listed as a requirement.
- ``I901``: Package is required but not used. (not implemented yet)

Important notice
----------------

In order to collect project's dependencies, this checker evaluates Python code from the
``setup.py`` file stored in the project's root directory. Code evaluation is done with the `eval()
<https://docs.python.org/3/library/functions.html#eval>`_ function. As a fall-back method, this
checker also tries to load dependencies, in order, from the ``setup.cfg``, the ``pyproject.toml``
file from the `PEP 621 <https://peps.python.org/pep-0621/>`_ project section, the ``pyproject.toml``
file from the `poetry <https://python-poetry.org/>`_ tool section, or from the
``requirements.txt`` text file in the project's root directory.

At this point it is very important to be aware of the consequences of the above approach. One
might inject malicious code into the ``setup.py`` file, which will be executed by this checker.
Hence, this checker shall NEVER be use to check code from an unknown source! However, in most
cases, one validates code from a known source (e.g. own code) and one will run script stored in
the ``setup.py`` file anyway. The worst case scenario is, that this checker will execute the
equivalent of the ``python setup.py``, which shall be idempotent (it's a horribly designed
``setup.py`` file if it's not).

If you have noticed some side effects during the ``flake8`` check and your ``setup.py`` file is
written in a standard way (e.g. `pypa-sampleproject
<https://github.com/pypa/sampleproject/blob/master/setup.py>`_), please fill out a bug report.

Installation
------------

You can install, upgrade, or uninstall ``flake8-requirements`` with these commands::

  $ pip install flake8-requirements
  $ pip install --upgrade flake8-requirements
  $ pip uninstall flake8-requirements

Customization
-------------

For projects with custom (private) dependencies, one can provide mapping between project name and
provided modules. Such a mapping can be set on the command line during the flake8 invocation with
the ``--known-modules`` option or alternatively in the ``[flake8]`` section of the configuration
file, e.g. ``setup.cfg``. The syntax of the custom mapping looks like follows::

  1st-project-name:[module1,module2,...],2nd-project-name:[moduleA,moduleB,...],...

If some local project lacks "name" attribute in the ``setup.py`` file (it is highly discouraged
not to provide the "name" attribute, though), one can omit the project name in the mapping and do
as follows::

  :[localmodule1,localmodule2,...],1st-local-library:[moduleA,moduleB,...],...

Real life example::

  $ cat setup.cfg
  [flake8]
  max-line-length = 100
  known-modules = my-lib:[mylib.drm,mylib.encryption]

If you use `Flake8-pyproject <https://pypi.org/project/Flake8-pyproject/>`_
(can include for installation using ``flake8-requirements[pyproject]``),
you can also configure the known modules using a nicer syntax in ``pyproject.toml``::

  $ cat pyproject.toml
  ...
  [tool.flake8]
  max-line-length = 100

  [tool.flake8.known-modules]
  my-lib = ["mylib.drm", "mylib.encryption"]

Note that if the module's name contains dots, you have to quote it in pyproject.toml (e.g.
``"my_namespace.my_lib" = [...]``).

It is also possible to scan host's site-packages directory for installed packages. This feature is
disabled by default, but user can enable it with the ``--scan-host-site-packages`` command line
option. Please note, however, that the location of the site-packages directory will be determined
by the Python version used for flake8 execution.

In order to read requirements from the text file, user shall provide the location of such a file
with the ``--requirements-file`` option. If the given location is not an absolute path, then it
has to be specified as a path relative to the project's root directory.

If you use the ``-r`` flag in your requirements text file with more than one level of recursion
(in other words, one file includes another, the included file includes yet another, and so on),
add the ``--requirements-max-depth`` option to flake8 (for example, ``--requirements-max-depth=3``
to allow three levels of recursion).

FAQ
---

| **Q:** Package is added to the requirements, but flake8 still reports "I900 '<NAME>' not listed
         as a requirement".
| **A:** It happens when the name of the package is not the same as the name of the module. In such
         a case, you have to provide the mapping between the package name and the module name. See
         the "`Customization <#customization>`_" section for more details. If the package for which
         that happens is a well-known package, please fill out a bug report or add mapping to the
         `KNOWN_3RD_PARTIES <src/flake8_requirements/modules.py#L509>`_ and submit a pull request.
