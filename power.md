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

/usr/local/bin/power.py -i -s <set_freq> -r <range> -g <governor>
   <no params>   use interactive menu
   -h            Show this help
   -i            Show information on available freqs, C-States, etc
   -l            List information on each core
   -M <freq>     Set core maximum frequency
   -m <freq>     Set core minimum frequency
   -s <freq>     Set core frequency (within min and max)
   -r <range>    Range of cores to affect, e.g. 1-3,5,7
   -g <governor> Set core governor (usually 'userspace')
   -e <cstate>   Enable any core C-State except C0 (POLL)
   -d <cstate>   Disable any core C-State except C0 (POLL)

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

[3] Set P-State governor for a range of cores
[4] Set Maximum P-State for a range of cores
[5] Set Minimum P-State for a range of cores
[6] Set P-State for a range of cores

[7] Enable C-State for a range of cores
[8] Disable C-State for a range of cores

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
Available P-States: [2501, 2500, 2400, 2300, 2200, 2100, 2000, 1900, 1700, 1600, 1500, 1400, 1300, 1200, 1100, 1000]
Turbo Available (use pstate '2501')
Number of CPUs: 56
Available Governors: ['conservative', 'ondemand', 'userspace', 'powersave', 'performance', 'schedutil']
Available C-States: ['POLL', 'C1-SKX', 'C1E-SKX', 'C6-SKX']

Press enter to continue ...
```
_Note: The output produced varies based on system configuration, not all governors will always be available._

[2] Display Current Settings
```bash
Option: 2

==== ====== ====== ====== ========= ======= ======= ======= =======
              P-STATE INFO                  C-STATES DISABLED?
Core    Max    Min    Now  Governor    POLL  C1-SKX C1E-SKX  C6-SKX
==== ====== ====== ====== ========= ======= ======= ======= =======
   0   2500   1000   1000  ondemand      no     YES     YES     YES
   1   2500   1000   1000  ondemand      no     YES     YES     YES
   2   2500   1000   1000  ondemand      no     YES     YES     YES
   3   2500   1000   1000  ondemand      no     YES     YES     YES
   4   2500   1000   1000  ondemand      no     YES     YES     YES
   5   2500   1000   1000  ondemand      no     YES     YES     YES
   6   2500   1000   1000  ondemand      no     YES     YES     YES
   7   2500   1000   1000  ondemand      no     YES     YES     YES
   8   2500   1000   1000  ondemand      no     YES     YES     YES
   9   2500   1000   1000  ondemand      no     YES     YES     YES
  10   2500   1000   1000  ondemand      no     YES     YES     YES
  11   2500   1000   1000  ondemand      no     YES     YES     YES
  12   2500   1000   1000  ondemand      no     YES     YES     YES
  13   2500   1000   1000  ondemand      no     YES     YES     YES
  14   2500   1000   1000  ondemand      no     YES     YES     YES
  15   2500   1000   1000  ondemand      no     YES     YES     YES
  16   2500   1000   1000  ondemand      no     YES     YES     YES
  17   2500   1000   1000  ondemand      no     YES     YES     YES
  18   2500   1000   1000  ondemand      no     YES     YES     YES
  19   2500   1000   1000  ondemand      no     YES     YES     YES
  20   2500   1000   1000  ondemand      no     YES     YES     YES
  21   2500   1000   1000  ondemand      no     YES     YES     YES
  22   2500   1000   1000  ondemand      no     YES     YES     YES
```

The remaining options allow settings of P-States (core frequency) and
C-States (core sleep states)

# Working with P-States

The P-State settings allow per-core settings of the P-State governor, maximum
frequency, minimum frequency, and the set frequency. Typically this involves
the user selecting an option from a list of available values, followed by the
user entering a range of cores  to which to apply the setting.

```bash
Option: 3
 [1] conservative
 [2] ondemand
 [3] userspace
 [4] powersave
 [5] performance
 [6] schedutil
Select Governor: 3
Input Range of Cores: 5-10,14,20
Working with cores: [5, 6, 7, 8, 9, 10, 14, 20]
Writing 'userspace' to /sys/devices/system/cpu/cpu5/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu6/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu7/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu8/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu9/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu10/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu14/cpufreq/scaling_governor
Writing 'userspace' to /sys/devices/system/cpu/cpu20/cpufreq/scaling_governor

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
Option: 7
 [1] C1-SKX
 [2] C1E-SKX
 [3] C6-SKX
 [a] All
Select C-State: a
Input Range of Cores: 0,2
Working with cores: [0, 2]
Writing '0' to /sys/devices/system/cpu/cpu0/cpuidle/state1/disable
Writing '0' to /sys/devices/system/cpu/cpu0/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu0/cpuidle/state3/disable
Writing '0' to /sys/devices/system/cpu/cpu2/cpuidle/state1/disable
Writing '0' to /sys/devices/system/cpu/cpu2/cpuidle/state2/disable
Writing '0' to /sys/devices/system/cpu/cpu2/cpuidle/state3/disable

Press enter to continue ...
```

Note that when changing C-State settings, there is an option to select all,
allowing the convenient enable/disable of all non-POLL C-States in one step.

Please see the help text provided by the script for examples of using the
command line parameters.
