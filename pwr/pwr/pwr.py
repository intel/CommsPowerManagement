#!/usr/bin/env python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019 Intel Corporation
"""
Power library which allows an application to modify power attributes of cpu.
"""
import os
import re
import struct
import time
from .internal import cpuinfo

MSR_PLATFORM_INFO = 0xCE
MSR_TURBO_RATIO_LIMIT = 0x1AD
MSR_IA32_PERF_STATUS = 0x198
MSR_IA32_MISC_ENABLES = 0x1A0
MSR_IA32_PM_ENABLE = 0x770
MSR_UNCORE_RATIO_LIMIT = 0x620
MSR_UNCORE_PERF_STATUS = 0x621
MSR_RAPL_POWER_UNIT = 0x606
MSR_PKG_POWER_INFO = 0x614
MSR_PKG_ENERGY_STATUS = 0x611
BASE_PATH = "/sys/devices/system/cpu"
BASE_POWERCAP_PATH = "/sys/devices/virtual/powercap/intel-rapl"

# Core and cpu lists to be filled with corresponding objects
CORES = []
CPUS = []
SYSTEM = None
# Python 2 doesn't have monotonic
try:
    time.monotonic
except AttributeError:
    time.monotonic = time.time


class Core(object):
    """
    Core class which contains all data relevant to core,
    as well as core methods to get and set that data.
    """

    def __init__(self, id_num, cpu):
        """ Core object constructure """
        self.core_id = id_num                               # core id number
        self.online = False                                 # core availability flag
        self.cpu = cpu                                      # this cores cpu object
        self.thread_siblings = None                         # list of thread siblings
        self.high_priority = False                          # high/low priority
        self.base_freq = None                               # base freqeuncy
        self.sst_bf_base_freq = None                        # priority based frequency
        self.all_core_turbo_freq = None                     # all core turbo frequency
        self.highest_freq = None                            # single core turbo frequency
        self.lowest_freq = None                             # lowest active frequency
        self.curr_freq = None                               # current core frequency
        self.min_freq = None                                # desired low frequency
        self.max_freq = None                                # desired high frequency
        self.epp = None                                     # energy performance preference

        self._epp_available = []
        self._cpu_name = "cpu{}".format(self.core_id)
        self._core_online_filename = os.path.join(
            BASE_PATH, self._cpu_name, "online")
        self._max_desired_filename = os.path.join(BASE_PATH, self._cpu_name,
                                                  "cpufreq", "scaling_max_freq")
        self._min_desired_filename = os.path.join(BASE_PATH, self._cpu_name,
                                                  "cpufreq", "scaling_min_freq")
        self._epp_filename = os.path.join(BASE_PATH, self._cpu_name,
                                          "cpufreq", "energy_performance_preference")
        self._epp_available_filename = os.path.join(BASE_PATH, self._cpu_name,
                                                    "cpufreq",
                                                    "energy_performance_available_preferences")
        self._sst_bf_base_filename = os.path.join(BASE_PATH,
                                                  "cpu{}".format(id_num),
                                                  "cpufreq", "base_frequency")
        try:
            self._epp_available = _read_sysfs(self._epp_available_filename)
        except (IOError, OSError):
            # EPP is not available
            pass

    def _read_capabilities(self):
        """
        Get constant capabilities of core, this is called at core initialization
        and does not need to be called by the application
        """

        # On initialization these values need to be checked before checking is sst_bf enabled
        try:
            self.sst_bf_base_freq = int(
                _read_sysfs(self._sst_bf_base_filename)) // 1000
        except (IOError, OSError) as err:
            if self.cpu.sys.sst_bf_enabled is None:  # Before this could be set to False on init
                pass
            else:
                raise IOError("{}\n"
                              "Could not read core {} SST-BF base frequency "
                              "from sysfs entry '{}'"
                              .format(err, self.core_id,
                                      self._sst_bf_base_filename))

        self.base_freq = self.cpu.base_freq

        # Check if core is high priority, depending on base frequency
        if self.cpu.sys.sst_bf_enabled and self.sst_bf_base_freq > self.base_freq:
            self.high_priority = True

        self.all_core_turbo_freq = self.cpu.all_core_turbo_freq
        self.highest_freq = self.cpu.highest_freq
        self.lowest_freq = self.cpu.lowest_freq

    def refresh_stats(self):
        """ Get current regularly changing or user defined stats of core """
        valid_range = [v for v in range(
            self.lowest_freq, self.highest_freq + 100, 100)]

        def get_desired_min_freq():
            """ Get current desired minimum core frequency """
            try:
                min = int(_read_sysfs(self._min_desired_filename)) // 1000
                if min not in valid_range:
                    raise ValueError("Incorrect sysfs Entry")
                return min
            except (IOError, OSError) as err:
                raise IOError("{}\nCould not read core {} stats from sysfs entry"
                              .format(err, self.core_id))

        def get_desired_max_freq():
            """ Get current desired maximum core frequency """
            try:
                max = int(_read_sysfs(self._max_desired_filename)) // 1000
                if max not in valid_range:
                    raise ValueError("Incorrect sysfs Entry")
                return max
            except (IOError, OSError) as err:
                raise IOError("{}\nCould not read core {} stats from sysfs entry"
                              .format(err, self.core_id))

        def get_desired_epp():
            """ Get current desired epp core value """
            try:
                if self.cpu.sys.epp_enabled:
                    epp = _read_sysfs(self._epp_filename)
                    if epp not in self._epp_available:  # Ensure valid sysfs entry before setting
                        raise ValueError("Incorrect sysfs Entry")
                    return epp
            except (IOError, OSError) as err:
                raise IOError("{} \nCould not read core {} stats from sysfs entry"
                              .format(err, self.core_id))

        def get_curr_freq():
            """ Get current frequency """
            regstr = _rdmsr(self.core_id, MSR_IA32_PERF_STATUS)
            # unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            # Byte 1 contains current frequency
            return data[1] * 100

        def check_core_online():
            """ Check that the core is online and available to use """
            try:
                with open(self._core_online_filename) as online_file:
                    return int(online_file.readline()) == 1
            except IOError:
                # File not found, core is online, proceed with setup
                return True

        self.min_freq = get_desired_min_freq()
        self.max_freq = get_desired_max_freq()
        self.epp = get_desired_epp()
        self.curr_freq = get_curr_freq()
        self.online = check_core_online()

    def commit(self, profile=""):
        """ Update sysfs entries for min/max/epp with core instance attributes """
        core_profiles = ["minimum", "maximum", "base", "default", "no_turbo"]

        if self.cpu.sys.sst_bf_enabled:
            core_profiles += ["sst_bf"]

        def apply_profile(profile=""):
            """ Set min and max core frequency based on profile if one has been chosen """
            if profile == "minimum":
                self.min_freq = self.lowest_freq
                self.max_freq = self.lowest_freq
            elif profile == "maximum":
                self.min_freq = self.highest_freq
                self.max_freq = self.highest_freq
            elif profile == "base":
                self.min_freq = self.base_freq
                self.max_freq = self.base_freq
            elif profile == "default":
                self.min_freq = self.lowest_freq
                self.max_freq = self.highest_freq
            elif profile == "no_turbo":
                self.min_freq = self.lowest_freq
                self.max_freq = self.base_freq
            elif profile == "sst_bf":
                self.min_freq = self.sst_bf_base_freq
                self.max_freq = self.sst_bf_base_freq

        def set_min_max_freq(self):
            """ Set desired minimum and maximum frequency """
            if self.min_freq > self.max_freq:
                raise ValueError("Cannot update core, desired min freq ({}) "
                                 "is greater than desired max freq ({})".format(self.min_freq, self.max_freq))

            try:
                # Write desired min, if failure, retry after setting max.
                _write_sysfs(self._min_desired_filename, self.min_freq * 1000)
                _write_sysfs(self._max_desired_filename, self.max_freq * 1000)
            except IOError as err:
                if err.errno != 22:  # EINVAL
                    raise
                _write_sysfs(self._max_desired_filename, self.max_freq * 1000)
                _write_sysfs(self._min_desired_filename, self.min_freq * 1000)

        def set_epp(self):
            """ Set energy performance preference """
            # EPP may not be available
            if not self.cpu.sys.epp_enabled:
                if self.epp is None:
                    return
                else:
                    raise ValueError("Cannot set epp to {}, EPP is not enabled"
                                     .format(self.epp))
            if self.epp and self.epp not in self._epp_available:
                raise ValueError("Cannot set epp to {}, available options are {}"
                                 .format(self.epp, self._epp_available))

            _write_sysfs(self._epp_filename, self.epp)

            # Setting to default changes epp to the actual default value, this needs to be read
            if self.epp == "default":
                self.epp = _read_sysfs(self._epp_filename)

        valid_range = [v for v in range(
            self.lowest_freq, self.highest_freq + 100, 100)]

        if self.min_freq not in valid_range:
            raise ValueError("Cannot update core, min freq out of valid range. "
                             "Lowest: {}, Highest: {}".format(self.lowest_freq, self.highest_freq))

        if self.max_freq not in valid_range:
            raise ValueError("Cannot update core, max freq out of valid range. "
                             "Lowest: {}, Highest: {}".format(self.lowest_freq, self.highest_freq))

        if profile and profile not in core_profiles:  # Check if valid profile
            raise ValueError("Cannot set core profile {}, available profiles are {}"
                             .format(profile, core_profiles))
        else:
            apply_profile(profile)

        try:
            set_min_max_freq(self)
        except (IOError, OSError) as err:
            raise IOError("{}\nCannot update min/max freq on core {}"
                          .format(err, self.core_id))

        try:
            set_epp(self)
        except (IOError, OSError) as err:
            raise IOError("{}\nCannot update epp on core {}"
                          .format(err, self.core_id))


