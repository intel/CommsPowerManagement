#!/usr/bin/python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019 Intel Corporation
"""SST-BF enable/disable"""

from __future__ import print_function
import os
import sys
import time
import re
import struct
import argparse
import subprocess
import textwrap

# raw_input() is only available in python 2.
try:
    raw_input
except NameError:
    raw_input = input

DRV_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"
BASE_FILE = "/sys/devices/system/cpu/cpu%d/cpufreq/base_frequency"
CPU_MAX_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
CPU_MIN_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq"
MAX_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
MIN_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq"
MSR_FILE = "/dev/cpu/0/msr"

CPU_COUNT = 0
SCRIPT_VERSION = "1.2j"

# Read a 64-byte value from an MSR through the sysfs interface.
# Returns an 8-byte binary packed string.
def __rdmsr(core, msr):
    try:
        msr_filename = os.path.join("/dev/cpu", str(core), "msr")
        with open(msr_filename, "rb") as msr_file:
            msr_file.seek(msr, os.SEEK_SET)
            regstr = msr_file.read(8)
        return regstr
    except:
        print("Could not read from MSR 0x%x on core %i" % (msr, core))
        raise

# Writes a 64-byte value to an MSR through the sysfs interface.
# Expects an 8-byte binary packed string in regstr.
def __wrmsr(core, msr, regstr):
    try:
        msr_filename = os.path.join("/dev/cpu", str(core), "msr")
        with open(msr_filename, "wb") as msr_file:
            msr_file.seek(msr)
            msr_file.write(regstr)
    except IOError:
        print("Could not write to MSR 0x%x on core %i" % (msr, core))
        raise

# Read the HWP_ENABLED MSR
def get_hwp_enabled():
    """Read the HWP_ENABLED MSR."""
    # rdmsr returns 8 bytes of packed binary data
    regstr = __rdmsr(0, 0x770)
    # Unpack the 8 bytes into array of unsigned chars
    msr_bytes = struct.unpack('BBBBBBBB', regstr)
    enabled = msr_bytes[0]
    return enabled

# Read the TURBO_MODE_ENABLED from package
def get_turbo_disabled():
    """Read if the Package TURBO is  disabled"""
    # rdmsr returns 8 bytes of packed binary data
    regstr = __rdmsr(0, 0x1A0)
    # Unpack the 8 bytes into array of unsigned chars
    msr_bytes = struct.unpack('BBBBBBBB', regstr)
    disabled = msr_bytes[4] & 0x40
    return disabled

# Get the CPU base frequencey from the PLATFORM_INFO MSR
def get_cpu_base_frequency():
    """Get the CPU base frequencey from the PLATFORM_INFO MSR."""
    regstr = __rdmsr(0, 0xCE) # MSR_PLATFORM_INFO
    # Unpack the 8 bytes into array of unsigned chars
    msr_bytes = struct.unpack('BBBBBBBB', regstr)
    # Byte 1 contains the max non-turbo frequecy
    freq_p1 = msr_bytes[1]*100
    return freq_p1

# Set package UNCORE frequency
def __set_uncore(freq):
    freq = int(freq)/100
    regstr = struct.pack('BBBBBBBB', freq, freq, 0, 0, 0, 0, 0, 0)
    __wrmsr(0, 0x620, regstr)
    __wrmsr(CPU_COUNT-1, 0x620, regstr)
    time.sleep(0.1)

# get package UNCORE frequency
def __get_uncore():
    regstr = __rdmsr(0, 0x621)
    msr_bytes = struct.unpack('BBBBBBBB', regstr)
    return int(msr_bytes[0]*100)

# Get the CPU max frequency
def get_cpu_max_frequency(core):
    """ Get the CPU max frequency"""
    max_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/cpuinfo_max_freq"
    try:
        with open(max_filename, 'r') as max_file:
            maximum = int(max_file.readline().strip("\n"))
    except IOError:
        print("WARNING: cpuinfo_max_freq sysfs entry not found")
        maximum = 0
    return maximum

# Get the CPU min frequencey
def get_cpu_min_frequency(core):
    """ Get the CPU min frequency"""
    min_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/cpuinfo_min_freq"
    try:
        with open(min_filename, 'r') as min_file:
            minimum = int(min_file.readline().strip("\n"))
    except IOError:
        print("WARNING: cpuinfo_min_freq sysfs entry not found")
        minimum = 0
    return minimum
