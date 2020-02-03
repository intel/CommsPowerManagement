#!/usr/bin/python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019-20 Intel Corporation
"""Power Management configuration script"""

from __future__ import print_function
import os
import sys
import getopt
import re
import struct

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
pstateList = []
freqs = []
stateList = []
govList = []
scriptname = "power.py"
driver = ""
freq_P0 = 0
freq_P1 = 0
freq_P1n = 0

# Read a 64-byte value from an MSR through the sysfs interface.
# Returns an 8-byte binary packed string.


def rdmsr(core, msr):
    msr_filename = "/dev/cpu/" + str(core) + "/msr"
    msr_file = os.open(msr_filename, os.O_RDONLY)
    os.lseek(msr_file, msr, os.SEEK_SET)
    regstr = os.read(msr_file, 8)
    return regstr


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
    except:
        print()
        print("ERROR: No pstate driver file found.")
        print("       Are P-States enabled in the system BIOS?")
        print()
        return 0
    driver = drvFile.readline().strip("\n")
    drvFile.close()
    if driver == "acpi-cpufreq":
        return 1
    elif driver == "intel_pstate":
        try:
            open(MSR_FILE, "r")
        except IOError:
            print("ERROR: Need the 'msr' kernel module")
            print("Please run 'modprobe msr'")
            sys.exit(1)
        print()

        print("WARNING: Current pstate driver is '" + driver + "'")
        print("         Some options may be unavailable.")
        print()
        # get the P1 frequency
        freq_P1 = get_cpu_base_frequency(11)
        print("CPU Base Frequency (P1): " + str(freq_P1) + "MHz")
        return 1
    else:
        print()
        print("WARNING: Current pstate driver is '" + driver + "'")
        print("         Some options may be unavailable.")
        print()
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
              str(freq_list[0]) + "')")
    elif freq_P0 > freq_P1:
        print("    Turbo Available: Yes (any pstate above '" + str(freq_P1) + "')")
    else:
        print("    Turbo Available: No")
    return freq_list


def get_cstates():
    stateList = []
    try:
        states = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle/")
    except:
        states = ""
    stateList = ""
    for state in states:
        stateFileName = "/sys/devices/system/cpu/cpu0/cpuidle/" + state + "/name"
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


def getfileval(stateFileName):
    stateFile = open(stateFileName, 'r')
    statename = stateFile.readline().strip("\n")
    return statename


def listinfo():
    cpucount = getcpucount()
    try:
        cstates = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle")
    except:
        cstates = ""
    print("")
    print("==== ====== ====== ====== ===========", end='')
    for x in cstates:
        print(" =======", end='')
    print("")
    print("              P-STATE INFO              ", end='')
    if cstates != "":
        print("     C-STATES DISABLED?")
    else:
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
    for x in range(0, cpucount):
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
        print("%s" % str(x).rjust(4), " %s" % str(max).rjust(5), " %s" % str(min).rjust(5), " %s" % str(cur).rjust(5), "% 11s" % gov, end='')
        for y in cstates:
            value = getfileval("/sys/devices/system/cpu/cpu" +
                               str(x) + "/cpuidle/" + y + "/disable")
            if int(value) > 0:
                print(" % 7s" % ("YES",), end='')
            else:
                print(" % 7s" % ("no",), end='')
        print("")
    print("")


def getcpucount():
    cpus = os.listdir("/sys/devices/system/cpu")
    regex = re.compile(r'cpu[0-9]')
    cpus = list(filter(regex.search, cpus))
    cpucount = len(cpus)
    return cpucount


def set_max_cpu_freq(maxfreq, cpurange):
    for x in cpurange:
        maxName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_max_freq"
        print("Writing " + str(maxfreq) + " to " + maxName)
        maxFile = open(maxName, 'w')
        maxFile.write(str(maxfreq))
        maxFile.close()


def set_min_cpu_freq(minfreq, cpurange):
    for x in cpurange:
        minName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_min_freq"
        print("Writing " + str(minfreq) + " to " + minName)
        minFile = open(minName, 'w')
        minFile.write(str(minfreq))
        minFile.close()


def set_cpu_freq(setfreq, cpurange):
    for x in cpurange:
        setName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_setspeed"
        print("Writing " + str(setfreq) + " to " + setName)
        minFile = open(setName, 'r')
        current = minFile.readline().strip("\n")
        minFile.close()
        if current == "<unsupported>":
            print("Error, cannot set frequency for core " +
                  str(x) + " " + current + " Need '-g userspace'")
        else:
            minFile = open(setName, 'w')
            minFile.write(str(setfreq))
            minFile.close()


