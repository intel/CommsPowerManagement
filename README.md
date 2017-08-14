# Introduction

Recent generations of the Intel® Xeon® family processors allow configurations
where Turbo Boost can be enabled on a per-core basis.

`turbo-cores.sh` is a bash script that allows you to enable and disable
specific cores using an easy-to-use menu.

# Prerequisites

It is required to disable the intel_pstate kernel driver, as this may disrupt
with the configuration enabled buy the script. To achieve this, we need to
add `intel_pstate=disabled` to the kernel boot parameters. Typically this iss
done by editing `/boot/grub2/grub.cfg`, and adding to the relevant kernel
parameter line (it may be slightly different on different operating systems).

```bash
linux /boot/vmlinuz-4.10.11-100.fc24.x86_64 root=... quiet intel_pstate=disable
```

The script also depends on some utilities, so please ensure the following
packages are installed:

```bash
sudo dnf install -y msr-tools kernel-tools util-linux
```
or
```bash
sudo apt-get install -y msr-tools kernel-tools util-linux
```

# The Script

The script is compatible with Intel® Xeon® CPU E5 v3, Intel® Xeon® CPU E5 v4,
and Intel® Xeon® Processor Scalable Family.

When executing the script, the user is presented with the following menu:

```bash
# ./turbo-cores.sh

Intel® Xeon® CPU E5 v4 detected (BDX)

******************************************
1) Load msr tools driver
2) Check Turbo Boost Configuration
3) Enable package-wide Turbo Boost
4) Disable package-wide Turbo Boost
5) Enable per-core Turbo Boost
6) Disable per-core Turbo Boost

q) Quit

Please enter your choice:
```

The key options in this script are those to enable package-wide turbo, and
enable per-core turbo on specific cores. The current configuration can best
viewed using option 2.


```bash
Please enter your choice: 2

-----------------------------------
Package TURBO enabled for socket 0
-----------------------------------
-----------------------------------
Package TURBO enabled for socket 1
-----------------------------------
core 00: turbo disabled
core 01: turbo disabled
core 02: turbo disabled
core 03: turbo disabled
core 04: turbo disabled
core 05: turbo disabled
core 06: turbo disabled
..
..
```

Option 5 allows per-core turbo to be enabled by entering a space-separated
list of core numbers:

```bash
Please enter your choice: 5

Please enter a list of cores to enable:
E.g. '3 5 7' or 'all': 4 5 6
Enabling Turbo on core(s) 4 5 6
core 00: turbo disabled
core 01: turbo disabled
core 02: turbo disabled
core 03: turbo disabled
core 04: turbo enabled
core 05: turbo enabled
core 06: turbo enabled
core 07: turbo disabled
core 08: turbo disabled
..
..
```

To confirm the settings, the `turbostat` tool can be used to check the
frequencies of the cores while the application is running. Here’s an example
of an application using 8 cores, and the three cores that were configured
with Turbo enabled can be seen running at ~2900MHz, where the remaining cores
are running at ~2200MHz:

```bash
CPU     Avg_MHz Busy%   Bzy_MHz TSC_MHz
-       446     18.22   2454    2195
0       20      1.70    1200    2195
1       0       0.03    1200    2195
2       0       0.02    1200    2195
3       2195    100.00  2200    2195
4       2870    99.44   2893    2195
5       2870    99.45   2893    2195
6       2870    99.45   2893    2195
7       2195    100.00  2200    2195
8       2195    100.00  2200    2195
9       2195    100.00  2200    2195
10      2195    100.00  2200    2195
11      0       0.01    1200    2195
```