# Get the scaling max frequency
def get_scaling_max_frequency(core):
    """ Get the scaling max frequency"""
    max_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/scaling_max_freq"
    try:
        with open(max_filename, 'r') as max_file:
            maximum = int(max_file.readline().strip("\n"))
    except IOError:
        print("WARNING: scaling_max_freq sysfs entry not found")
        maximum = 0
    return maximum

# Get the scaling min frequencey
def get_scaling_min_frequency(core):
    """ Get the scaling min frequency"""
    min_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/scaling_min_freq"
    try:
        with open(min_filename, 'r') as min_file:
            minimum = int(min_file.readline().strip("\n"))
    except IOError:
        print("WARNING: scaling_min_freq sysfs entry not found")
        minimum = 0
    return minimum

# Get the SST-BF base frequencey
def get_sst_bf_frequency(core):
    """ Get the SST-BF frequency"""
    base_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/base_frequency"
    try:
        with open(base_filename, 'r') as base_file:
            base = int(base_file.readline().strip("\n"))/1000
    except IOError:
        print("WARNING: base_frequency sysfs entry not found")
        base = FREQ_P1
    return base

def get_issbf_cpu_freqs():
    """Get the SST-BF frequencies."""

    p1_high = 0
    p1_normal = 0
    for core in range(0, CPU_COUNT):
        base = get_sst_bf_frequency(core)
        if p1_high == 0:
            p1_high = base
        if p1_normal == 0:
            p1_normal = base
        if base > p1_high:
            p1_high = base
    return (p1_high, p1_normal)

# read CPUID to get CPU Name
def get_cpu_name():
    """Get the CPU name from the list of valid SST_BF CPUs"""

    valid_cpus = ["6252N", "6230N", "5218N"]

    pargs = ["cpuid", "-i", "-1"]
    try:
        output = subprocess.check_output(pargs).decode()
    except (subprocess.CalledProcessError, OSError):
        print("Failed to get CPU information: 'cpuid' package not installed.")
        return ""

    for line in output.splitlines():
        for name in valid_cpus:
            if name in line:
                return name

    return ""

def check_driver():
    """check the name of the P-STATE driver"""

    driver = "none"

    try:
        with open(DRV_FILE, 'r') as drv_file:
            driver = drv_file.readline().strip("\n")
    except IOError:
        print()
        print("ERROR: No pstate driver file found.")
        print("       Are P-States enabled in the system BIOS?")
        print()
        return 0

    if driver == "intel_pstate":
        return 1
    print("Invalid Driver : [" + driver + "]")
    return 0

# Set max core frequency
def set_max_cpu_freq(maxfreq, core):
    """Set the core's max cpu frequency."""
    max_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/scaling_max_freq"
    try:
        with open(max_filename, 'w') as max_file:
            max_file.write(str(maxfreq))
    except IOError:
        print("WARNING: cannot set core %s to %s" % (str(core), str(maxfreq)))


# Set min core frequency
def set_min_cpu_freq(minfreq, core):
    """Set the core's min cpu frequency."""
    min_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/scaling_min_freq"
    try:
        with open(min_filename, 'w') as min_file:
            min_file.write(str(minfreq))
    except IOError:
        print("WARNING: cannot set core %s to %s" % (str(core), str(minfreq)))


# Set core governor
def set_core_governor(governor, core):
    """Set the core's power governor"""
    min_filename = "/sys/devices/system/cpu/cpu" + str(core) + "/cpufreq/scaling_governor"
    try:
        with open(min_filename, 'w') as min_file:
            min_file.write(governor)
    except IOError:
        print("WARNING: cannot write to scaling_governor sysfs file")

def getcpu_count():
    """Get the number of cores in the system."""

    cpus = os.listdir("/sys/devices/system/cpu")
    regex = re.compile(r'cpu[0-9]')
    cpus = list(filter(regex.search, cpus))
    return len(cpus)


