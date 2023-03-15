# power.py

`power.py` is a Python script that allows you to configure
specific cores using command line parameters or an easy-to-use menu.
It allows adjustment of P-States and C-States through the 
Linux kernel /proc file system interface. 

# Additional Setup Notes

This script works with both acpi-cpufreq and intel_pstate drivers, although
functionality may be slightly different between them. If you wish to
disable the intel_pstate kernel driver, we need to
add `intel_pstate=disable` to the kernel boot parameters. Typically this is
done by editing `/boot/grub2/grub.cfg` or `/etc/default/grub`, and adding
to the relevant kernel parameter line (it may be slightly different on
different operating systems).

```bash
GRUB_CMDLINE_LINUX_DEFAULT="net.ifnames=0 intel_pstate=disable ..."
```

After making updates, a new grub file needs to be generated and a reboot
is required. For example, on Ubuntu:
```bash
update-grub
reboot
```

# Use case for Performance

Certain cores may need more performance than others, so in this case those
cores could have Turbo Boost enabled, while leaving the rest of the cores
at P1 (or lower). P1 is the maximum non-turbo frequency.

# Use case for Power Saving

For applications utilizing DPDK, the mechanisms for passing packets around
a system usually involves busy polling, which the intel_pstate driver sees
as 100% busy and will be unable to scale down the frequency of any of the
cores to save power. In this case it is possible to use the userspace
governor, and force the frequencey of the cores down during quiet periods
to save power.

# The Script

The script is compatible with Intel® Xeon® CPU E5 v3, Intel® Xeon® CPU E5 v4,
and Intel® Xeon® Processor Scalable Family among others.

There are two modes of operation of the script. One method is via command line
paramters, allowing the script to be called from other scripts, binaries, etc.
The other method is via interactive menu, which is invoked when no command
line parameters are given.

When executing the script with the '-h' command line parameter, the user is
presented with help text:

```bash
# power.py  -h

/usr/local/sbin/power.py -i -M <maxfreq> -m <minfreq> -s <setfreq> -r <range> -g <governor>
   <no params>   use interactive menu
   -h            Show this help
   -i            Show information on available freqs, C-States, etc
   -l            List information on each core
   -L <sec>      List information on each core repeatedly at <sec> intervals
   -M <freq>     Set core maximum frequency. Can also use "max", "min", or "base"
   -m <freq>     Set core minimum frequency. Can also use "max", "min", or "base"
   -s <freq>     Set core frequency (within min and max)
   -r <range>    Range of cores to affect, e.g. 1-3,5,7
   -g <governor> Set core governor (usually 'userspace')
   -e <cstate>   Enable core C-State
   -d <cstate>   Disable core C-State
   -U <freq>     Set uncore maximum frequency
   -u <freq>     Set uncore minimum frequency
   -T            Enable Turbo
   -t            Disable Turbo

Examples:

1. Set governor to ondemand, min 1GHz, max 2.5GHz, cores 0-10

   /usr/local/bin/power.py -g ondemand -r 0-10 -M 2500 -m 1000

2. Set governor to userspace, cores 2 and 4 only, set freq to 2GHz

   /usr/local/bin/power.py -g userspace -r 2,4 -s 2000

3. Set governor to userspace, core 1, set freq to Turbo Boost
   this assumes there's a 2501 and a 2500 freq available.

   /usr/local/bin/power.py -g userspace -r 1 -M 2501 -s 2501
```

When executing the script without any command line parameters, the user is
presented with the following menu:

```bash
# power.py
----------------------------------------------------------
[1] Display Available Settings
[2] Display Current Settings

[3] Display Available P-States
[4] Set P-State governor for a range of cores
[5] Set Maximum P-State for a range of cores
[6] Set Minimum P-State for a range of cores

[7] Display Available C-States
[8] Enable C-State for a range of cores
[9] Disable C-State for a range of cores

[10] Display Available Uncore Freqs
[11] Set Uncore Maximum for a range of cores
[12] Set Uncore Minimum for a range of cores

[13] Enable Turbo
[14] Disable Turbo

[h] Show Help Text
[q] Exit Script
----------------------------------------------------------
Option:
```

The first two menu options are informational, one giving the available
settings, and the other displaying a table with the current system settings.

[1] Display Available Settings
```bash
Option: 1

     P-State Driver: intel_pstate
 CPU Base Frequency: 1900MHz
 Available P-States: [3600, 3500, 3400, 3300, 3200, 3100, 3000, 2900, 2800, 2700, 2600, 2500, 2400, 2300, 2200, 2100, 2000, 1900, 1800, 1700, 1600, 1500, 1400, 1300, 1200, 1100, 1000, 900, 800]
    Turbo Available: Yes (any pstate above '1900'): Enabled
     Number of CPUs: 64
Available Governors: ['performance', 'powersave']
 Available C-States: ['C6', 'C1', 'C1E', 'POLL']

Press enter to continue ...
```
_Note: The output produced varies based on system configuration, not all governors will always be available._