class CPU(object):
    """
    CPU class which contains all data relevant to CPU,
    as well as CPU methods to get and set that data
    """

    def __init__(self):
        """ CPU object Constructor """
        self.cpu_id = None              # CPU id number
        self.physical_id = None         # physical cpu number
        self.core_list = []             # list of core objects on this CPU
        self.sys = SYSTEM               # system object
        self.turbo_enabled = False      # turbo enabled flag
        self.hwp_enabled = False        # HWP enabled flag
        self.sst_bf_configured = False  # cpu cores min&max set to sst_bf base frequency
        self.base_freq = None           # base frequency
        self.all_core_turbo_freq = None # all core turbo frequency
        self.highest_freq = None        # single core turbo frequency
        self.lowest_freq = None         # lowest active frequency
        self.uncore_hw_max = 2400       # max available uncore frequency
        self.uncore_hw_min = 1200       # min available uncore frequency
        self.power_consumption = None   # power consumption since last update
        self.tdp = None                 # max possible power consumption
        self.freq_budget = None         # Frequency budget for stable performance
        self.uncore_freq = None         # current uncore frequency
        self.uncore_max_freq = None     # max desired uncore frequency
        self.uncore_min_freq = None     # min desired uncore frequency

        # private power consumption-related data
        self._prev_power_cons_ts = None   # timestamp for previous power consumption data
        self._prev_power_cons_val = None  # previous power consumption data
        self._power_cons_max = None       # wraparound power consumption value
        self._power_cons_power_unit = None  # power unit as reported by MSR
        self._power_cons_energy_unit = None  # energy unit as reported by MSR

    def _read_capabilities(self, core=None):
        """
        Get constant capabilities of CPU, this is called at CPU initialization
        and does not need to be called by application
        """
        if core is None:
            core = self.core_list[0].core_id

        powercap_cpu_base = os.path.join(
            BASE_POWERCAP_PATH, "intel-rapl:{}".format(self.cpu_id))
        power_cons_msr = not os.path.isdir(powercap_cpu_base)

        def get_msr_power_units():
            """ Get power and energy units from MSR_RAPL_POWER_UNIT """
            regstr = _rdmsr(core, MSR_RAPL_POWER_UNIT)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)

            # power and energy units are first 4 bits of first two bytes
            power_unit = data[0] & 0xF
            energy_unit = data[1] & 0xF

            return power_unit, energy_unit

        def get_tdp_msr():
            """ Get TDP from MSR_PKG_POWER_INFO """
            regstr = _rdmsr(core, MSR_PKG_POWER_INFO)
            # Unpack the 8 bytes into array of 16-bit values
            data = struct.unpack('HHHH', regstr)

            return data[0] & 0x3FFF  # first 14 bits

        def get_min_max_freq():
            """ Get package turbo frequency and lowest frequency """
            max_filename = os.path.join(BASE_PATH, "cpu{}".format(core),
                                        "cpufreq", "cpuinfo_max_freq")
            min_filename = os.path.join(BASE_PATH, "cpu{}".format(core),
                                        "cpufreq", "cpuinfo_min_freq")
            files_map = {max_filename: 0, min_filename: 0}

            for file_name in files_map:
                try:
                    value = int(_read_sysfs(file_name)) // 1000
                    files_map[file_name] = value
                except (IOError, OSError) as err:
                    raise IOError("{}\nCould not read cpu {} capabilities from sysfs entry"
                                  .format(err, core))

            return files_map[min_filename], files_map[max_filename]

        def get_base_freq():
            """ Get out of the box frequency """
            regstr = _rdmsr(core, MSR_PLATFORM_INFO)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            return data[1] * 100

        def check_hwp():
            """ Check HWP enabled """
            regstr = _rdmsr(core, MSR_IA32_PM_ENABLE)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            data = data[0] & 1  # Flag contained in bit 0
            return data == 1

        def check_turbo():
            """ Check Turbo enabled """
            regstr = _rdmsr(core, MSR_IA32_MISC_ENABLES)
            # Unpack 8 bytes into array of unsigned chars
            msr_bytes = struct.unpack('BBBBBBBB', regstr)
            disabled = msr_bytes[4] & 0x40
            return disabled == 0

        def get_all_core_turbo():
            """ Get frequency at which all cores can go turbo """
            regstr = _rdmsr(core, MSR_TURBO_RATIO_LIMIT)
            # Unpack the 8 bytes into array of unsigned chars
            msr_bytes = struct.unpack('BBBBBBBB', regstr)
            data = msr_bytes[7]
            return data * 100

        def get_max_power_consumption():
            """ Get the max power consumption of CPU """
            try:
                path = os.path.join(powercap_cpu_base, "max_energy_range_uj")
                cons_max = int(_read_sysfs(path))
                # uJ to J
                cons_max /= 1000000.0
            except (IOError, OSError) as err:
                raise IOError(
                    "{}\nCould not read power consumption wraparound value".format(err))
            except ValueError as err:
                raise ValueError(
                    "{}\nCould not parse power consumption wraparound value".format(err))
            return cons_max

        def get_tdp_sysfs():
            """ Get max available power draw from CPU """
            try:
                path = os.path.join(powercap_cpu_base,
                                    "constraint_0_power_limit_uw")
                # convert uW to W
                tdp = int(_read_sysfs(path)) // 1000000
            except (IOError, OSError) as err:
                raise IOError("{}\nCould not read TDP value".format(err))
            except ValueError as err:
                raise ValueError("{}\nCould not parse TDP value".format(err))
            return tdp

        
        
        self.lowest_freq, self.highest_freq = get_min_max_freq()
        self.base_freq = get_base_freq()
        self.hwp_enabled = check_hwp()
        self.turbo_enabled = check_turbo()
        self.all_core_turbo_freq = get_all_core_turbo()
        self.freq_budget = sum([self.base_freq for c in self.core_list], 0)
        if power_cons_msr:
            # read raw power units from MSR
            power_unit, energy_unit = get_msr_power_units()

            # units are in (1 / 2 ^ msr value)
            self._power_cons_power_unit = 1.0 / (2.0 ** power_unit)
            self._power_cons_energy_unit = 1.0 / (2.0 ** energy_unit)

            self.tdp = get_tdp_msr() * self._power_cons_power_unit

            # calculate register wraparound value in energy units - it's a
            # 32-bit wide unsigned register, so it wraps around at 2 ^ 32
            self._power_cons_max = (2 ** 32) * self._power_cons_energy_unit
        else:
            self.tdp = get_tdp_sysfs()
            self._power_cons_max = get_max_power_consumption()

    # this isn't an inner function in refresh_stats because we need private state
    def _get_avg_power_consumption(self, core):
        """ Get average power consumption since last check """
        powercap_cpu_base = os.path.join(
            BASE_POWERCAP_PATH, "intel-rapl:{}".format(self.cpu_id))
        power_cons_msr = not os.path.isdir(powercap_cpu_base)

        def get_power_consumption_sysfs():
            """ Get current power consumption """
            try:
                path = os.path.join(powercap_cpu_base, "energy_uj")
                cons = int(_read_sysfs(path))
            except (IOError, OSError) as err:
                raise IOError(
                    "{}\nCould not read power consumption value".format(err))
            except ValueError as err:
                raise IOError(
                    "{}\nCould not parse power consumption value".format(err))
            return cons

        def get_power_consumption_msr(core):
            """ Get current power consumption from MSR """
            regstr = _rdmsr(core, MSR_PKG_ENERGY_STATUS)
            cur_cons, _ = struct.unpack('II', regstr)
            return cur_cons

        # first, read current power consumption value and timestamp
        cur_ts = time.monotonic()
        if power_cons_msr:
            # power consumption in energy units
            cur_cons = get_power_consumption_msr(core)
            # turn energy units to Joules
            cur_cons *= self._power_cons_energy_unit
        else:
            # power consumption in uJ
            cur_cons = get_power_consumption_sysfs()
            # uJ to J
            cur_cons /= 1000000.0

        # do we have a previous timestamp?
        prev_ts = self._prev_power_cons_ts
        prev_cons = self._prev_power_cons_val

        # sanity checks if previous values exist
        if prev_ts:
            # timer wraps around about every 60 seconds on a loaded system, so reset the values
            # if it's been longer than 60 seconds since last read
            if cur_ts - prev_ts >= 60:
                prev_ts = None
                prev_cons = None
            # in Python 2 we won't be using a monotonic clock so we're susceptible to timezone
            # changes, so also check for negative time
            elif cur_ts < prev_ts:
                prev_ts = None
                prev_cons = None

        # overwrite stored values to use them next time
        self._prev_power_cons_val = cur_cons
        self._prev_power_cons_ts = cur_ts

        # if this is our first read, or if we reset the values earlier, return 0
        if not prev_ts or not prev_cons:
            return 0

        # data is valid, so process it

        # adjust current value if the counter wrapped around
        if prev_cons > cur_cons:
            cur_cons -= self._power_cons_max

        diff_ts = cur_ts - prev_ts
        diff_cons = cur_cons - prev_cons

        # J / seconds gives us W
        res = diff_cons / diff_ts

        # constrain our values within TDP limits
        res = min(max(0.0, res), self.tdp)
        return res

    def refresh_stats(self, core=None):
        """ Get current regularly changing or user defined stats of CPU """
        if core is None:
            core = self.core_list[0].core_id

        def check_sst_bf_configured():
            if not self.sys.sst_bf_enabled:
                return False
            for core in self.core_list:
                if core.min_freq != core.sst_bf_base_freq or core.max_freq != core.sst_bf_base_freq:
                    return False
            return True

        def get_current_uncore_freq():
            """ Get frequency of package uncore """
            regstr = _rdmsr(core, MSR_UNCORE_PERF_STATUS)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            curr = data[0] & 0x7F  # bits 0-6
            return curr * 100

        def get_uncore_min_max():
            """ Get uncore min & max frequency """
            regstr = _rdmsr(core, MSR_UNCORE_RATIO_LIMIT)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            # Byte 0 & 1 contains the max/min uncore frequency
            maximum = data[0] & 0x7F  # bits 0-6
            minimum = data[1] & 0x7F  # bits 8-14
            return minimum * 100, maximum * 100

        self.sst_bf_configured = check_sst_bf_configured()
        self.uncore_freq = get_current_uncore_freq()
        self.uncore_min_freq, self.uncore_max_freq = get_uncore_min_max()
        self.power_consumption = self._get_avg_power_consumption(core)

    def commit(self):
        """ Update package wide MSRs with cpu object attributes """
        if self.uncore_min_freq > self.uncore_max_freq:
            raise ValueError("Cannot update uncore freq, desired min({}) greater than desired max({})"
                             .format(self.uncore_min_freq, self.uncore_max_freq))
        # Read all msr data as to not overwrite other MSR data on write
        read_regstr = _rdmsr(self.core_list[0].core_id, MSR_UNCORE_RATIO_LIMIT)
        data = struct.unpack('BBBBBBBB', read_regstr)

        # Update uncore desired min & max, currently only bytes 0 and 1 are used.
        write_regstr = struct.pack('BBBBBBBB',
                                   self.uncore_max_freq // 100, self.uncore_min_freq // 100,
                                   data[2], data[3], data[4], data[5], data[6], data[7])
        _wrmsr(self.core_list[0].core_id, MSR_UNCORE_RATIO_LIMIT, write_regstr)


