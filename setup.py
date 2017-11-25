from __future__ import with_statement

import re
from os import path

from setuptools import setup


def get_abs_path(pathname):
    return path.join(path.dirname(__file__), pathname)


with open(get_abs_path("src/flake8_requirements/checker.py")) as f:
    version = re.match(r'.*__version__ = "(.*?)"', f.read(), re.S).group(1)
with open(get_abs_path("README.rst")) as f:
    long_description = f.read()

setup(
    name="flake8-requirements",
    version=version,
    author="Arkadiusz Bokowy",
    author_email="arkadiusz.bokowy@gmail.com",
    url="https://github.com/Arkq/flake8-requirements",
    description="Package requirements checker, plugin for flake8",
    long_description=long_description,
    license="MIT",
    package_dir={'': "src"},
    packages=["flake8_requirements"],
    install_requires=[
        "flake8 > 2.0.0",
        "setuptools",
    ],
    setup_requires=["pytest-runner"],
    tests_require=["pytest"],
    entry_points={
        'flake8.extension': [
            'I90 = flake8_requirements:Flake8Checker',
        ],
    },
    classifiers=[
        "Framework :: Flake8",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Quality Assurance",
    ],
)
