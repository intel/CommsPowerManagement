#!/usr/bin/python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019-20 Intel Corporation
"""Power Management configuration script"""

from __future__ import print_function
import os
import sys
import getopt
import re
import struct
import glob
import time

# raw_input() is only available in python 2.
try:
    raw_input
except NameError:
    raw_input = input

CPU_MAX_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
CPU_MIN_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq"
MAX_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
MIN_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq"
FREQ_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies"
GOV_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors"
DRV_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"
MSR_FILE = "/dev/cpu/0/msr"
UNCORE_PATH = "/sys/devices/system/cpu/intel_uncore_frequency/"
UNCORE_INIT_MIN = "initial_min_freq_khz"
UNCORE_INIT_MAX = "initial_max_freq_khz"
UNCORE_MIN = "min_freq_khz"
UNCORE_MAX = "max_freq_khz"
UNCORE_CUR = "current_freq_khz"
TURBO_PATH = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPU_PATH = "/sys/devices/system/cpu/"
TOPO_PKG = "topology/physical_package_id"
TOPO_DIE_ID = "topology/die_id"
TOPO_SIBLING_LIST = "topology/core_siblings_list"
NODE_PATH="/sys/devices/system/node/"
PKG0_DIE0_PATH = "package_00_die_00"
MSR_UNCORE_RATIO_LIMIT = 0x620
MSR_UNCORE_PERF_STATUS = 0x621
UNCORE_HW_MAX = 2400
UNCORE_HW_MIN = 800
MHZ_CONVERSION_FACTOR = 1000
pstateList = []
freqs = []
stateList = []
govList = []
scriptname = "power.py"
driver = ""
freq_P0 = 0
freq_P1 = 0
freq_P1n = 0
PKG_TO_DIE_PATH = {}
CORE_TO_PKG = {}
list_interval = 0


def getfileval(stateFileName):
    with open(stateFileName, 'r') as state_file:
        return state_file.readline().strip("\n")


def rdmsr(core, msr):
    """
    Read a 64-byte value from an MSR through the sysfs interface.
    Returns an 8-byte binary packed string.
    """
    try:
        msr_filename = os.path.join("/dev/cpu/", str(core), "msr")
        msr_file = os.open(msr_filename, os.O_RDONLY)
        os.lseek(msr_file, msr, os.SEEK_SET)
        regstr = os.read(msr_file, 8)
        os.close(msr_file)
        return regstr
    except (IOError, OSError) as err:
        raise IOError(f"{err}: Could not read MSR 0x{msr} on core {core}")


def wrmsr(core, msr, regstr):
    """
    Writes a 64-byte value to an MSR through the sysfs interface.
    Expects an 8-byte binary packed string in regstr.
    """
    try:
        msr_filename = os.path.join("/dev/cpu", str(core), "msr")
        with open(msr_filename, "wb") as msr_file:
            msr_file.seek(msr)
            msr_file.write(regstr)
    except (IOError, OSError) as err:
        raise IOError("{}\nCould not write to MSR 0x{} on core {}"
                      .format(err, msr, core)) from err


def get_cpu_base_frequency(core):
    regstr = rdmsr(0, 0xCE)  # MSR_PLATFORM_INFO
    # Unpack the 8 bytes into array of unsigned chars
    bytes = struct.unpack('BBBBBBBB', regstr)
    # Byte 1 contains the max non-turbo frequecy
    P1 = bytes[1]*100
    return P1


def check_driver():
    global driver
    global freq_P1

    try:
        drvFile = open(DRV_FILE, 'r')
    except IOError:
        print()
        print("ERROR: No pstate driver file found.")
        print("       Are P-States enabled in the system BIOS?")
        print()
        return 0
    driver = drvFile.readline().strip("\n")
    drvFile.close()

    print("Current pstate driver is '" + driver + "'")

    try:
        open(MSR_FILE, "r")
    except IOError:
        print("ERROR: Need the 'msr' kernel module")
        print("Please run 'modprobe msr'")
        sys.exit(1)
    # get the P1 frequency
    freq_P1 = get_cpu_base_frequency(11)
    print("CPU Base Frequency (P1): " + str(freq_P1) + "MHz")
    return 1