class System(object):
    """
    SYSTEM class which contains all data relevant to the whole system,
    as well as system methods to get and set that data.
    """

    def __init__(self):
        """ SYSTEM object Constructor """
        self.cpu_list = CPUS            # list of CPU objects on the system
        self.sst_bf_enabled = False     # base frequency enabled in BIOS
        self.sst_bf_configured = False  # all system cores min&max set to sst_bf base frequency
        self.epp_enabled = None         # epp enabled flag

    def request_config(self, cpus=None):
        """
        Test is configuration is stable through either
        the current desired frequencies in core objects
        or through parameters passed to API.
        """
        def check_valid_core_freq(core):
            """ Ensure frequencies are valid """
            valid_range = [v for v in range(
                self.cpu_list[0].lowest_freq, self.cpu_list[0].highest_freq + 100, 100)]
            if  core.min_freq > core.max_freq:
                raise ValueError("Invalid config, desired min freq({}) "
                                 "is greater than desired max freq({})" .format(core.min_freq, core.max_freq))
            elif core.min_freq not in valid_range or core.max_freq not in valid_range:
                raise ValueError("Invalid config, core desired frequency, must be in range {} to {}"
                                 .format(core.lowest_freq, core.highest_freq))

        def test_current_config(cpus=None):
            """ Test current configuration of core objects """

            if not cpus:
                cpus = self.cpu_list
            cores = [c for cpu in cpus for c in cpu.core_list]
   
            # Check for SST-BF configuration
            if self.sst_bf_enabled:
                for core in cores:
                    check_valid_core_freq(core)
                    target = set([core.sst_bf_base_freq])
                    if set([core.min_freq, core.max_freq]) != target:
                        break
                else:
                    return True

            # Check requested configuration minimum greater than the cpu budget frequency
            for cpu in cpus:
                freqs = [c.min_freq for c in cpu.core_list]
                requested_budget = sum(freqs)
                over_act = max(freqs) > cpu.all_core_turbo_freq
                if over_act or requested_budget > cpu.freq_budget:
                    return False
            return True

        if cpus:
            if type(cpus) != list: # User passes single CPU Object
                cpus = [cpus]
            if not all([isinstance(c, CPU) for c in cpus]): # Ensure list only contains CPU objects
                raise ValueError("Invalid CPU object passed")
        return(test_current_config(cpus))

    def commit(self, profile=""):
        """ Commit all cores and CPU configurations"""
        for core in CORES:
            core.commit(profile)

        for cpu in self.cpu_list:
            cpu.commit()

    def _check_epp_enabled(self):
        """
        EPP is enabled if CPUID bits indicate support for EPP, and if there are
        sysfs entries.
        """
        core_obj = self.cpu_list[0].core_list[0]
        core_id = core_obj.core_id
        try:
            cpuinfo_obj = cpuinfo.get_info_list()[core_id]
        except (IOError, OSError):
            # failed to read /proc/cpuinfo, assume EPP is not supported
            self.epp_enabled = False
            return
        # if EPP bit in CPUID is not set, EPP is not supported
        if "hwp_epp" not in cpuinfo_obj.flags:
            self.epp_enabled = False
            return

        # EPP bit set, check if there are sysfs entries
        self.epp_enabled = os.path.isfile(core_obj._epp_filename)

    def _read_capabilities(self):
        def _check_sst_bf_enabled():
            """
            SST_BF is enabled when sysfs base frequencies differ between cores
            """
            base_freqs = set(core.sst_bf_base_freq for core in CORES)
            # if there are two tiers, that means SST-BF is enabled
            self.sst_bf_enabled = len(base_freqs) == 2

        _check_sst_bf_enabled()
        self._check_epp_enabled()

    def refresh_stats(self):
        def check_sst_bf_configured():
            """
            SST_BF is configured when the min & max of all cores is set to
            the priority based frequency of that core
            """
            for cpu in self.cpu_list:
                if not self.sst_bf_enabled:
                    cpu.sst_bf_configured = False
                    continue
                # assume configured unless we find otherwise
                
                for core in cpu.core_list:
                    target = set([core.sst_bf_base_freq])
                    if set([core.min_freq, core.max_freq]) != target:
                        cpu.sst_bf_configured = False
                        break
                else:
                    cpu.sst_bf_configured = True         
            results = [cpu.sst_bf_configured for cpu in self.cpu_list]
            self.sst_bf_configured = False not in results

        check_sst_bf_configured()

    def refresh_all(self):
        """ Refresh all system, cpu and core stats """
        for cpu in self.cpu_list:
            cpu.refresh_stats()
        for core in CORES:
            core.refresh_stats()
        self.refresh_stats()


