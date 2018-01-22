Package requirements checker
============================

This module provides a plug-in for `flake8 <http://flake8.pycqa.org>`_, which checks/validates
package import requirements. It reports missing and/or not used project direct dependencies.

This plug-in adds new flake8 warnings:

- ``I900``: Package is not listed as a requirement.
- ``I901``: Package is require but not used.

Important notice
----------------

In order to collect project's dependencies, this checker evaluates Python code from the
``setup.py`` file stored in the project's root directory. Code evaluation is done with the
`eval() <https://docs.python.org/3/library/functions.html#eval>`_ function. As a fall-back
method, this checker also tries to load dependencies from the ``requirements.txt`` file.

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
