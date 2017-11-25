Package requirements checker
============================

This module provides a plug-in for [flake8](http://flake8.pycqa.org), which checks/validates
package import requirements. It reports missing and/or not used project direct dependencies.

Installation
------------

You can install, upgrade, or uninstall ``flake8-requirements`` with these commands::

  $ pip install flake8-requirements
  $ pip install --upgrade flake8-requirements
  $ pip uninstall flake8-requirements

Warnings
--------

This package adds new flake8 warnings as follows:

- ``I900``: Package is not listed as a requirement.
- ``I901``: Package is require but not used.