def _rdmsr(core, msr):
    """
    Read a 64-byte value from an MSR through the sysfs interface.
    Returns an 8-byte binary packed string.
    """
    msr_filename = os.path.join("/dev/cpu", str(core), "msr")
    try:
        with open(msr_filename, "rb") as msr_file:
            os.lseek(msr_file.fileno(), msr, os.SEEK_SET)
            regstr = msr_file.read(8)
            return regstr
    except (IOError, OSError) as err:
        raise IOError("{}\nCould not read from MSR 0x{} on core {}"
                      .format(err, msr, core))


def _wrmsr(core, msr, regstr):
    """
    Write a 64-byte value to an MSR through the sysfs interface.
    Expects an 8-byte binary packed string in regstr.
    """
    msr_filename = os.path.join("/dev/cpu", str(core), "msr")
    try:
        with open(msr_filename, "wb") as msr_file:
            os.lseek(msr_file.fileno(), msr, os.SEEK_SET)
            msr_file.write(regstr)
    except (IOError, OSError) as err:
        raise IOError("{}\nCould not write to MSR 0x{} on core {}"
                      .format(err, msr, core))


def _write_sysfs(file_name, value):
    """
    Write desired value into sysfs file
    """
    with open(file_name, 'w') as sysfs:
        sysfs.write(str(value))