[2] Display Current Settings
```bash
Option: 2

==== ================================ =============================== ========================
                         P-STATE INFO              C-STATES DISABLED?              UNCORE INFO
Core    Max    Min    Now    Governor    POLL      C1     C1E      C6     Max      Min     Now
==== ====== ====== ====== =========== ======= ======= ======= ======= ======= ======== =======
   0   3600    800    800   powersave      no      no      no      no    2500      800     800
   1   3600    800   1900   powersave      no      no      no      no    2500      800     800
   2   3600    800    799   powersave      no      no      no      no    2500      800     800
   3   3600    800   1900   powersave      no      no      no      no    2500      800     800
   4   3600    800   1900   powersave      no      no      no      no    2500      800     800
   5   3600    800   1900   powersave      no      no      no      no    2500      800     800
   6   3600    800   1900   powersave      no      no      no      no    2500      800     800
   7   3600    800    800   powersave      no      no      no      no    2500      800     800
   8   3600    800   1900   powersave      no      no      no      no    2500      800     800
   9   3600    800   1900   powersave      no      no      no      no    2500      800     800
  10   3600    800    800   powersave      no      no      no      no    2500      800     800
  11   3600    800   1900   powersave      no      no      no      no    2500      800     800
  12   3600    800   1900   powersave      no      no      no      no    2500      800     800
  13   3600    800   1900   powersave      no      no      no      no    2500      800     800
  14   3600    800   1900   powersave      no      no      no      no    2500      800     800
  15   3600    800   1900   powersave      no      no      no      no    2500      800     800
  16   3600    800    800   powersave      no      no      no      no    2500      800     800
  17   3600    800   1900   powersave      no      no      no      no    2500      800     800
  18   3600    800   1900   powersave      no      no      no      no    2500      800     800
  19   3600    800   1900   powersave      no      no      no      no    2500      800     800
  20   3600    800   1900   powersave      no      no      no      no    2500      800     800
  21   3600    800   1900   powersave      no      no      no      no    2500      800     800
  22   3600    800   1900   powersave      no      no      no      no    2500      800     800
```

The remaining options allow settings of P-States (core frequency) and
C-States (core sleep states)

# Working with P-States

The P-State settings allow per-core settings of the P-State governor, maximum
frequency, minimum frequency, and the set frequency. Typically this involves
the user selecting an option from a list of available values, followed by the
user entering a range of cores  to which to apply the setting.

```bash
Option: 4
 [1] performance
 [2] powersave
Select Governor: 1
Input Range of Cores: 5-10,14,20
Working with cores: [5, 6, 7, 8, 9, 10, 14, 20]
Writing 'performance' to /sys/devices/system/cpu/cpu5/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu6/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu7/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu8/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu9/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu10/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu14/cpufreq/scaling_governor
Writing 'performance' to /sys/devices/system/cpu/cpu20/cpufreq/scaling_governor

Press enter to continue ...
```

Note that the range of cores can include ranges and specific cores, seperated
by commas. For example the input "5-10,14,20" is expanded out to
cores "5, 6, 7, 8, 9, 10, 14, 20", and then the setting is applied to each of
those cores.

# Working with C-States

The C-State settings allow the enable/disable of any C-State except C0, which
is the POLL C-state. Any other C-State is a sleep state, and may be
enabled/disabled.

```bash
Option: 8
 [1] C6
 [2] C1
 [3] C1E
 [4] POLL
Select C-State: 3
Input Range of Cores: 0-4
Working with cores: [0, 1, 2, 3, 4]
Writing '0' to /sys/devices/system/cpu/cpu0/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu1/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu2/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu3/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu4/cpuidle/state2/disable

Press enter to continue ...
```

Note that when changing C-State settings, there is an option to select all,
allowing the convenient enable/disable of all non-POLL C-States in one step.

# Working with Uncore Freqs

The Uncore Freqs settings allow setting of the maximum and minimum range
of Uncore Frequencies and also displays available Uncore Frequencies.

```bash
Option: 11
 Available uncore freqs: [2500, 2400, 2300, 2200, 2100, 2000, 1900, 1800, 1700, 1600, 1500, 1400, 1300, 1200, 1100, 1000, 900, 800]
Input UncoreFreq: 2000

Press enter to continue ...
```

Please see the help text provided by the script for examples of using the
command line parameters.