def get_pstates():
    global freq_P0
    global freq_P1n
    if driver == "acpi-cpufreq":
        freq_file = open(FREQ_FILE)
        frequencies = freq_file.readline().strip("\n")
        freq_file.close()
        freq_list = frequencies.split(" ")
        freq_list = list(filter(len, freq_list))
        freqs = list(map(int, freq_list))
        for x in range(0, len(freqs)):
            freqs[x] = int(freqs[x])/1000
    else:
        min_file = open(CPU_MIN_FILE)
        min = int(int(min_file.readline().strip("\n"))/1000)
        min_file.close()
        freq_P1n = min
        max_file = open(CPU_MAX_FILE)
        max = int(int(max_file.readline().strip("\n"))/1000)
        max_file.close()
        freq_P0 = max
        freqs = []
        for i in range(min, max+1, 100):
            freqs.append(i)

    freqs.sort(reverse=True)
    return freqs


def show_pstates():
    freq_list = get_pstates()
    print(" Available P-States: " + str(freq_list))

    if (freq_list[0]-1 == freq_list[1]):
        print("    Turbo Available: Yes (use pstate '" +
              str(freq_list[0]) + "')", end='')
        try:
            if int(getfileval(TURBO_PATH)) == 0:
                print(": Enabled")
            else:
                print(": Disabled")
        except (IOError, OSError) as err:
            print(f"{err}: failed to read turbo status")
    elif freq_P0 > freq_P1:
        print("    Turbo Available: Yes (any pstate above '" +
              str(freq_P1) + "')", end='')
        try:
            if int(getfileval(TURBO_PATH)) == 0:
                print(": Enabled")
            else:
                print(": Disabled")
        except (IOError, OSError) as err:
            print(f"{err}: failed to read turbo status")
    else:
        print("    Turbo Available: No")
    return freq_list


def get_cstates():
    stateList = []
    try:
        states = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle/")
    except OSError:
        states = ""
    for state in states:
        stateFileName = f'/sys/devices/system/cpu/cpu0/cpuidle/{state}/name'
        stateFile = open(stateFileName, 'r')
        statename = stateFile.readline().strip("\n")
        stateList.append(statename)
        stateFile.close()
    return stateList


def show_cstates():
    stateList = get_cstates()
    s = " Available C-States: " + str(stateList)
    print(s)


def get_governors():
    govFile = open(GOV_FILE)
    govs = govFile.readline().strip("\n")
    govFile.close()
    govList = govs.split(" ")
    govList = list(filter(len, govList))
    return govList


def show_governors():
    govList = get_governors()
    s = "Available Governors: " + str(govList)
    print(s)


def is_multi_uncore_sku():
    """Checks if the system has nultiple uncores"""
    return os.path.isdir(os.path.join(UNCORE_PATH, "uncore00"))


def show_available_uncore_clusters():
    """Display uncores available in the system"""
    if is_multi_uncore_sku():
        cluster_list = []
        for dirpath, dirnames, filenames in os.walk(UNCORE_PATH):
            for dirname in dirnames:
                if dirname.startswith("uncore"):
                    cluster_list.append(dirname[6:])

        cluster_list.sort()
        print(f"\nAvailable uncore cluster: {cluster_list}\n")


def getinfo():
    global driver

    print()
    print("     P-State Driver: " + driver)
    print(" CPU Base Frequency: " + str(freq_P1) + "MHz")
    show_pstates()

    cpucount = getcpucount()
    s = "     Number of CPUs: " + str(cpucount)
    print(s)

    show_governors()
    show_cstates()
    show_available_uncore_clusters()


def writetofile(val, stateFileName):
    with open(stateFileName, 'w') as state_file:
        state_file.write(val)


def get_min_max_uncore_freq_msr(core_id):
    """ Get the min uncore frequeny from MSR."""
    try:
        regstr = rdmsr(core_id, MSR_UNCORE_RATIO_LIMIT)
        # Unpack the 8 bytes into array of unsigned chars
        msr_bytes = struct.unpack('BBBBBBBB', regstr)
        # Byte 1 contains the max non-turbo frequecy
        uncore_max = msr_bytes[0]*100
        uncore_min = msr_bytes[1]*100
        return uncore_min, uncore_max
    except(IOError, OSError):
        return 0, 0


def get_cur_uncore_freq_msr(core_id):
    """ Get the current uncore frequency from MSR."""
    try:
        # read current uncore frequency
        regstr = rdmsr(core_id, MSR_UNCORE_PERF_STATUS)
        msr_bytes = struct.unpack('BBBBBBBB', regstr)
        uncore_cur = msr_bytes[0]*100

        return uncore_cur

    except(IOError, OSError):
        return 0


