[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/intel/CommsPowerManagement/badge)](https://securityscorecards.dev/viewer/?uri=github.com/intel/CommsPowerManagement)
![CodeQL](https://github.com/intel/userspace-cni-network-plugin/actions/workflows/codeql.yml/badge.svg?branch=main)


# Introduction

Recent generations of the Intel® Xeon® family processors allow configurations
where:

1. Turbo Boost can be enabled on a per-core basis.
2. Some cores can be given a higher base frequency than others

# Overview

The scripts provided are as follows:

[power.py](power.md) allows the user
to adjust the frequencies and Turbo-Boost availability on a core-by-core basis.
This script allows the adjustment of P-states, C-states and Turbo-Boost.

[sst_bf.py](sst_bf.md) allows the user to confure the system for
Intel® Speed Select Technology - Base Frequency (Intel® SST-BF).
This allows some cores to run at a higher base frequency than
others.

[pwr.py](pwr.md) a python library which can be imported into an application,
to measure/modify core frequencies of a CPU to utilize Intel® Speed Select Technology.

Please click on the links to see more information on the scripts.
