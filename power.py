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
TURBO_PATH = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPU_PATH = "/sys/devices/system/cpu/"
TOPO_PKG = "topology/physical_package_id"
PKG0_DIE0_PATH = "package_00_die_00"
MSR_UNCORE_RATIO_LIMIT = 0x620
UNCORE_HW_MAX = 2400
UNCORE_HW_MIN = 800
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
        if int(getfileval(TURBO_PATH)) == 0:
            print(": Enabled")
        else:
            print(": Disabled")
    elif freq_P0 > freq_P1:
        print("    Turbo Available: Yes (any pstate above '" +
              str(freq_P1) + "')", end='')
        if int(getfileval(TURBO_PATH)) == 0:
            print(": Enabled")
        else:
            print(": Disabled")
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


def show_uncore_freqs():
    """ Show available uncore freqs from sysfs/MSR."""
    try:
        init_min_path = os.path.join(UNCORE_PATH, PKG0_DIE0_PATH,
                                     UNCORE_INIT_MIN)
        init_max_path = os.path.join(UNCORE_PATH, PKG0_DIE0_PATH,
                                     UNCORE_INIT_MAX)
        min = int(getfileval(init_min_path)) // 1000
        max = int(getfileval(init_max_path)) // 1000
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


def listinfo():
    cpucount = getcpucount()
    try:
        cstates = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle")
    except OSError:
        cstates = ""
    print("")
    print("==== ================================", end='')
    print(" ", end='')
    for x in cstates:
        print("=======", end='')
    print("==", end='')
    print(" ================", end='')
    print("")

    print("                         P-STATE INFO", end='')
    if cstates != "":
        print("      C-STATES DISABLED?", end='')
    print("      UNCORE INFO ", end='')
    print("")

    print("Core    Max    Min    Now    Governor", end='')
    cstates = sorted(cstates)
    for x in cstates:
        name = getfileval(
            "/sys/devices/system/cpu/cpu0/cpuidle/" + x + "/name")
        print(" % 7s" % (name,), end='')
    print("     Max      Min", end='')
    print("")

    print("==== ====== ====== ====== ===========", end='')
    for x in cstates:
        print(" =======", end='')
    print(" ======= ========", end='')
    print("")

    for x in range(0, cpucount):
        try:
            cpu = getPkgId(x)
            pkg_die_path = f"package_*{cpu}_die_*/"
            path = os.path.join(UNCORE_PATH, pkg_die_path)
            pkg_n_die_p = glob.glob(path)

            if not pkg_n_die_p:
                raise IOError("no sysfs entry for uncore_freq control")
            min_path = os.path.join(pkg_n_die_p[0], UNCORE_MIN)
            max_path = os.path.join(pkg_n_die_p[0], UNCORE_MAX)

            uncore_min = int(getfileval(min_path)) // 1000
            uncore_max = int(getfileval(max_path)) // 1000
        except (IOError, OSError):
            uncore_min, uncore_max = get_min_max_uncore_freq_msr(x)
        max = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_max_freq")
        min = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_min_freq")
        cur = getfileval("/sys/devices/system/cpu/cpu" +
                         str(x) + "/cpufreq/scaling_cur_freq")
        max = int(max) // 1000
        min = int(min) // 1000
        cur = int(cur) // 1000
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
        print(f" {uncore_max:>7} {uncore_min:>8}", end='')
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


def set_uncore_max_msr(uncore_freq, cpurange):
    """Set user passed uncore frequency as max freq using MSR."""
    for core_id in cpurange:
        try:
            # Read all msr data as to not overwrite other MSR data on write
            read_regstr = rdmsr(core_id, MSR_UNCORE_RATIO_LIMIT)
            data = struct.unpack('BBBBBBBB', read_regstr)

            # Update uncore desired max using bytes 0.
            write_regstr = struct.pack('BBBBBBBB',
                                       uncore_freq // 100,
                                       data[1], data[2], data[3],
                                       data[4], data[5], data[6],
                                       data[7])
            wrmsr(core_id, MSR_UNCORE_RATIO_LIMIT, write_regstr)
        except (IOError, OSError) as err:
            print(f"{err}:Could not set max uncore on core {core_id}")


def set_uncore_max_sysfs(uncore_freq, cpurange):
    """Set user passed uncore frequency as max freq using sysfs."""
    for core_id in cpurange:
        try:
            pkg = getPkgId(core_id)
            pkg_n_die_p = get_sysfs_die_path(pkg)
            max_path = os.path.join(pkg_n_die_p, UNCORE_MAX)
            print(f"Writing {uncore_freq} to {max_path}")
            writetofile(str(uncore_freq * 1000), max_path)
        except (IOError, OSError) as err:
            raise IOError(f"{err}:Try setting using MSR on core {core_id}")