def show_uncore_from_MSRs():
    """ Called if no uncore driver installed. Uses MSR values """

    print("==================   ==========================    ==============")
    print("Uncore                    Min      Max  Current         Core list")
    print("==================   ==========================    ==============")
    for entry in os.listdir(NODE_PATH):
        if entry.startswith("node"):
            for entry2 in os.listdir(NODE_PATH + entry):
                match =  re.match(r'^cpu(\d+)', entry2)
                if match:
                    core = int(match.group(1))
                    cpu_dir_path = os.path.join(CPU_PATH, "cpu" + str(core))
                    core_list_path = os.path.join(cpu_dir_path, TOPO_SIBLING_LIST)
                    core_list_data = getfileval(core_list_path)
                    uncore_min, uncore_max = get_min_max_uncore_freq_msr(core)
                    uncore_cur = get_cur_uncore_freq_msr(core)
                    socket = entry.replace("node", "Socket ")
                    print(f"{socket:<18}   {uncore_min:>8} {uncore_max:>8} {uncore_cur:>8}  {core_list_data:>16}")
                    break


def show_uncore_freqs():
    """ Show available uncore freqs from sysfs/MSR."""
    try:
        init_min_path = os.path.join(UNCORE_PATH, PKG0_DIE0_PATH,
                                     UNCORE_INIT_MIN)
        init_max_path = os.path.join(UNCORE_PATH, PKG0_DIE0_PATH,
                                     UNCORE_INIT_MAX)
        min = int(getfileval(init_min_path)) // MHZ_CONVERSION_FACTOR
        max = int(getfileval(init_max_path)) // MHZ_CONVERSION_FACTOR
    except (IOError, OSError, ValueError):
        min = UNCORE_HW_MIN
        max = UNCORE_HW_MAX

    uncore_freqs = list(reversed(range(min, max+1, 100)))
    print(" Available uncore freqs: " + str(uncore_freqs))
    return uncore_freqs


def set_turbo(val):
    """This function enable or disable the turbo."""
    try:
        writetofile(str(val), TURBO_PATH)
    except (IOError, OSError, ValueError) as err:
        print(f"{err}: failed to enable or disable the turbo")


def get_physical_id_mapping():
    """This function returns dictionary with packageID and cpu associated with ID"""
    physical_id_mapping = {}
    for entry in os.listdir(CPU_PATH):
        if entry.startswith('cpu'):
            package_id_path = os.path.join(CPU_PATH, entry, TOPO_PKG)
            if os.path.exists(package_id_path):
                package_id = getfileval(package_id_path)
                if package_id in physical_id_mapping:
                    physical_id_mapping[package_id].append(entry[3:])
                else:
                    physical_id_mapping[package_id] = [entry[3:]]
    return dict(sorted(physical_id_mapping.items()))


def get_cluster_id_mapping():
    """Returns dictionary with uncores and it package ID as key, value pairs """
    cluster_id_mapping = {}
    for entry in os.listdir(UNCORE_PATH):
        if entry.startswith('uncore'):
            uncore_fab_path = os.path.join(UNCORE_PATH, entry)
            if os.path.isdir(uncore_fab_path):
                fab_pkg_path = os.path.join(uncore_fab_path, "package_id")
                if os.path.isfile(fab_pkg_path):
                    with os.popen(f"cat {fab_pkg_path}") as f:
                        uncore_output = f.read()
                        cluster_id_mapping[entry] = uncore_output.strip()
    return dict(sorted(cluster_id_mapping.items()))

def get_package_id_mapping():
    """Returns dictionary with package ID as key, value pairs """
    cluster_id_mapping = {}

    # make a regex so we can extract the pkg_id from the directory name.
    pattern = re.compile(r'package_(\d+)')

    for entry in os.listdir(UNCORE_PATH):
        # look for a directory that starts with package_ and has a number.
        match = pattern.match(entry)
        if match:
            pkg_id = match.group(1)
            uncore_fab_path = os.path.join(UNCORE_PATH, entry)
            if os.path.isdir(uncore_fab_path):
                cluster_id_mapping[entry] = pkg_id
    return dict(sorted(cluster_id_mapping.items()))