def _read_sysfs(filename):
    """
    Read desired value from sysfs file
    """
    with open(filename) as sysfs:
        value = sysfs.readline().strip("\n")
    return value


def get_cores():  # type: () -> List[Core]
    """
    Returns Core object list
    """
    if not CORES:
        _init()
    return CORES


def get_cpus():  # type: () -> List[CPU]
    """ Returns CPU object list """
    if not CPUS:
        _init()
    return CPUS


def get_system():  # type: () -> SYSTEM
    global SYSTEM
    """ Returns system object """
    if not SYSTEM:
        _init()
    return SYSTEM


def get_objects():  # type: () -> SYSTEM,List[CPU],List[Core]
    """ Returns all objects, system, cpus and cores """
    global SYSTEM
    if not SYSTEM:
        _init()
    return SYSTEM, CPUS, CORES


def _init():
    """ Check drivers present and populate core and CPU lists """

    _get_msr_driver()

    _get_scaling_driver()

    _populate_cores_cpus()


def _get_msr_driver():
    """ Check is MSR driver loaded """
    try:
        with open("/dev/cpu/0/msr", "r"):
            pass
    except (OSError, IOError) as e:
        if e.errno == 13:  # EACCES
            raise IOError("MSR Driver not accessible\nPlease run as 'root'.")
        raise IOError("MSR Driver not loaded\nRun 'modprobe msr'")


