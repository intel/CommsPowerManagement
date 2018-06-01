# Introduction

Recent generations of the Intel® Xeon® family processors allow configurations
where Turbo Boost can be enabled on a per-core basis.

The scripts provided in this repository gives the user the ability to configure
the core frequencies (P-states), sleep states (C-states), and Turbo-Boost
capabilities of a core on a core by core basis. 

# Overview

The scripts provided are as follows:

[power.py](power.md) is written in python, and is the preferred method
for adjusting the frequencies and Turbo-Boost availability. This script also 
allows command-line paramaters, allowing easy integration into other scripts or
cron jobs. This script allows the adjustment of P-states, C-states and Turbo-Boost.

[turbo-cores.sh](turbo-cores.md) is written in shell scripts, and reads and 
writes Model Specific Registers (MSRs) to read configuration, and change
settings. This is aimed at users who don't have the standard Linux Kernel 
governors (ondemand, userspace, etc) available to them. This script does not
allow adjustment of C-states.

Both scripts provide a menu system for ease-of-use.

Please click on the links to see more information on each script.
