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

MSR_PLATFORM_INFO = 0xCE
MSR_TURBO_RATIO_LIMIT = 0x1AD
MSR_IA32_PERF_STATUS = 0x198
MSR_IA32_MISC_ENABLES = 0x1A0
MSR_IA32_PM_ENABLE = 0x770
MSR_UNCORE_RATIO_LIMIT = 0x620
MSR_UNCORE_PERF_STATUS = 0x621
BASE_PATH = "/sys/devices/system/cpu"
BASE_POWERCAP_PATH = "/sys/devices/virtual/powercap/intel-rapl"

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
        self.cpu = cpu                                      # this cores cpu object
        self.thread_siblings = None                         # list of thread siblings
        self.high_priority = False                          # high/low priority
        self.base_freq = cpu.base_freq                      # base frequency
        self.sst_bf_base_freq = None                        # priority based frequency
        self.all_core_turbo_freq = cpu.all_core_turbo_freq  # all core turbo freq
        self.highest_freq = cpu.highest_freq                # single core turbo frequency
        self.lowest_freq = cpu.lowest_freq                  # lowest active frequency
        self.curr_freq = None                               # current core frequency
        self.min_freq = None                                # desired low frequency
        self.max_freq = None                                # desired high frequency
        self.epp = ""                                       # energy performance preference

        self._epp_available = []
        self._cpu_name = "cpu{}".format(self.core_id)
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
        except (IOError, OSError) as err:
            raise IOError("%s\nCould not read available performance profiles" % err)

    def read_capabilities(self):
        """
        Get constant capabilities of core, this is called at core initialization
        and does not need to be called by the application
        """
        if os.path.isfile(self._sst_bf_base_filename):
            try:
                self.sst_bf_base_freq = int(
                    _read_sysfs(self._sst_bf_base_filename)) // 1000
            except (IOError, OSError) as err:
                raise IOError("{}\n"
                              "Could not read core {} SST-BF base frequency "
                              "from sysfs entry '{}'"
                              .format(err, self.core_id,
                                      self._sst_bf_base_filename))

    def refresh_stats(self):
        """ Get current regularly changing or user defined stats of core """
        files_map = {
            self._max_desired_filename: "max_freq",
            self._min_desired_filename: "min_freq",
            self._epp_filename: "epp"
        }
        valid_range = [v for v in range(self.lowest_freq, self.highest_freq + 100, 100)]

        # Get desired min & max
        for file_name, attr in files_map.items():
            try:
                if attr == "epp":
                    value = _read_sysfs(file_name)
                    if value not in self._epp_available:  # Ensure valid sysfs entry before setting
                        raise ValueError("Incorrect sysfs Entry")
                    self.epp = value
                elif attr == "max_freq":
                    value = int(_read_sysfs(file_name)) // 1000
                    if value not in valid_range:  # Ensure valid sysfs entry before setting
                        raise ValueError("Incorrect sysfs Entry")
                    self.max_freq = value
                elif attr == "min_freq":
                    value = int(_read_sysfs(file_name)) // 1000
                    if value not in valid_range:  # Ensure valid sysfs entry before setting
                        raise ValueError("Incorrect sysfs Entry")
                    self.min_freq = value
            except (IOError, OSError) as err:
                raise IOError("%s\nCould not read core %s stats from sysfs entry" %
                              (err, str(self.core_id)))

        # Get current frequency
        regstr = _rdmsr(self.core_id, MSR_IA32_PERF_STATUS)
        # unpack the 8 bytes into array of unsigned chars
        data = struct.unpack('BBBBBBBB', regstr)
        # Byte 1 contains current frequency
        self.curr_freq = data[1] * 100

    def commit(self, profile=""):
        """ Update sysfs entries for min/max/epp with core instance attributes """
        core_profiles = ["minimum", "maximum", "base", "default", "no_turbo"]
        if self.cpu.sst_bf_enabled:
            core_profiles += ["sst_bf_base", "sst_bf_high_turbo", "sst_bf_low_turbo"]

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
            elif profile == "sst_bf_base":
                self.min_freq = self.sst_bf_base_freq
                self.max_freq = self.sst_bf_base_freq
            elif profile == "sst_bf_high_turbo":
                if self.high_priority:
                    self.min_freq = self.sst_bf_base_freq
                    self.max_freq = self.highest_freq
                else:
                    self.min_freq = self.lowest_freq
                    self.max_freq = self.sst_bf_base_freq
            elif profile == "sst_bf_low_turbo":
                if self.high_priority:
                    self.min_freq = self.sst_bf_base_freq
                    self.max_freq = self.sst_bf_base_freq
                else:
                    self.min_freq = self.lowest_freq
                    self.max_freq = self.highest_freq

        def set_min_max_freq(self):
            """ Set desired minimum and maximum frequency """
            if self.min_freq > self.max_freq:
                raise ValueError("Cannot update core, desired min freq(%s) "
                                 "is greater than desired max freq(%s)" %
                                 (str(self.min_freq), str(self.max_freq)))

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
            if self.epp not in self._epp_available:
                raise ValueError("Cannot set epp to %s, available options are %s" %
                                 (self.epp, self._epp_available))

            _write_sysfs(self._epp_filename, self.epp)

            # Setting to default changes epp to the actual default value, this needs to be read
            if self.epp == "default":
                self.epp = _read_sysfs(self._epp_filename)

        valid_range = [v for v in range(self.lowest_freq, self.highest_freq + 100, 100)]

        if self.min_freq not in valid_range:
            raise ValueError("Cannot update core, min freq out of valid range. "
                             "Lowest: %s, Highest: %s" % (self.lowest_freq, self.highest_freq))

        if self.max_freq not in valid_range:
            raise ValueError("Cannot update core, max freq out of valid range. "
                             "Lowest: %s, Highest: %s" % (self.lowest_freq, self.highest_freq))

        if profile and profile not in core_profiles:  # Check if valid profile
            raise ValueError("Cannot set core profile %s, available profiles are %s" %
                             (profile, core_profiles))
        else:
            apply_profile(profile)

        try:
            set_min_max_freq(self)
        except (IOError, OSError) as err:
            raise IOError("%s\nCannot update min/max freq on core %i" % (err, self.core_id))

        try:
            set_epp(self)
        except (IOError, OSError) as err:
            raise IOError("%s\nCannot update epp on core %i" % (err, self.core_id))


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
        self.sst_bf_enabled = False     # base frequency enabled in BIOS
        self.sst_bf_configured = False  # cores min&max set to sst_bf base frequency
        self.turbo_enabled = False      # turbo enabled flag
        self.hwp_enabled = False        # HWP enabled flag
        self.base_freq = None           # base frequency
        self.all_core_turbo_freq = None # all core turbo frequency
        self.highest_freq = None        # single core turbo frequency
        self.lowest_freq = None         # lowest active frequency
        self.uncore_hw_max = 2400       # max available uncore frequency
        self.uncore_hw_min = 1200       # min available uncore frequency
        self.power_consumption = None   # power consumption since last update
        self.tdp = None                 # max possible power consumption
        self.uncore_freq = None         # current uncore frequency
        self.uncore_max_freq = None     # max desired uncore frequency
        self.uncore_min_freq = None     # min desired uncore frequency

        # private power consumption-related data
        self._prev_power_cons_ts = None   # timestamp for previous power consumption data
        self._prev_power_cons_val = None  # previous power consumption data
        self._power_cons_max = None       # wraparound power consumption value

    def read_capabilities(self, core=None):
        """
        Get constant capabilities of CPU, this is called at CPU initialization
        and does not need to be called by application
        """
        if core is None:
            core = self.core_list[0].core_id

        powercap_cpu_base = os.path.join(BASE_POWERCAP_PATH, "intel-rapl:{}".format(self.cpu_id))

        def get_min_max_freq():
            """ Get package turbo frequency and lowest frequency """
            max_filename = os.path.join(BASE_PATH, "cpu{}".format(core),
                                        "cpufreq", "cpuinfo_max_freq")
            min_filename = os.path.join(BASE_PATH, "cpu{}".format(core),
                                        "cpufreq", "cpuinfo_min_freq")
            files_map = {max_filename : 0, min_filename : 0}

            for file_name in files_map:
                try:
                    value = int(_read_sysfs(file_name)) // 1000
                    files_map[file_name] = value
                except (IOError, OSError) as err:
                    raise IOError("%s\nCould not read cpu %d capabilities from sysfs entry" %
                                  (err, core))

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
            data = data[0] & 1 #Flag contained in bit 0
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
                # leave it to be in uJ
                cons_max = int(_read_sysfs(path))
            except (IOError, OSError) as err:
                raise IOError("%s\nCould not read power consumption wraparound value" % err)
            except ValueError as err:
                raise ValueError("%s\nCould not parse power consumption wraparound value" % err)
            return cons_max

        def get_tdp():
            """ Get max available power draw from CPU """
            try:
                path = os.path.join(powercap_cpu_base, "constraint_0_power_limit_uw")
                # convert uW to W
                tdp = int(_read_sysfs(path)) // 1000000
            except (IOError, OSError) as err:
                raise IOError("%s\nCould not read TDP value" % err)
            except ValueError as err:
                raise ValueError("%s\nCould not parse TDP value" % err)
            return tdp

        self.lowest_freq, self.highest_freq = get_min_max_freq()
        self.base_freq = get_base_freq()
        self.hwp_enabled = check_hwp()
        self.turbo_enabled = check_turbo()
        self.all_core_turbo_freq = get_all_core_turbo()
        self.tdp = get_tdp()
        self._power_cons_max = get_max_power_consumption()

    # this isn't an inner function in refresh_stats because we need private state
    def _get_avg_power_consumption(self):
        """ Get average power consumption since last check """
        powercap_cpu_base = os.path.join(BASE_POWERCAP_PATH, "intel-rapl:{}".format(self.cpu_id))

        def get_power_consumption():
            """ Get current power consumption """
            try:
                path = os.path.join(powercap_cpu_base, "energy_uj")
                cons = int(_read_sysfs(path))
            except (IOError, OSError) as err:
                raise IOError("%s\nCould not read power consumption value" % err)
            except ValueError as err:
                raise IOError("%s\nCould not parse power consumption value" % err)
            return cons


        # first, read current power consumption value and timestamp
        cur_ts = time.monotonic()
        cur_cons = get_power_consumption()

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
            if cur_ts < prev_ts:
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
        diff_cons = (cur_cons - prev_cons) / 1000000  #uJ to J

        # J / seconds gives us W
        res = diff_cons / diff_ts

        # constrain our values within TDP limits
        res = min(max(0.0, res), self.tdp)
        return res

    def refresh_stats(self, core=None):
        """ Get current regularly changing or user defined stats of CPU """
        if core is None:
            core = self.core_list[0].core_id

        def get_current_uncore_freq():
            """ Get frequency of package uncore """
            regstr = _rdmsr(core, MSR_UNCORE_PERF_STATUS)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            curr = data[0] & 0x7F # bits 0-6
            return curr * 100

        def get_uncore_min_max():
            """ Get uncore min & max frequency """
            regstr = _rdmsr(core, MSR_UNCORE_RATIO_LIMIT)
            # Unpack the 8 bytes into array of unsigned chars
            data = struct.unpack('BBBBBBBB', regstr)
            # Byte 0 & 1 contains the max/min uncore frequency
            maximum = data[0] & 0x7F # bits 0-6
            minimum = data[1] & 0x7F # bits 8-14
            return minimum * 100, maximum * 100

        self.uncore_freq = get_current_uncore_freq()
        self.uncore_min_freq, self.uncore_max_freq = get_uncore_min_max()
        self.sst_bf_configured = _check_sst_bf_configured(self)
        self.power_consumption = self._get_avg_power_consumption()


    def commit(self):
        """ Update package wide MSRs with cpu object attributes """
        if self.uncore_min_freq > self.uncore_max_freq:
            raise("Cannot update uncore freq, desired min(%s) greater than desired max(%s)" %
                  (str(self.uncore_min_freq), str(self.uncore_max_freq)))
        # Read all msr data as to not overwrite other MSR data on write
        read_regstr = _rdmsr(self.core_list[0].core_id, MSR_UNCORE_RATIO_LIMIT)
        data = struct.unpack('BBBBBBBB', read_regstr)

        # Update uncore desired min & max, currently only bytes 0 and 1 are used.
        write_regstr = struct.pack('BBBBBBBB',
                                   self.uncore_max_freq // 100, self.uncore_min_freq // 100,
                                   data[2], data[3], data[4], data[5], data[6], data[7])
        _wrmsr(self.core_list[0].core_id, MSR_UNCORE_RATIO_LIMIT, write_regstr)

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
        raise IOError("%s\nCould not read from MSR 0x%x on core %d" % (err, msr, core))

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
        raise IOError("%s\nCould not write to MSR 0x%x on core %d" % (err, msr, core))

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

