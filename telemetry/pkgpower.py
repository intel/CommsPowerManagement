#!/usr/bin/python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2020 Intel Corporation
"""Read package current power, package TDP(max power)"""

import os
import time
import re
import glob
import collectd

BASE_POWERCAP_PATH = "/sys/devices/virtual/powercap/intel-rapl"
SYSFS_NODE_BASE = "/sys/bus/node/devices"
MICRO_CONV = 1000000.0
SIXTY_SEC = 60

# Python 2 doesn't have monotonic
try:
    time.monotonic
except AttributeError:
    time.monotonic = time.time

class _CpuPowerStatus:
    '''
    The _CpuPowerStatus object maintains per package id
    and package maximum power and TDP along with some house keeping
    data
    '''
    def __init__(self, node_id):
        self.node_id = node_id
        self.prev_cons_ts = 0
        self.prev_cons_val = 0
        self.power_cons_max = 0
        self.tdp = 0
        self.name = ""

__CPUS = []

def _read_sysfs(filename):
    """
    Read desired value from sysfs file
    """
    with open(filename) as sysfs:
        value = sysfs.readline().strip("\n")
    return value

def _get_max_power_consumption(cpu):
    """ Get the max power consumption of CPU """
    powercap_cpu_base = os.path.join(
        BASE_POWERCAP_PATH, "intel-rapl:{}".format(cpu.node_id))
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
    cpu.power_cons_max = cons_max

def _get_tdp_power(cpu):
    """ Get the TDP limit of package"""
    powercap_cpu_base = os.path.join(
        BASE_POWERCAP_PATH, "intel-rapl:{}".format(cpu.node_id))
    try:
        path = os.path.join(powercap_cpu_base, "constraint_0_max_power_uw")
        tdp = int(_read_sysfs(path))
        #uW to W
        tdp /= MICRO_CONV
    except (IOError, OSError) as err:
        raise IOError(
            "{}\nCould not read TDP".format(err))
    except ValueError as err:
        raise ValueError(
            "{}\nCould not parse TDP value".format(err))
    cpu.tdp = tdp

def _get_pkg_name(cpu):
    """ Get the package name """
    powercap_cpu_base = os.path.join(
        BASE_POWERCAP_PATH, "intel-rapl:{}".format(cpu.node_id))
    try:
        path = os.path.join(powercap_cpu_base, "name")
    except (IOError, OSError) as err:
        raise IOError(
            "{}\nCould not read name".format(err))
    cpu.name = _read_sysfs(path)

def _get_power_consumption_sysfs(cpu):
    powercap_cpu_base = os.path.join(
        BASE_POWERCAP_PATH, "intel-rapl:{}".format(cpu.node_id))
    path = os.path.join(powercap_cpu_base, "energy_uj")
    cons = int(_read_sysfs(path))
    return cons

def _get_node_id(nodepath):
    reg_ex = re.compile(r"node(?P<node>\d+)")
    # function to extract node ID from full node path
    # get basename, e.g. "node0"
    nodepath = os.path.basename(nodepath)
    # find node ID with regex
    match_nodepath = reg_ex.match(nodepath)
    return int(match_nodepath.group("node"))

def config_func(_unused_config):
    '''
    call back function called by collectd, here
    we initialize __CPUS list
    '''
    global __CPUS
    # initialize the list first time we request data
    glob_path = os.path.join(SYSFS_NODE_BASE, "*")
    nodes = glob.glob(glob_path)
    node_ids = [_get_node_id(np) for np in nodes]
    for node in node_ids:
        cpu = _CpuPowerStatus(node)
        _get_max_power_consumption(cpu)
        _get_tdp_power(cpu)
        _get_pkg_name(cpu)
        __CPUS += [cpu]

def _read_pkg_power(cpu):
    # first, read current power consumption value and timestamp
    cur_ts = time.monotonic()
    cur_cons = _get_power_consumption_sysfs(cpu)
    # uJ to J
    cur_cons /= MICRO_CONV

    # do we have a previous timestamp?
    prev_ts = cpu.prev_cons_ts
    prev_cons = cpu.prev_cons_val
    # sanity checks if previous values exist

    if prev_ts:
        # timer wraps around about every 60 seconds on a loaded system, so reset the values
        # if it's been longer than 60 seconds since last read
        if cur_ts - prev_ts >= SIXTY_SEC:
            prev_ts = None
            prev_cons = None
        # in Python 2 we won't be using a monotonic clock so we're susceptible to timezone
        # changes, so also check for negative time
        elif cur_ts < prev_ts:
            prev_ts = None
            prev_cons = None

    # overwrite stored values to use them next time
    cpu.prev_cons_ts = cur_ts
    cpu.prev_cons_val = cur_cons

    # adjust previous value if the counter wrapped around
    if prev_cons > cur_cons:
        prev_cons -= cpu.power_cons_max

    diff_ts = cur_ts - prev_ts
    diff_cons = cur_cons - prev_cons

    # J / seconds gives us W
    res = diff_cons / diff_ts

    return res

def read_func():
    '''
    Callback function called by collectd on periodic basis.
    This function pushes the power data of all the packages
    on the system.
    '''
    #collectd power of all cpus
    for cpu in __CPUS:
        pkg_power = _read_pkg_power(cpu)
        # Dispatch value to collectd
        val = collectd.Values(type='power')
        val.plugin = cpu.name + '-power'
        val.dispatch(values=[pkg_power])
        #Dispatch TDP value
        val = collectd.Values(type='power')
        val.plugin = cpu.name + '-TDP-power'
        val.dispatch(values=[cpu.tdp])

collectd.register_config(config_func)
collectd.register_read(read_func)