def uncore_info():
    """This function collects and prints uncore uncore information"""

    directory = UNCORE_PATH[0:-1]

    if not os.path.exists(directory):
        print(f"Missing [{directory}], is kernel uncore driver installed?")
        show_uncore_from_MSRs()
        return

    physical_id_mapping = get_physical_id_mapping()
    if is_multi_uncore_sku():
        cluster_id_mapping = get_cluster_id_mapping()
    else:
        cluster_id_mapping = get_package_id_mapping()


    print("==================   ==========   ========   ==========================    ==============")
    print("                                                  Uncore freq                     ")
    print("Uncore Identifier    package Id     Die ID        Min      Max  Current         Core list")
    print("==================   ==========   ========   ==========================    ==============")
    for folder_name, value in cluster_id_mapping.items():
        if folder_name is not None:
            for pkg_id , cpus_list in physical_id_mapping.items():
                if int(value.strip()) == int(pkg_id.strip()):
                    uncore_fab_path = os.path.join(UNCORE_PATH, folder_name)
                    cpu_dir_path = os.path.join(CPU_PATH, "cpu" + cpus_list[0])
                    min_path = os.path.join(uncore_fab_path, UNCORE_MIN)
                    max_path = os.path.join(uncore_fab_path, UNCORE_MAX)
                    cur_path = os.path.join(uncore_fab_path, UNCORE_CUR)
                    pkg_id_path = os.path.join(cpu_dir_path, TOPO_PKG)
                    die_id_path = os.path.join(cpu_dir_path, TOPO_DIE_ID)
                    core_list_path = os.path.join(cpu_dir_path, TOPO_SIBLING_LIST)

                    uncore_min =  int(getfileval(min_path)) // MHZ_CONVERSION_FACTOR
                    uncore_max =  int(getfileval(max_path)) // MHZ_CONVERSION_FACTOR
                    try:
                        uncore_cur =  int(getfileval(cur_path)) // MHZ_CONVERSION_FACTOR
                    except (IOError, OSError) as err:
                        uncore_cur = 0
                    pkg_id_data = getfileval(pkg_id_path)
                    die_id_data = getfileval(die_id_path)
                    core_list_data = getfileval(core_list_path)
                    print(f"{folder_name:<18}   {pkg_id_data:>10}  {die_id_data:>9}   {uncore_min:>8} {uncore_max:>8} {uncore_cur:>8}  {core_list_data:>16}")
    print("")


def listinfo(cpurange):
    try:
        cstates = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle")
    except OSError:
        cstates = ""
    print("")
    print("==== ================================", end=' ')

    # pointer_pos used for formating C-STATE title
    pointer_pos = 1
    for x in range(len(cstates)):
        print("=======", end='')
        pointer_pos += 7
        if x != 0:
            print("=", end='')
            pointer_pos += 1
    if cstates != "":
        print(" ", end='')

    print("")

    print("                         P-STATE INFO", end='')
    if cstates != "":
        cstates_title = "C-STATES DISABLED?"
        print(f'{cstates_title:>{pointer_pos}}', end='')

    print("")

    print("Core    Max    Min    Now    Governor", end='')
    cstates = sorted(cstates)
    for x in cstates:
        name = getfileval(
            "/sys/devices/system/cpu/cpu0/cpuidle/" + x + "/name")
        print(" % 7s" % (name,), end='')
    print("")

    print("==== ====== ====== ====== ===========", end='')
    for x in cstates:
        print(" =======", end='')
    print("")

    for x in cpurange:
        max = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_max_freq")
        min = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_min_freq")
        cur = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_cur_freq")
        max = int(max) // MHZ_CONVERSION_FACTOR
        min = int(min) // MHZ_CONVERSION_FACTOR
        cur = int(cur) // MHZ_CONVERSION_FACTOR
        gov = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_governor")
        print(f"{x:4} {max:>6} {min:>6} {cur:>6} {gov:>11}", end='')
        for y in cstates:
            value = getfileval("/sys/devices/system/cpu/cpu" +
                               str(x) + "/cpuidle/" + y + "/disable")
            if int(value) > 0:
                print(" % 7s" % ("YES",), end='')
            else:
                print(" % 7s" % ("no",), end='')
        print("")
    print("")


def getcpus():
    cpus = os.listdir("/sys/devices/system/cpu")
    regex = re.compile(r'cpu[0-9]')
    cpus = list(filter(regex.search, cpus))
    return cpus


def getcpucount():
    cpucount = len(getcpus())
    return cpucount


def set_max_cpu_freq(maxfreq, cpurange):
    for x in cpurange:
        maxName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_max_freq"
        try:
            maxFile = open(maxName, 'w')
        except OSError:
            print("Could not open '" + str(maxName) + "', skipping.")
            continue
        print("Writing " + str(maxfreq) + " to " + maxName)
        maxFile.write(str(maxfreq))
        maxFile.close()


