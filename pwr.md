# pwr module

This is a python module which allows an application to modify power attributes of a CPU. Manipulation can be done to the frequency of cores,
frequency of the uncore, frequency profiles can be set to achieve desired performance, as well as that capabilities of a CPU can be obtained and its frequency and power consumption stats monitored.
The library will provide a list of core and/or CPU objects whose attributes can be modified and committed to make changes on the CPU.

# Installation

The module can be installed with pip using the following command:

pip install "git+https://github.com/intel/CommsPowerManagement.git#egg=pwr&subdirectory=pwr"

## Initialization
Creation of the cpu and core object lists is done using the `get_cores()/get_cpus()` functions, which return a list of the respective objects.

```python
import pwr  # Import the module

cores = pwr.get_cores()  # Create core object list
cpus = pwr.get_cpus()  # Create CPU object list
```

## Adjusting Power Configuration
### Modifying
Each cpu and core object have attributes which replicate the capabilities and stats of the physical cores and cpus.
### CPU
* `cpu_id`                  # CPU id number
* `physical_id`             # physical CPU number
* `core_list`               # list of core objects on this CPU
* `sst_bf_enabled`          # SST-BF priority based frequency
* `sst_bf_configured`       # core configured to use base frequencies
* `turbo_enabled`           # turbo enabled flag
* `hwp_enabled`             # HWP enabled flag
* `base_freq`               # base frequency
* `all_core_turbo_freq`     # all core turbo frequency
* `highest_freq`            # highest available frequency
* `lowest_freq`             # lowest available frequency
* `uncore_hw_max`           # max available uncore frequency
* `uncore_hw_min`           # min available uncore frequency
* `power_consumption`       # power consumption since last update
* `tdp`                     # max possible power consumption
* `uncore_freq`             # current uncore frequency
* `uncore_max_freq`         # max desired uncore frequency
* `uncore_min_freq`         # min desired uncore frequency

### Core
* `core_id`                 # logical core id number
* `cpu`                     # this cores cpu object
* `thread_siblings`         # list of other logical cores residing on same physical core
* `high_priority`           # boolean value indicating whether the core will be set up to be a high priority core when SST-BF is configured.
* `base_freq`               # base frequency [2300Mhz]
* `sst_bf_base_freq`        # priority based frequency [2100Mhz/2700Mhz]
* `all_core_turbo_freq`     # all core turbo frequency [2800Mhz]
* `highest_freq`            # highest frequency available [3900Mhz]
* `lowest_freq`             # lowest active frequency [800Mhz]
* `curr_freq`               # current core frequency
* `min_freq`                # desired low frequency
* `max_freq`                # desired high frequency
* `epp`                     # energy performance preference
>Specific frequencies will depend on system and configuration.

Most of the Core/CPU object attributes are constant and cannot be changed. The only **Core** attributes that can be written to by the user, are `min_freq`, `max_freq` and `epp`.
The only **CPU** object attributes which can be written to by the user, are `uncore_max_freq` and `uncore_min_freq`.

```python
core.min_freq = core.lowest_freq  # Set the desired minimum frequency to be lowest available
core.max_freq = core.highest_freq  # Set the desired maximum frequency to the highest available

cpu.uncore_max_freq = cpu.uncore_hw_max  # Set the desired maximum uncore frequency to the highest available
cpu.uncore_min_freq = cpu.uncore_hw_min  # Set the desired minimum uncore frequency to the lowest available
```

### Committing
Modification of the power settings of a system is done by altering the core or CPU characteristics, as shown above,
then finalizing with the `commit()` function call.
```python
cores = pwr.get_cores()  # Create the cores object list

for core in cores:  # Loop through core objects in list
    core.min_freq = core.base_freq  # Set the desired minimum frequency to be the base frequency
    core.max_freq = core.highest_freq  # Set the desired maximum frequency to the highest available
    core.commit()  # Commit changes to be made on system
```


