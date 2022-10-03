#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from setuptools import setup, find_packages


setup(
    name="hpctops",
    version="0.1.0",
    description="Operator base classes for the HPC team at Canonical",
    license="Apache-2.0",
    packages=find_packages(where="lib", include=["hpctops*"]),
    package_dir={"": "lib"},
    install_requires=["ops"],
)