def set_min_cpu_freq(minfreq, cpurange):
    for x in cpurange:
        minName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_min_freq"
        try:
            minFile = open(minName, 'w')
        except OSError:
            print("Could not open '" + str(minName) + "', skipping.")
            continue
        print("Writing " + str(minfreq) + " to " + minName)
        minFile.write(str(minfreq))
        minFile.close()


def set_cpu_freq(setfreq, cpurange):
    for x in cpurange:
        setName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_setspeed"
        try:
            minFile = open(setName, 'r+')
        except OSError:
            print("Could not open '" + str(setName) + "', skipping.")
            continue
        current = minFile.readline().strip("\n")
        if current == "<unsupported>":
            print("Error, cannot set frequency for core " +
                  str(x) + " " + current + " Need '-g userspace'")
        else:
            print("Writing " + str(setfreq) + " to " + setName)
            minFile.write(str(setfreq))
        minFile.close()


def set_governor(gov, cpurange):
    for x in cpurange:
        govName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_governor"
        try:
            govFile = open(govName, 'w')
        except OSError:
            print("Could not open '" + str(govName) + "', skipping.")
            continue
        print("Writing '" + str(gov) + "' to " + govName)
        govFile.write(str(gov))
        govFile.close()


def set_cstate(cstate, disable, cpurange):

    # Get list of cstate dirs to iterate through to find the cstate name
    cstates = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle")

    for x in cpurange:
        for y in cstates:
            name = getfileval(
                "/sys/devices/system/cpu/cpu0/cpuidle/" + y + "/name")
            if (name == cstate):
                stateName = "/sys/devices/system/cpu/cpu" + \
                    str(x) + "/cpuidle/" + str(y) + "/disable"
                try:
                    stateFile = open(stateName, 'w')
                except OSError:
                    print("Could not open '" + str(stateName) + "', skipping.")
                    continue
                print("Writing '" + str(disable) + "' to " + stateName)
                stateFile.write(str(disable))
                stateFile.close()


def getPkgId(core_id):
    try:
        if core_id in CORE_TO_PKG:
            pkg = CORE_TO_PKG[core_id]
        else:
            pkgId = os.path.join(CPU_PATH, f"cpu{core_id}/", TOPO_PKG)
            pkg = getfileval(pkgId)
            CORE_TO_PKG[core_id] = pkg
        return pkg
    except (IOError, OSError) as err:
        print(f"{err}")
        return None


def get_sysfs_die_path(pkg):

    # find die path
    if pkg in PKG_TO_DIE_PATH:
        die_path = PKG_TO_DIE_PATH[pkg]
    else:
        # haven't seen this cpu before
        pkg_die_path = f"package_*{pkg}_die_*/"
        path = os.path.join(UNCORE_PATH, pkg_die_path)
        pkg_n_die_p = glob.glob(path)
        die_path = pkg_n_die_p[0] if pkg_n_die_p else None
        PKG_TO_DIE_PATH[pkg] = die_path

    if not die_path:
        # path was reported as unavailable
        raise IOError("uncore_freq sysfs not available")

    return die_path


def set_uncore_sysfs(uncore_freq, uncore, path_constant):
    """Set freq for the uncore using sysfs."""
    cluster_info = "uncore" + uncore
    min_path = os.path.join(UNCORE_PATH, cluster_info, path_constant)
    print(f"Writing {uncore_freq} to {min_path}")
    writetofile(str(uncore_freq * 1000), min_path)
    print("")


def set_uncore_min_sysfs(uncore_freq, uncore):
    """Set uncore_ freq as min freq for the uncore using sysfs."""
    set_uncore_sysfs(uncore_freq, uncore, UNCORE_MIN)


def set_uncore_max_sysfs(uncore_freq, uncore):
    """Set uncore_ freq as max freq for the uncore using sysfs."""
    set_uncore_sysfs(uncore_freq, uncore, UNCORE_MAX)


def get_uncore_from_user(min_freq, max_freq):
    """With a valid user input the function sets min/max frequency"""
    show_available_uncore_clusters()
    pattern = r'^\d{2}$'
    uncore = raw_input("Select uncore cluster:")
    try:
        if re.match(pattern, uncore):
            if min_freq:
                set_uncore_min_sysfs(min_freq, uncore)
            elif max_freq:
                set_uncore_max_sysfs(max_freq, uncore)
        else:
            raise ValueError()
    except(IOError, ValueError):
        raise ValueError("\nError : Invalid value.\nEnter correct value shown in available uncore cluster \n")