### Pre-set Profiles
When an application is modifying the desired min and max core frequencies, pre-set configurations can also be applied, these will overwrite current configurations and commit the pre-sets.
* `minimum`:            Set all cores minimum to 800Mhz and maximum to 800Mhz.
* `maximum`:            Set all cores minimum to 3900Mhz and maximum to 3900Mhz.
* `base`:               Set all cores minimum to 2300Mhz and maximum to 2300Mhz.
* `default`:            Set all cores minimum to 800Mhz and maximum to 3900Mhz.
* `no_turbo`:           Set all cores minimum to 800Mhz and maximum to 2300Mhz.
* `sst_bf_base`:        Set high priority cores minimum and maximum to 2700Mhz, normal priority cores minimum and maximum to 2100Mhz (Only available with SST-BF).
* `sst_bf_high_turbo`:  Set high priority cores minimum to 2700Mhz and maximum to 3900Mhz, normal priority cores minimum to 800Mhz and maximum to 2100Mhz(Only available with SST-BF).
* `sst_bf_low_turbo`:   Set high priority cores minimum to 2700Mhz and maximum to 2700Mhz, normal priority cores minimum to 800Mhz and maximum to 3900Mhz(Only available with SST-BF).
>Specific frequencies will depend on system and configuration.

```python
For c in cores:
    c.commit("sst_bf_base") # Configure cores with the SST-BF configuration
```
## Concept Overview
### CPU
A CPU may have multiple physical cores, which are represented by the core objects. These cores can optionally have multiple threads, which means there would be multiple logical cores on a single physical core, these are called thread siblings. Each logical core will also have its own core object. Uncore frequency is the frequency at which everything on the CPU, except the cores, runs at. This can be scaled within the limits of min and max.
### Core
Each core's frequency can scaled up or down, in the case of multiple logical cores on a physical core, both logical cores must have the same frequency for the physical core to operate at that frequency. Core frequencies can be set up to utilize the SST-BF configuration, if available. Energy performance profiles can be set up on a per core basis using a specific EPP policy, if the system configuration allows.

## Refreshing cpu stats
CPU stats can become out of date, such as `curr_freq` or `sst_bf_configured`. These can be refreshed in with `refresh_stats()`.
It is *advised* that CPU and core objects be updated with `refresh_stats()` before requesting object data.

core.refresh_stats() will update:
* `curr_freq`
* `min_freq`
* `max_freq`
* `epp`

cpu.refresh_stats() will update:
* `uncore_freq`
* `uncore_max_freq`
* `uncore_min_freq`
* `sst_bf_configured`
* `power_consumption`

```python
for c in cores:
    c.refresh_stats()  # Refresh core stats, which refreshes the sst_bf_configured value
    if not c.sst_bf_configured:  # Check are cores configured for SST-BF
        c.commit("sst_bf_base")  # Set cores to SST-BF configuration
```

## Object Referencing
Both CPU & core objects reference each other, the list of core objects can be accessed through the CPU and the CPU object of a core can be accessed through a core.

```python
for core in cores:  # Loop through cores in object list
    if core.cpu.sst_bf_enabled:  # Access CPU flag from core object
        if core.high_priority:  # Check if core has high priority base frequency
            core.min_freq = core.base_freq  # Modify minimum desired frequency
            core.max_freq = core.sst_bf_base_freq  # Modify maximum desired frequency
            core.commit()  # Commit changes to hardware
```
or
```python
for cpu in cpus:
    if cpu.core_list[0].epp == "performance":  # Access core performance profile through core list of CPU object
        cpu.uncore_max_freq = cpu.uncore_hw_max  # set desired max uncore frequency from hardware limit
        cpu.uncore_min_freq = cpu.uncore_hw_min  # set desired min uncore frequency from hardware limit
        cpu.commit() #Commit changes to hardware
```

## EPP
The EPP value (`epp` attribute in the `Core` object) uses SST-CP technology to prioritize core power consumption. Available EPP values are:
* "performance" (maximum power consumption priority)
* "balance_performance" (default power consumption priority)
* "balance_power" (lower power consumption priority)
* "power" (lowest power consumption priority)

For more information about EPP, see relevant product manuals' section describing the SST-CP technology.

## Power Consumption
The power consumption of the CPU can be read from the `power_consumption` attribute, this value can be compared against the `tdp` value to check is the current power draw close to the limit, indicated by the tdp value. The power consumption is reported as average since last time it was calculated. The first time this value is read, it can be 0. The next time it is read, it will show average power consumption (in Watts) since last read. Time period between reads must not exceed 60 seconds, otherwise the value will be reset to 0.
