#!/usr/bin/env python
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2019 Intel Corporation

"""
Simple /proc/cpuinfo parser
"""

__INFOS = []  # type: List[ParsedInfo]


class ParsedInfo(object):
    """
    Simple wrapper around parsed /proc/cpuinfo
    """
    def __init__(self, lines):
        self.flags = None           # CPU flags reported by cpuinfo

        self.__parse_funcs = {
            "flags": self.__parse_flags
        }

        # parse our line
        for line in lines:
            self.__parse_line(line)

    def __parse_flags(self, val):
        self.flags = val.split()

    def __parse_line(self, line):
        key, val = [s.strip() for s in line.split(":")]

        func = self.__parse_funcs.setdefault(key, None)
        if func:
            func(val)


def __read_cpuinfo():  # type: List[ParsedInfo]
    info_list = []
    with open("/proc/cpuinfo") as cpuinfo_f:
        info_lines = []
        for line in cpuinfo_f.readlines():
            if not line.strip():
                info_list += [ParsedInfo(info_lines)]
                info_lines = []  # reset current buffer
            # don't add empty lines
            line = line.strip()
            if line:
                info_lines += [line]
        # we may have stopped early
        if info_lines:
            info_list += [ParsedInfo(info_lines)]
    return info_list


def get_info_list():  # type: List[ParsedInfo]
    """
    Parse /proc/cpuinfo into a list of per-core ParsedInfo objects
    """
    global __INFOS
    if not __INFOS:
        __INFOS = __read_cpuinfo()
    return __INFOS