def set_uncore_min_msr(uncore_freq, cpurange):
    """Set user passed uncore frequency as min freq using MSR."""
    for core_id in cpurange:
        try:
            # Read all msr data as to not overwrite other MSR data on write
            read_regstr = rdmsr(core_id, MSR_UNCORE_RATIO_LIMIT)
            data = struct.unpack('BBBBBBBB', read_regstr)

            # Update uncore desired min in byte 1.
            write_regstr = struct.pack('BBBBBBBB',
                                       data[0],
                                       uncore_freq // 100,
                                       data[2], data[3],
                                       data[4], data[5], data[6],
                                       data[7])
            wrmsr(core_id, MSR_UNCORE_RATIO_LIMIT, write_regstr)
        except (IOError, OSError) as err:
            print(f"{err}:Could not set min uncore on core {core_id}")


def set_uncore_min_sysfs(uncore_freq, cpurange):
    """Set user passed uncore frequency as min freq using sysfs."""
    for core_id in cpurange:
        try:
            pkg = getPkgId(core_id)
            pkg_n_die_p = get_sysfs_die_path(pkg)
            min_path = os.path.join(pkg_n_die_p, UNCORE_MIN)
            print(f"Writing {uncore_freq} to {min_path}")
            writetofile(str(uncore_freq * 1000), min_path)
        except (IOError, OSError) as err:
            raise IOError(f"{err}: Try setting using MSR on core {core_id}")


def validate_uncore_freq(package, uncore_freq):
    try:
        pkg_n_die_p = get_sysfs_die_path(package)
        init_min_path = os.path.join(pkg_n_die_p, UNCORE_INIT_MIN)
        init_max_path = os.path.join(pkg_n_die_p, UNCORE_INIT_MAX)
        min_freq = int(getfileval(init_min_path)) // 1000
        max_freq = int(getfileval(init_max_path)) // 1000
    except (IOError, OSError, ValueError):
        min_freq = UNCORE_HW_MIN
        max_freq = UNCORE_HW_MAX

    sup_uncore_freqs = list(range(min_freq, max_freq+100, 100))
    if uncore_freq not in sup_uncore_freqs:
        raise ValueError(f"Invalid uncore freq {uncore_freq}, "
                         f"should be between {min_freq}Mhz-{max_freq}Mhz")


def set_uncore_freq(cpurange, min_freq=None, max_freq=None):
    pkgs = set(getPkgId(c) for c in cpurange)  # get all packages in cpu range
    freqs = list(filter(None, (min_freq, max_freq)))  # get list of valid freqs

    for p in pkgs:
        for f in freqs:
            validate_uncore_freq(p, f)

    # all freqs are validated now, can just set them
    if min_freq:
        try:
            set_uncore_min_sysfs(min_freq, cpurange)
        except (IOError, OSError):
            set_uncore_min_msr(min_freq, cpurange)
    if max_freq:
        try:
            set_uncore_max_sysfs(max_freq, cpurange)
        except (IOError, OSError):
            set_uncore_max_msr(max_freq, cpurange)


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
    print('   -l            List information on each core')
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


def do_menu():
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
    print("[10] Display Available Uncore Freqs")
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
        listinfo()
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
        freqs = show_uncore_freqs()
    # ("[11] Set Uncore Maximum for a range of cores")
    elif text == "11":
        freqs = show_uncore_freqs()
        unfreq = raw_input("Input UncoreFreq: ")
        # Uncore is changed for all cores
        cpucount = getcpucount()
        cpurange = range_expand('0-' + str(cpucount-1))
        try:
            set_uncore_freq(cpurange, max_freq=int(unfreq))
        except ValueError as err:
            print(err)
    # ("[12] Set Uncore Minimum for a range of cores")
    elif text == "12":
        freqs = show_uncore_freqs()
        unfreq = raw_input("Input UncoreFreq: ")
        # Uncore is changed for all cores
        cpucount = getcpucount()
        cpurange = range_expand('0-' + str(cpucount-1))
        try:
            set_uncore_freq(cpurange, min_freq=int(unfreq))
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


if (check_driver() == 0):
    print("Invalid Driver : [" + driver + "]")
    sys.exit(1)

try:
    opts, args = getopt.getopt(sys.argv[1:], "hilM:m:r:s:g:e:d:U:u:Tt", [
                               "maxfreq=", "minfreq=", "range="])
except getopt.GetoptError:
    print('d.py -x <maxfreq>')
    sys.exit(-1)

cpucount = getcpucount()
cpurange = range_expand('0-' + str(cpucount-1))

scriptname = sys.argv[0]

if (len(opts) == 0):
    while(1):
        do_menu()
        print("")
        raw_input("Press enter to continue ... ")
        print("")


for opt, arg in opts:
    if opt == '-h':
        show_help()
        sys.exit()
    if opt == '-i':
        getinfo()
        sys.exit()
    if opt == '-l':
        listinfo()
        sys.exit()
    if opt in ("-r", "--range"):
        cpurange = range_expand(arg)
        print("Working with cores: " + str(cpurange))

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
        # Uncore is changed for all cores
        cpucount = getcpucount()
        cpurange = range_expand('0-' + str(cpucount-1))
        try:
            set_uncore_freq(cpurange, max_freq=int(arg))
        except ValueError as err:
            print(err)
    if opt in ("-u", "--minUncore"):
        # Uncore is changed for all cores
        cpucount = getcpucount()
        cpurange = range_expand('0-' + str(cpucount-1))
        try:
            set_uncore_freq(cpurange, min_freq=int(arg))
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