def set_uncore_freq(min_freq=None, max_freq=None):
    if (is_multi_uncore_sku()):
        # Set frequency for specific uncore
        print("\nUpdating uncore frequency...")
        get_uncore_from_user(min_freq, max_freq)
    else:
        directory = UNCORE_PATH[0:-1]
        if not os.path.exists(directory):
            print(f"Missing [{directory}], is kernel uncore driver installed?")
            return

        # Set Uncore for all package ids
        for entry in os.listdir(UNCORE_PATH):
            if entry.startswith('package'):
                try:
                    initial_max_freq = int(getfileval(f"{UNCORE_PATH}/{entry}/{UNCORE_INIT_MAX}")) // MHZ_CONVERSION_FACTOR
                    initial_min_freq = int(getfileval(f"{UNCORE_PATH}/{entry}/{UNCORE_INIT_MIN}")) // MHZ_CONVERSION_FACTOR
                except (IOError, OSError) as err:
                    raise IOError(f"{err}: failed to get initial min/max uncore frequency")
                if max_freq:
                    if (max_freq < initial_min_freq) or (max_freq > initial_max_freq):
                        raise ValueError("\nError : value outside allowed min/max range\n")
                    try:
                        writetofile(str(max_freq * MHZ_CONVERSION_FACTOR), f"{UNCORE_PATH}/{entry}/{UNCORE_MAX}")
                        print(f"Set maximum uncore frequency to {max_freq} for {entry}")
                    except (IOError, OSError) as err:
                        raise IOError(f"{err}: failed to set max uncore frequency")
                if min_freq:
                    if min_freq < initial_min_freq or min_freq > initial_max_freq:
                        raise ValueError("\nError : value outside allowed min/max range\n")
                    try:
                        writetofile(str(min_freq * MHZ_CONVERSION_FACTOR), f"{UNCORE_PATH}/{entry}/{UNCORE_MIN}")
                        print(f"Set minimum uncore frequency to {min_freq} for {entry}")
                    except (IOError, OSError) as err:
                        raise IOError(f"{err}: failed to set min uncore frequency")


def range_expand(s):
    try:
        r = []
        for i in s.split(','):
            if '-' not in i:
                r.append(int(i))
            else:
                l, h = map(int, i.split('-'))
                r += range(l, h+1)
        return r
    except ValueError:
        return None


def validate_cores(cores):
    cores_range = range_expand(cores)
    if not cores_range:
        raise ValueError("Invalid core range")
    cpus = getcpus()
    # check if there are invalid cores in the core list
    diff = set(cores_range).difference(set(range(len(cpus))))
    if diff:
        raise ValueError("Invalid core range: cores {} do"
                         " not exist".format(list(diff)))
    return cores_range


def show_help():
    print("")
    print(scriptname + ' -i -M <maxfreq> -m <minfreq> -s <setfreq> -r <range> -g <governor>')
    print('   <no params>   use interactive menu')
    print('   -h            Show this help')
    print('   -i            Show information on available freqs, C-States, etc')
    print('   -f            Show UNCORE information')
    print('   -l            List information on each core')
    print('   -L <sec>      List information repeatedly at <sec> intervals (need -l or -f, or both)')
    print('   -M <freq>     Set core maximum frequency. Can also use "max", "min", or "base"')
    print('   -m <freq>     Set core minimum frequency. Can also use "max", "min", or "base"')
    print('   -s <freq>     Set core frequency (within min and max)')
    print('   -r <range>    Range of cores to affect, e.g. 1-3,5,7')
    print('   -g <governor> Set core governor (usually \'userspace\')')
    print('   -e <cstate>   Enable core C-State ')
    print('   -d <cstate>   Disable core C-State ')
    print('   -U <freq>     Set uncore maximum frequency')
    print('   -u <freq>     Set uncore minimum frequency')
    print('   -T            Enable Turbo')
    print('   -t            Disable Turbo')
    print()
    print('Examples:')
    print()
    print('1. Set governor to ondemand, min 1GHz, max 2.5GHz, cores 0-10')
    print()
    print('   ' + scriptname + ' -g ondemand -r 0-10 -M 2500 -m 1000')
    print()
    print('2. Set governor to userspace, cores 2 and 4 only, set freq to 2GHz')
    print()
    print('   ' + scriptname + ' -g userspace -r 2,4 -s 2000')
    print()
    print('3. Set governor to userspace, core 1, set freq to Turbo Boost')
    print('   this assumes there\'s a 2501 and a 2500 freq available.')
    print()
    print('   ' + scriptname + ' -g userspace -r 1 -M 2501 -s 2501')
    print()
    print('4. Display information on the uncore')
    print()
    print('   ' + scriptname + ' -f')
    print()
    print('5. Display information about core and uncore every second')
    print()
    print('   ' + scriptname + ' -L 1 -lf')
    print()