def set_governor(gov, cpurange):
    for x in cpurange:
        govName = "/sys/devices/system/cpu/cpu" + \
            str(x) + "/cpufreq/scaling_governor"
        print("Writing '" + str(gov) + "' to " + govName)
        govFile = open(govName, 'w')
        govFile.write(str(gov))
        govFile.close()


def set_cstate(cstate, enable, cpurange):

    # Get list of cstate dirs to iterate through to find the cstate name
    cstates = os.listdir("/sys/devices/system/cpu/cpu0/cpuidle")

    for x in cpurange:
        for y in cstates:
            name = getfileval(
                "/sys/devices/system/cpu/cpu0/cpuidle/" + y + "/name")
            if (name == cstate):
                stateName = "/sys/devices/system/cpu/cpu" + \
                    str(x) + "/cpuidle/" + str(y) + "/disable"
                print("Writing '" + str(enable) + "' to " + stateName)
                stateFile = open(stateName, 'w')
                stateFile.write(str(enable))
                stateFile.close()


def range_expand(s):
    r = []
    for i in s.split(','):
        if '-' not in i:
            r.append(int(i))
        else:
            l, h = map(int, i.split('-'))
            r += range(l, h+1)
    return r


def show_help():
    print("")
    print(scriptname + ' -i -M <maxfreq> -m <minfreq> -s <setfreq> -r <range> -g <governor>')
    print('   <no params>   use interactive menu')
    print('   -h            Show this help')
    print('   -i            Show information on available freqs, C-States, etc')
    print('   -l            List information on each core')
    print('   -M <freq>     Set core maximum frequency')
    print('   -m <freq>     Set core minimum frequency')
    print('   -s <freq>     Set core frequency (within min and max)')
    print('   -r <range>    Range of cores to affect, e.g. 1-3,5,7')
    print('   -g <governor> Set core governor (usually \'userspace\')')
    print('   -e <cstate>   Enable core C-State ')
    print('   -d <cstate>   Disable core C-State ')
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
    print('   ' + scriptname + ' -g ondemand -r 2,4 -M 2501, -s 2501')
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
    print("[h] Show Help Text")
    print("[q] Exit Script")
    print("----------------------------------------------------------")
    text = raw_input("Option: ")

    #("[1] Display Available Settings")
    if (text == "1"):
        getinfo()
    #("[2] Display Current Settings")
    elif (text == "2"):
        listinfo()
    #("[3] Display Available P-States")
    elif (text == "3"):
        show_pstates()
    #print("[4] Set P-State governor for a range of cores")
    elif (text == "4"):
        governor = input_governor()
        if (governor == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_governor(governor, cpurange)
    #("[5] Set Maximum P-State for a range of cores")
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
    #("[6] Set Minimum P-State for a range of cores")
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

    #("[7] Display Available C-States")
    elif (text == "7"):
        show_cstates()
    #("[8] Enable C-State for a range of cores")
    elif (text == "8"):
        cstate = input_cstate()
        if (cstate == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_cstate(cstate, 0, cpurange)
    #("[9] Disable C-State for a range of cores")
    elif (text == "9"):
        cstate = input_cstate()
        if (cstate == ""):
            print("Invalid Selection")
            return
        cores = raw_input("Input Range of Cores: ")
        cpurange = range_expand(cores)
        print("Working with cores: " + str(cpurange))
        set_cstate(cstate, 1, cpurange)
    #("[h] Show Help Text")
    elif (text == "h"):
        show_help()
    #("[q] Exit Script")
    elif (text == "q"):
        sys.exit(0)
    else:
        print("")
        print("Unknown Option")


if (check_driver() == 0):
    print("Invalid Driver : [" + driver + "]")
    sys.exit(1)

try:
    opts, args = getopt.getopt(sys.argv[1:], "hilM:m:r:s:g:e:d:", [
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
        setfreq = int(arg) * 1000
        set_max_cpu_freq(setfreq, cpurange)
    if opt in ("-m", "--minfreq"):
        setfreq = int(arg) * 1000
        set_min_cpu_freq(setfreq, cpurange)
    if opt in ("-g", "--governor"):
        set_governor(arg, cpurange)
    if opt in ("-e", "--enable"):
        set_cstate(arg, 0, cpurange)
    if opt in ("-d", "--disable"):
        set_cstate(arg, 1, cpurange)


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
            print("Error: setspeed not supported without acpi-cpufreq driver. Please")
            print("       add 'intel_pstate=disable' to kernel boot parameters,")
            print("       or use maxfreq and minfreq together.")
            print()