# Core and cpu lists to be filled with corresponding objects
CORES = []
CPUS = []

def get_cores():  # type: () -> List[Core]
    """
    External API to create core object list, both core and cpu
    lists will be created on either get_cores or get_cpus function calls,
    only the requested list will be returned as both lists are accessible
    through each other, through the PACKAGE/CORE_LIST instance variables.
    """
    if not CORES:
        _init()
    return CORES

def get_cpus():  # type: () -> List[CPU]
    """
    External API to create cpu object list, both core and cpu
    lists will be created on either get_cpu or get_cores function calls,
    only the requested list will be returned as both lists are accessible
    through each other, through the CORE_LIST/PACKAGE instance variables.
    """
    if not CPUS:
        _init()
    return CPUS

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
    except IOError:
        raise IOError("MSR Driver not loaded\nRun 'modprobe msr'")
    except OSError:
        raise IOError("MSR Driver not loaded\nRun 'modprobe msr'")

def _get_scaling_driver():
    """ Check is scaling driver loaded """
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"):
            pass
    except (IOError, OSError) as err:
        raise IOError("Scaling driver not loaded\n%s" % err)

def _populate_cores_cpus():
    """ Create and initialize core and cpu object lists """
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
            raise Exception("%s\nCould not read cores physical ID" % err)

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
            raise Exception("%s\nCould not read thread siblings" % err)
        # Store  siblings for current core in a map
        ht_siblings_map[core] = siblings

        # Create CPU object and initialize
        if physical_id not in cpu_ids:
            cpu_obj = CPU()
            cpu_obj.cpu_id = len(cpu_ids)
            cpu_ids.append(physical_id)
            cpu_obj.physical_id = physical_id
            cpu_obj.read_capabilities(core)
            cpu_obj.refresh_stats(core)
            CPUS.append(cpu_obj)
        else:
            cpu_idx = cpu_ids.index(physical_id)
            cpu_obj = CPUS[cpu_idx]

        # Create core object and initialize
        core_obj = Core(core, cpu_obj)
        core_obj.read_capabilities()
        core_obj.refresh_stats()

        # Add core to CPU core_list
        cpu_obj.core_list.append(core_obj)

        # Check if core is high priority, depending on base frequency
        if core_obj.sst_bf_base_freq > core_obj.base_freq:
            core_obj.high_priority = True

        # Add core object to core list
        CORES.append(core_obj)

    # Gather hyperthread siblings - we have to have the full list before we can do that
    for core in CORES:
        # Update siblings list in core object list
        core.thread_siblings = [CORES[s] for s in ht_siblings_map[core.core_id]]

    # Post core & cpu initialization, check if SST-BF is enabled and configured
    for cpu in CPUS:
        # if there's no sysfs base frequency, SST-BF is not supported
        if cpu.core_list[0].sst_bf_base_freq:
            cpu.sst_bf_enabled = _check_sst_bf_enabled(cpu)
            cpu.sst_bf_configured = _check_sst_bf_configured(cpu)

def _check_sst_bf_configured(cpu_obj):
    """
    SST_BF is configured when the min & max of all cores is set to
    the priority based frequency of that core
    """
    if cpu_obj.sst_bf_enabled:
        for core in cpu_obj.core_list:
            if core.min_freq != core.sst_bf_base_freq or core.max_freq != core.sst_bf_base_freq:
                return False
    return True


def _check_sst_bf_enabled(cpu_obj):
    """
    SST_BF is enabled when sysfs base frequencies differ between cores
    """
    prev_seen = None
    for core in cpu_obj.core_list:
        if not prev_seen:
            prev_seen = core.sst_bf_base_freq
            continue
        # base frequencies differ, that means SST-BF is enabled
        if prev_seen != core.sst_bf_base_freq:
            return True
    # base frequencies don't differ
    return False