def input_governor():
    govList = get_governors()
    i = 1
    for x in govList:
        print(' [' + str(i) + '] ' + x)
        i = i + 1
    selection = raw_input("Select Governor: ")
    if ((int(selection) > 0) and (int(selection) <= len(govList))):
        return(govList[int(selection)-1])
    else:
        return ""


def input_cstate():
    stateList = get_cstates()
    i = 1
    for x in stateList:
        print(' [' + str(i) + '] ' + x)
        i = i + 1
    selection = raw_input("Select C-State: ")
    if ((int(selection) > 0) and (int(selection) <= len(stateList))):
        return(stateList[int(selection)-1])
    else:
        return ""


def do_menu(cpurange):
    print("----------------------------------------------------------")
    print("[1] Display Available Settings")
    print("[2] Display Current Settings")
    print("")
    print("[3] Display Available P-States")
    print("[4] Set P-State governor for a range of cores")
    print("[5] Set Maximum P-State for a range of cores")
    print("[6] Set Minimum P-State for a range of cores")
    print("")
    print("[7] Display Available C-States")
    print("[8] Enable C-State for a range of cores")
    print("[9] Disable C-State for a range of cores")
    print("")
    print("[10] Display Uncore Information")
    print("[11] Set Uncore Maximum for a range of cores")
    print("[12] Set Uncore Minimum for a range of cores")
    print("")
    print("[13] Enable Turbo")
    print("[14] Disable Turbo")
    print("")
    print("[h] Show Help Text")
    print("[q] Exit Script")
    print("----------------------------------------------------------")
    text = raw_input("Option: ")

    # ("[1] Display Available Settings")
    if (text == "1"):
        getinfo()
    # ("[2] Display Current Settings")
    elif (text == "2"):
        listinfo(cpurange)
    # ("[3] Display Available P-States")
    elif (text == "3"):
        show_pstates()
    # print("[4] Set P-State governor for a range of cores")
    elif (text == "4"):
        governor = input_governor()
        if (governor == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_governor(governor, cpurange)
    # ("[5] Set Maximum P-State for a range of cores")
    elif (text == "5"):
        freqs = show_pstates()
        pstate = raw_input("Input P-State: ")
        print(freqs)
        if (int(pstate) not in freqs):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_max_cpu_freq(str(int(pstate)*1000), cpurange)
    # ("[6] Set Minimum P-State for a range of cores")
    elif (text == "6"):
        freqs = show_pstates()
        pstate = raw_input("Input P-State: ")
        print(freqs)
        if (int(pstate) not in freqs):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_min_cpu_freq(str(int(pstate)*1000), cpurange)

    # ("[7] Display Available C-States")
    elif (text == "7"):
        show_cstates()
    # ("[8] Enable C-State for a range of cores")
    elif (text == "8"):
        cstate = input_cstate()
        if (cstate == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_cstate(cstate, 0, cpurange)
    # ("[9] Disable C-State for a range of cores")
    elif (text == "9"):
        cstate = input_cstate()
        if (cstate == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_cstate(cstate, 1, cpurange)
    # ("[10] Set Uncore Maximum for a range of cores")
    elif text == "10":
        uncore_info()
        freqs = show_uncore_freqs()
    # ("[11] Set Uncore Maximum for a range of cores")
    elif text == "11":
        freqs = show_uncore_freqs()
        unfreq = raw_input("Input UncoreFreq: ")
        try:
            set_uncore_freq(max_freq=int(unfreq))
        except ValueError as err:
            print(err)
    # ("[12] Set Uncore Minimum for a range of cores")
    elif text == "12":
        freqs = show_uncore_freqs()
        unfreq = raw_input("Input UncoreFreq: ")
        try:
            set_uncore_freq(min_freq=int(unfreq))
        except ValueError as err:
            print(err)
    # ("[13] Enable the turbo")
    elif text == "13":
        print("Enabling Turbo")
        set_turbo(0)
    # ("[14] Disable the turbo")
    elif text == "14":
        print("Disabling Turbo")
        set_turbo(1)
    # ("[h] Show Help Text")
    elif (text == "h"):
        show_help()
    # ("[q] Exit Script")
    elif (text == "q"):
        sys.exit(0)
    else:
        print("")
        print("Unknown Option")

def main():
    global driver

    driver = "unknown"
    if (check_driver() == 0):
        print("Invalid Driver : [" + driver + "]")
        sys.exit(1)

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hilM:m:r:s:g:e:d:U:u:TtL:f", [
                               "maxfreq=", "minfreq=", "range="])
    except getopt.GetoptError:
        show_help()
        sys.exit(-1)

    cpucount = getcpucount()
    cpurange = range_expand('0-' + str(cpucount-1))

    if (len(opts) == 0):
        while(1):
            do_menu(cpurange)
            print("")
            raw_input("Press enter to continue ... ")
            print("")

    for opt, arg in opts:
        if opt in ("-r", "--range"):
            cpurange = range_expand(arg)
            print("Working with cores: " + str(cpurange))

    l_flag = 0
    u_flag = 0

    for opt, arg in opts:
        if opt == '-l':
            l_flag = 1
        if opt == '-f':
            u_flag = 1

    for opt, arg in opts:
        if opt == '-h':
            show_help()
            sys.exit()
        if opt == '-i':
            getinfo()
            sys.exit()
        if opt in ("-L"):
            if not l_flag and not u_flag:
                print("ERROR: Need to specify -l or -f when using interval mode.")
                sys.exit()
            list_interval = int(arg)
            print("Using list interval of " + str(list_interval) + " seconds.")
            while(1):
                if l_flag:
                    listinfo(cpurange)
                if u_flag:
                    uncore_info()
                time.sleep(list_interval)

    for opt, arg in opts:
        if opt == '-l':
            listinfo(cpurange)
            l_flag = 1
        if opt == '-f':
            uncore_info()
            u_flag = 1

    if l_flag or u_flag:
        sys.exit()

    for opt, arg in opts:
        if opt in ("-M", "--maxfreq"):
            setfreq = None
            if arg.lower() == "max":
                setfreq = max(get_pstates()) * 1000
            elif arg.lower() == "min":
                setfreq = min(get_pstates()) * 1000
            elif arg.lower() == "base":
                setfreq = get_cpu_base_frequency(0) * 1000
            else:
                setfreq = int(arg) * 1000
            print(f"Setting maxfreq to: {setfreq}")
            set_max_cpu_freq(setfreq, cpurange)
        if opt in ("-m", "--minfreq"):
            setfreq = None
            if arg.lower() == "max":
                setfreq = max(get_pstates()) * 1000
            elif arg.lower() == "min":
                setfreq = min(get_pstates()) * 1000
            elif arg.lower() == "base":
                setfreq = get_cpu_base_frequency(0) * 1000
            else:
                setfreq = int(arg) * 1000
            print(f"Setting minfreq to: {setfreq}")
            set_min_cpu_freq(setfreq, cpurange)
        if opt in ("-g", "--governor"):
            set_governor(arg, cpurange)
        if opt in ("-e", "--enable"):
            set_cstate(arg, 0, cpurange)
        if opt in ("-d", "--disable"):
            set_cstate(arg, 1, cpurange)
        if opt in ("-U", "--maxUncore"):
            try:
                set_uncore_freq(max_freq=int(arg))
            except ValueError as err:
                print(err)
        if opt in ("-u", "--minUncore"):
            try:
                set_uncore_freq(min_freq=int(arg))
            except ValueError as err:
                print(err)
        if opt in "-T":
            print("Enabling Turbo")
            set_turbo(0)
        if opt in "-t":
            print("Disabling Turbo")
            set_turbo(1)
    for opt, arg in opts:
        if opt in ("-s", "--setfreq"):

            drvFile = open(DRV_FILE, 'r')
            driver = drvFile.readline().strip("\n")
            drvFile.close()
            if driver == "acpi-cpufreq":
                setfreq = int(arg) * 1000
                set_cpu_freq(setfreq, cpurange)
            else:
                print()
                print("Error: setspeed not supported without acpi-cpufreq driver.")
                print("       Please add 'intel_pstate=disable' to kernel boot")
                print("       parameters, or use maxfreq and minfreq together.")
                print()

if __name__ == "__main__":
    main()