def set_sst_bf(mode):
    """Enable SST_BF mode"""

    print("CPU Count = " + str(CPU_COUNT))

    for core in range(0, CPU_COUNT):
        set_core_governor("powersave", core)
        set_max_cpu_freq(FREQ_P0*1000, core)
        base = get_sst_bf_frequency(core)

        if mode == 0:
            set_min_cpu_freq(base*1000, core)
            set_max_cpu_freq(base*1000, core)
        elif mode == 1:
            set_min_cpu_freq(FREQ_P1*1000, core)
            set_max_cpu_freq(FREQ_P1*1000, core)
        elif mode == 2:
            if base > FREQ_P1:
                set_min_cpu_freq(base*1000, core)
                set_max_cpu_freq(FREQ_P0*1000, core)
            else:
                set_min_cpu_freq(FREQ_P1N*1000, core)
                set_max_cpu_freq(base*1000, core)
        elif mode == 3:
            if base > FREQ_P1:
                set_min_cpu_freq(base*1000, core)
                set_max_cpu_freq(base*1000, core)
            else:
                set_min_cpu_freq(FREQ_P1N*1000, core)
                set_max_cpu_freq(FREQ_P0*1000, core)

    query_sst_bf()


def reverse_sst_bf():
    """Reverse SST-BF mode"""

    print("CPU Count = " + str(CPU_COUNT))

    for core in range(0, CPU_COUNT):
        maximum = get_cpu_max_frequency(core)
        set_max_cpu_freq(maximum, core)
        minimum = get_cpu_min_frequency(core)
        set_min_cpu_freq(minimum, core)

    query_sst_bf()

def reverse_sst_bf_to_p1():
    """"Reverse frequencies to non-turbo."""

    print("CPU Count = " + str(CPU_COUNT))

    freq_p1 = get_cpu_base_frequency()

    for core in range(0, CPU_COUNT):
        maximum = get_cpu_max_frequency(core)
        set_max_cpu_freq(maximum, core)
        minimum = get_cpu_min_frequency(core)
        set_min_cpu_freq(minimum, core)
        set_max_cpu_freq(freq_p1*1000, core)
    query_sst_bf()

def query_sst_bf():
    """"Show information on sst-bf frequencies."""

    print("Name = " + CPU_NAME)
    print("CPUs = " + str(CPU_COUNT))

    freq_p1 = get_cpu_base_frequency()
    print("Base = " + str(freq_p1))
    p1_high = 0

    print("     |------sysfs-------|")
    print("Core | base   max   min |")
    print("-----|------------------|")
    for core in range(0, CPU_COUNT):
        base = get_sst_bf_frequency(core)
        maximum = get_scaling_max_frequency(core)
        minimum = get_scaling_min_frequency(core)
        print(str(core).rjust(4) + " | " + \
            str(base).rjust(4) + "  " + \
            str(maximum/1000).rjust(4) + "  " + \
            str(minimum/1000).rjust(4) + " |")
        if base > freq_p1:
            p1_high = p1_high + 1

    print("-----|------------------|")
    print("We have " + str(p1_high) + " high priority cores according to sysfs base_frequency.")


def list_sst_bf_cores():
    """Short, comma-separated list of bf cores."""

    freq_p1 = get_cpu_base_frequency()
    cores = []

    for core in range(0, CPU_COUNT):
        base = get_sst_bf_frequency(core)
        if base > freq_p1:
            cores.append(core)
    print(*cores, sep=",")

    # Coremask may be bigger than 64-bit number, but Python 2 and 3 handle big numbers differently
    # Python 2 has 'long' type while Python 3 uses 'int'.
    try:
        coremask = long(0)
    except NameError:
        coremask = int(0)

    for core in cores:
        coremask = coremask + (2**core)
    print(hex(coremask).rstrip('L'))

def print_banner():
    """Print script banner."""
    print("----------------------------------------------------------")
    print("SST-BF SETUP SCRIPT v" + SCRIPT_VERSION)
    print("----------------------------------------------------------")

def __print_wrap(opt, text):
    wrapper = textwrap.TextWrapper()
    lines = wrapper.wrap(text)
    first = 1
    for line in lines:
        if first == 1:
            print("[%s] %s" % (opt, line))
            first = 0
        else:
            print("    %s" % line)

