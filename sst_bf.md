# sst_bf.py

`sst_bf.py` is a Python script that allows you to configure
Intel® Speed Select Technology - Base Frequency (Intel® SST-BF).
This allows some cores to run at a higher guaranteed base frequency than
others. The script provides several options for configuring the system and
to revert to a state that does not use Intel® SST-BF as necessary.

# Prerequesites

* An SST-BF enabled CPU
* SST-BF enabled in the BIOS
* Linux Kernel 4.20 or later
* Kernel using intel_pstate driver

The script is compatible with any CPU with the Intel® SST-BF feature, for
example: Intel® Xeon® Gold 6252N Processor, Intel® Xeon® Gold 6230N
Processor or Intel® Xeon® Gold 5218N Processor.

# The Script

There are two modes of operation of the script. One method is via command line
paramters, allowing the script to be called from other scripts, binaries, etc.
The other method is via interactive menu, which is invoked when no command
line parameters are given.

When executing the script with the '-h' command line parameter, the user is
presented with help text (frequencies may vary for different CPUs):

```bash
# sst_bf.py -h
usage: sst_bf.py [-h] [-s] [-m] [-r] [-t] [-a] [-b] [-i] [-l] [-v]

Configure SST-BF frequencies

optional arguments:
  -h, --help  show this help message and exit
  -s          Set SST-BF config. Set high priority cores to 2700 minimum and
              2700 maximum, and set normal priority cores to 2100 minimum and
              2100 maximum.
  -m          Set P1 on all cores. Set all cores to 2300 minimum and 2300
              maximum.
  -r          Revert cores to minimum/Turbo. Set all cores to 800 minimum and
              3900 maximum.
  -t          Revert cores to minimum/P1. Set all cores to 800 minimum and
              2300 maximum.
  -a          Mixed config A. Set high priority cores to 2700 minimum and 3900
              maximum, and set normal priority cores to 800 minimum and 2100
              maximum.
  -b          Mixed config B. Set high priority cores to 2700 minimum and 2700
              maximum, and set normal priority cores to 800 minimum and 3900
              maximum.
  -i          Show current SST-BF frequency information
  -l          List High Priority cores
  -v          Show script version
#
```

When executing the script without any command line parameters, the user is
presented with the following menu (frequencies may vary for different CPUs):

```bash
----------------------------------------------------------
[s] Set SST-BF config (set min/max to 2700/2700 and 2100/2100)
[m] Set P1 on all cores (set min/max to 2300/2300)
[r] Revert cores to min/Turbo (set min/max to 800/3900)
[t] Revert cores to min/P1 (set min/max to 800/2300)
[a] Mixed config A (set min/max to 2700/3900 and 800/2100)
[b] Mixed config B (set min/max to 2700/2700 and 800/3900)
[i] Show current SST-BF frequency information
[l] List High Priority cores
[v] Show script version
[h] Print additional help on menu options

[q] Exit Script
----------------------------------------------------------
Option:
```

Options i, l and v give information about the current system configuraion,
including a list of high priority cores (including a hexadecimal coremask),
and the version of the script.


[i] Show SST-BF info
```bash
Option: i
Name = 6230N
CPUs = 40
Base = 2300
     |------sysfs-------|
Core | base   max   min |
-----|------------------|
   0 | 2100  2100  2100 |
   1 | 2700  2700  2700 |
...
...
  38 | 2100  2100  2100 |
  39 | 2100  2100  2100 |
-----|------------------|
We have 12 high priority cores according to sysfs base_frequency.

Press enter to continue ...
```

And the List option, with it's comma-separated list and hexadecimal core mask
of high priority cores:

[l] List High Priority cores
```bash
Option: l
1,6,7,8,9,16,21,26,27,28,29,30
0x7c2103c2

Press enter to continue ...
```

The remaining options set up Intel® SST-BF, or revert the system to
a non-SST-BF configuration, where all cores share the same base frequency.

[s] Set SST-BF config (set min/max to 2700/2700 and 2100/2100)
```bash
Option: s
CPU Count = 40
Name = 6230N
CPUs = 40
Base = 2300
     |------sysfs-------|
Core | base   max   min |
-----|------------------|
   0 | 2100  2100  2100 |
   1 | 2700  2700  2700 |
...
...
  38 | 2100  2100  2100 |
  39 | 2100  2100  2100 |
-----|------------------|
We have 12 high priority cores according to sysfs base_frequency.

Press enter to continue ...
```

[r] Revert cores to Turbo/min (set max/min to 3900/800)
```bash
Option: r
CPU Count = 40
Name = 6230N
CPUs = 40
Base = 2300
     |------sysfs-------|
Core | base   max   min |
-----|------------------|
   0 | 2100  3900   800 |
   1 | 2700  3900   800 |
...
...
  38 | 2100  3900   800 |
  39 | 2100  3900   800 |
-----|------------------|
We have 12 high priority cores according to sysfs base_frequency.

Press enter to continue ...
```

The two remaining options, 'Mixed config A' and 'Mixed config B' allow a
mix of standard SST-BF and non-SST-BF configuration . These configurations
may be suitable for some use-cases.

For 'Mixed Config A', the high priority cores are set to 2700 minimum and
3900 maximum, and set normal priority cores to 800 minimum and 2100
maximum.

For 'Mixed Config B', the high priority cores are set to 2700 minimum and
2700 maximum, and set normal priority cores to 800 minimum and 3900s
maximum.

# Emulating SST-BF

If a suitable BIOS or Linux kernel is not available on the platform, SST-BF
may be emulated by setting the min and max frequencies high on some of the
cores. Typically this would be 6 or 8 cores at 2.7Ghz, and the remainder of
the cores at 2.1GHz on a 20 core CPU. 

The power.py python script (available in this repository) can be used to set
up an emulated mode, with the administrator supplying the list of cores they
want as high priority. 

Turbo is enabled on the system. Hyper-threading is disabled. 

Use the commands:

```bash
# First set max and min to be as wide as possible (3.9GHz and 1.0GHz).
power.py -r 0-39 -M 3900 -m 1000

# Set all cores to low priority (min/max at 2.1GHz)
power.py -r 0-39 -g powersave -M 2100 -m 2100

# Finally, set the high priority cores (min/max at 2.7GHz). These cores are just random cores. 6 cores per SKU on 6230N
power.py -r 2,4,6,8,10,12,22,24,26,28,30,32 -g powersave -M 2700 -m 2700
```

Then using “power.py -l” we see the following:

```bash
==== ====== ====== ====== =========== ======= ======= ======= =======
              P-STATE INFO                   C-STATES DISABLED?
Core    Max    Min    Now    Governor    POLL      C1     C1E      C6
==== ====== ====== ====== =========== ======= ======= ======= =======
   0   2100   2100    800   powersave      no      no      no      no
   1   2100   2100    800   powersave      no      no      no      no
   2   2700   2700    800   powersave      no      no      no      no
...
  37   2100   2100   2100   powersave      no      no      no      no
  38   2100   2100   1977   powersave      no      no      no      no
  39   2100   2100   2101   powersave      no      no      no      no
```

