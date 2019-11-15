#!/usr/bin/env python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019 Intel Corporation

from setuptools import setup

setup(
    name='pwr',
    version='0.2.0',
    description='Python library providing various tools to work with Intel processors',
    long_description=
"""The 'pwr' library is built to help take advantage of various Intel processor features such as:
 - Core and uncore frequency scaling
 - SST-BF technology
 - SST-CP technology
It is intended to be used to build various orchestration and platform power management tools.""",
    provides=["pwr"],
    url='https://github.com/intel/CommsPowerManagement',
    author='Intel Corporation',
    packages=["pwr", "pwr.internal"],
    project_urls={
        "Bug Tracker": "https://github.com/intel/CommsPowerManagement/issues",
        "Documentation": "https://github.com/intel/CommsPowerManagement/blob/master/pwr.md",
        "Source Code": "https://github.com/intel/CommsPowerManagement/blob/master/pwr/",
    },
    license='BSD-3-Clause',
    platforms=['Linux'],
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: POSIX :: Linux',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, <4',
    zip_safe=False
)