def __print_help():

    print("")
    print_banner()
    print("")
    __print_wrap('s', HELP_TEXT_S_LONG)
    __print_wrap('m', HELP_TEXT_M_LONG)
    __print_wrap('r', HELP_TEXT_R_LONG)
    __print_wrap('t', HELP_TEXT_T_LONG)
    __print_wrap('a', HELP_TEXT_A_LONG)
    __print_wrap('b', HELP_TEXT_B_LONG)
    print("[i] %s" % HELP_TEXT_I)
    print("[l] %s" % HELP_TEXT_L)
    print("[v] %s" % HELP_TEXT_V)
    print("[h] %s" % HELP_TEXT_H)
    print("    Run script with no arguments for interactive menu")
    print("    Run script with -h for help on the supported arguments")



def show_version():
    """print out the script version."""
    print(SCRIPT_VERSION)


def do_menu():
    """Show the main menu to the user."""

    print("")
    print_banner()
    print("")
    print("[s] %s" % HELP_TEXT_S)
    print("[m] %s" % HELP_TEXT_M)
    print("[r] %s" % HELP_TEXT_R)
    print("[t] %s" % HELP_TEXT_T)
    print("[a] %s" % HELP_TEXT_A)
    print("[b] %s" % HELP_TEXT_B)
    print("[i] %s" % HELP_TEXT_I)
    print("[l] %s" % HELP_TEXT_L)
    print("[v] %s" % HELP_TEXT_V)
    print("[h] %s" % HELP_TEXT_H)
    print("")
    print("[q] Exit Script")
    print("----------------------------------------------------------")
    text = raw_input("Option: ")

    if text == "s":
        set_sst_bf(0)
    elif text == "m":
        set_sst_bf(1)
    elif text == "r":
        reverse_sst_bf()
    elif text == "t":
        reverse_sst_bf_to_p1()
    elif text == "a":
        set_sst_bf(2)
    elif text == "b":
        set_sst_bf(3)
    elif text == "i":
        query_sst_bf()
    elif text == "l":
        list_sst_bf_cores()
    elif text == "v":
        show_version()
    elif text == "h":
        __print_help()
    elif text == "q":
        sys.exit(0)
    else:
        print("")
        print("Unknown Option")

#
# Do some prerequesite checks.
#
try:
    open(MSR_FILE, "r")
except IOError:
    print("ERROR: Need the 'msr' kernel module")
    print("Please run 'modprobe msr'")
    sys.exit(1)

if get_turbo_disabled() > 0:
    print("ERROR: Turbo Boost not enabled in BIOS. Exiting.")
    sys.exit(1)

if get_hwp_enabled() == 0:
    print("ERROR: HWP not enabled in BIOS. Exiting.")
    sys.exit(1)

if check_driver() == 0:
    sys.exit(1)

CPU_COUNT = getcpu_count()
CPU_NAME = get_cpu_name()
if CPU_NAME == "":
    print("Unknown CPU")
    sys.exit(-1)

FREQ_P1 = get_cpu_base_frequency()
BASE = get_sst_bf_frequency(0)
if BASE == FREQ_P1:
    print("base_frequency not available in %s" % BASE_FILE)
    sys.exit(-1)
FREQ_P0 = get_cpu_max_frequency(0) / 1000
FREQ_P1N = get_cpu_min_frequency(0) / 1000
(FREQ_P1_HIGH, FREQ_P1_NORMAL) = get_issbf_cpu_freqs()

SCRIPT_NAME = sys.argv[0]

# Set up the parser arguments, along with their help text. The help text
# contains the actual min/max/base frequencies from the local machine for
# extra clarity when using the script.
# The HELP_TEXT variables are also used later for the interactive menu.

PARSER = argparse.ArgumentParser(description="Configure SST-BF frequencies")

HELP_TEXT_S = "Set SST-BF config (set min/max to %s/%s and %s/%s)" % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P1_HIGH),
       str(FREQ_P1_NORMAL),
       str(FREQ_P1_NORMAL))
HELP_TEXT_S_LONG = "Set SST-BF config. Set high priority cores to %s" \
      " minimum and %s maximum, and set normal priority" \
      " cores to %s minimum and %s maximum." % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P1_HIGH),
       str(FREQ_P1_NORMAL),
       str(FREQ_P1_NORMAL))
PARSER.add_argument('-s', action="store_true", help=HELP_TEXT_S_LONG)