def _get_scaling_driver():
    """ Check is scaling driver loaded """
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"):
            pass
    except (IOError, OSError) as err:
        raise IOError("Scaling driver not loaded\n{}".format(err))


def _populate_cores_cpus():
    """ Create and initialize core and cpu object lists """
    global SYSTEM
    core_num = os.listdir("/sys/devices/system/cpu")
    regex = re.compile(r'cpu[0-9]+')
    core_num = list(filter(regex.match, core_num))
    corecount = len(core_num)
    cpu_ids = []
    ht_siblings_map = {}

    for core in range(corecount):
        # Get CPU ID of each core
        file_path = os.path.join(BASE_PATH, "cpu{}".format(core),
                                 "topology/physical_package_id")
        try:
            with open(file_path) as package_file:
                physical_id = int(package_file.read())
        except (IOError, OSError) as err:
            raise Exception("{}\nCould not read cores physical ID".format(err))

        # Get siblings of each core
        file_path = os.path.join(BASE_PATH, "cpu{}".format(core),
                                 "topology/thread_siblings_list")
        try:
            with open(file_path) as s_list:
                # thread_siblings_list is a CSV list, so parse it
                siblings = [int(c) for c in s_list.read().split(',')]
                # remove self from list
                siblings.remove(core)
        except (IOError, OSError) as err:
            raise Exception("{}\nCould not read thread siblings".format(err))
        # Store  siblings for current core in a map
        ht_siblings_map[core] = siblings

        # Create CPU object
        if physical_id not in cpu_ids:
            cpu_obj = CPU()
            cpu_obj.cpu_id = len(cpu_ids)
            cpu_ids.append(physical_id)
            cpu_obj.physical_id = physical_id
            CPUS.append(cpu_obj)
        else:
            cpu_idx = cpu_ids.index(physical_id)
            cpu_obj = CPUS[cpu_idx]

        # Create core object
        core_obj = Core(core, cpu_obj)
        cpu_obj.core_list.append(core_obj)

        # Create system object
        SYSTEM = System()
      
        # Add core object to core list
        CORES.append(core_obj)

    # Gather hyperthread siblings - we have to have the full list before we can do that
    for core in CORES:
        # Update siblings list in core object list
        core.thread_siblings = [CORES[s]
                                for s in ht_siblings_map[core.core_id]]

    # Initialize all system, cpu and core objects.
    SYSTEM._check_epp_enabled()
    for cpu in CPUS:
        cpu.sys = SYSTEM
        cpu._read_capabilities()
        cpu.refresh_stats()
    for core in CORES:
        core._read_capabilities()
        core.refresh_stats()
    SYSTEM._read_capabilities()
    SYSTEM.refresh_stats()