HELP_TEXT_M = "Set P1 on all cores (set min/max to %s/%s)" % \
      (str(FREQ_P1),
       str(FREQ_P1))
HELP_TEXT_M_LONG = "Set P1 on all cores. Set all cores to %s" \
      " minimum and %s maximum." % \
      (str(FREQ_P1),
       str(FREQ_P1))
PARSER.add_argument('-m', action="store_true", help=HELP_TEXT_M_LONG)

HELP_TEXT_R = "Revert cores to min/Turbo (set min/max to %s/%s)" % \
      (str(FREQ_P1N),
       str(FREQ_P0))
HELP_TEXT_R_LONG = "Revert cores to minimum/Turbo. Set all cores to %s" \
      " minimum and %s maximum." % \
      (str(FREQ_P1N),
       str(FREQ_P0))
PARSER.add_argument('-r', action="store_true", help=HELP_TEXT_R_LONG)

HELP_TEXT_T = "Revert cores to min/P1 (set min/max to %s/%s)" % \
      (str(FREQ_P1N),
       str(FREQ_P1))
HELP_TEXT_T_LONG = "Revert cores to minimum/P1. Set all cores to %s" \
      " minimum and %s maximum." % \
      (str(FREQ_P1N),
       str(FREQ_P1))
PARSER.add_argument('-t', action="store_true", help=HELP_TEXT_T_LONG)

HELP_TEXT_A = "Mixed config A (set min/max to %s/%s and %s/%s)" % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P0),
       str(FREQ_P1N),
       str(FREQ_P1_NORMAL))
HELP_TEXT_A_LONG = "Mixed config A. Set high priority cores to %s" \
      " minimum and %s maximum, and set normal priority" \
      " cores to %s minimum and %s maximum." % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P0),
       str(FREQ_P1N),
       str(FREQ_P1_NORMAL))
PARSER.add_argument('-a', action="store_true", help=HELP_TEXT_A_LONG)

HELP_TEXT_B = "Mixed config B (set min/max to %s/%s and %s/%s)" % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P1_HIGH),
       str(FREQ_P1N),
       str(FREQ_P0))
HELP_TEXT_B_LONG = "Mixed config B. Set high priority cores to %s" \
      " minimum and %s maximum, and set normal priority" \
      " cores to %s minimum and %s maximum." % \
      (str(FREQ_P1_HIGH),
       str(FREQ_P1_HIGH),
       str(FREQ_P1N),
       str(FREQ_P0))
PARSER.add_argument('-b', action="store_true", help=HELP_TEXT_B_LONG)

HELP_TEXT_I = "Show current SST-BF frequency information"
PARSER.add_argument('-i', action="store_true", help=HELP_TEXT_I)

HELP_TEXT_L = "List High Priority cores"
PARSER.add_argument('-l', action="store_true", help=HELP_TEXT_L)

HELP_TEXT_U = "Set UNCORE frequency, e.g. -u 1800 sets to 1.8GHz"
PARSER.add_argument('-u', type=int, help=HELP_TEXT_U)

HELP_TEXT_V = "Show script version"
PARSER.add_argument('-v', action="store_true", help=HELP_TEXT_V)

HELP_TEXT_H = "Print additional help on menu options"

ARGS = PARSER.parse_args()

if ARGS.s:
    set_sst_bf(0)
    sys.exit(0)
if ARGS.m:
    set_sst_bf(1)
    sys.exit(0)
if ARGS.r:
    reverse_sst_bf()
    sys.exit(0)
if ARGS.t:
    reverse_sst_bf_to_p1()
    sys.exit(0)
if ARGS.a:
    set_sst_bf(2)
    sys.exit(0)
if ARGS.b:
    set_sst_bf(3)
    sys.exit(0)
if ARGS.i:
    query_sst_bf()
    sys.exit(0)
if ARGS.l:
    list_sst_bf_cores()
    sys.exit(0)
if ARGS.u:
    __set_uncore(ARGS.u)
    UNCORE_FREQ = __get_uncore()
    print("Uncore frequency now running at %dMHz" % UNCORE_FREQ)
    sys.exit(0)
if ARGS.v:
    show_version()
    sys.exit(0)

while 1:
    do_menu()
    print("")
    raw_input("Press enter to continue ... ")
    print("")
