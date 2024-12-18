#!/usr/bin/python3
# Copyright(c) 2019-24 Intel Corporation
"""
Register read and write utility
"""

from __future__ import print_function
import argparse
import logging
import os
import sys


def setup_logging(enable_logging, logfile_name):
    """ Setup Logging """
    if enable_logging:
        logging.basicConfig(filename=logfile_name,
                            level=logging.DEBUG,
                            format='%(asctime)s %(levelname)s: %(message)s')
        log_or_print("Logging enabled")
    else:
        logging.disable(logging.CRITICAL)

def log_or_print(message, level='debug'):
    """ Log to file or print message to stdout """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        if level == 'debug':
            logging.getLogger().debug(message)
        elif level == 'info':
            logging.getLogger().info(message)
        elif level == 'error':
            logging.getLogger().error(message)
    else:
        print(message)

def rdmsr(core, msr):
    """  Read a MSR through via msr driver. """
    # Convert hex 0xMSR to int
    msr = hex_int(msr)

    # Open file to read MSR
    try:
        msr_filename = os.path.join("/dev/cpu/", str(core), "msr")
        msr_file = os.open(msr_filename, os.O_RDONLY)
        os.lseek(msr_file, msr, os.SEEK_SET)
        rdmsr_bytes = os.read(msr_file, 8)
        os.close(msr_file)

        # format output and print
        rdmsr_int_val = int.from_bytes(rdmsr_bytes, byteorder='big')
        rdmsr_bytes_little_endian = rdmsr_int_val.to_bytes(8, byteorder='little')
        log_or_print(f"Read value : {rdmsr_bytes_little_endian}, from MSR : {hex(msr)} on Core: {core}", level='debug')

        return rdmsr_bytes
    except (IOError, OSError) as err:
        log_or_print(f"Error:{err} Could not read MSR:{hex(msr)} from {msr_filename} on core : {core}", level='error')
        sys.exit(1)


def wrmsr(core, msr, msr_bytes):
    """ Writes an MSR via msr driver interface. """
    # Convert hex 0xMsr to int
    msr = hex_int(msr)

    # Pad msr_bytes to 8 bytes
    msr_bytes = msr_bytes.ljust(8, b'\x00')

    try:
        msr_filename = os.path.join("/dev/cpu/", str(core), "msr")
        with open(msr_filename, "wb") as msr_file:
            # format output and print
            wrmsr_int_val = int.from_bytes(msr_bytes, byteorder='big')
            wrmsr_bytes_little_endian = wrmsr_int_val.to_bytes(8, byteorder='little')
            log_or_print(f"Write to MSR:{hex(msr)} File: {msr_filename} Core: {core} Bytes: {wrmsr_bytes_little_endian}", level='debug')
            msr_file.seek(msr)
            msr_file.write(msr_bytes)
    except (IOError, OSError) as err:
        log_or_print(f"Error:{err} Could not write to MSR: {hex(msr)} on Core: {core} ", level='error')
        sys.exit(1)

def check_msr_driver():
    """ Check msr driver interface is available. """
    try:
        with open("/dev/cpu/0/msr", "r") as msr_file:
            pass
    except IOError:
        log_or_print("ERROR: 'msr' kernel module not found", level='error')
        sys.exit(1)

def range_expand(s):
    """ Parse core list from user input. """
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

# Parse command line
def parse_args():
    """ Setup and Parse command line arguments. """
    parser = argparse.ArgumentParser(
            description="Script to read and write registers\n\n"
                        "Usage examples:\n"
                        "Read MSR 0x621 on cores 0,1,2: rw-msr-tool.py -c 0,1,2 -m 0x621 -r\n"
                        "Write 0x1213 to MSR 0x620 on cores 0,1,2: rw-msr-tool.py -c 0,1,2 -m 0x620 -w 0x1213\n",
    formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-c', '--cores', type=str, required=True, help='Comma-separated list of cores or core ranges (e.g., "0,1,2-4")')
    parser.add_argument('-m', '--msr', type=str, required=True, help='MSR address to read/write (in hex)')
    parser.add_argument('-w', '--write', type=str, help='Write value to the MSR (in hex)')
    parser.add_argument('-r', '--read', action='store_true', help='Read from the MSR')
    parser.add_argument('-l', '--log', action='store_true', help='Enable logging to file (default: disabled and prints to stdout)')
    parser.add_argument('-f', '--logfile', type=str, default='rdwr-msr.log', help='Log file name (default: rdwr-msr.log)')
    return parser.parse_args()

def hex_int(value):
    """ Convert hex string to int. """
    try:
        # Check if the value starts with '0x' and remove it if it does
        if value.startswith('0x'):
            value = value[2:]
        return int(value, 16)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid hex value: {value}")

def main():
    """ Main function. """
    # Read command line args
    args = parse_args()

    # Check msr driver is loaded
    check_msr_driver()

    # Conifgure logging or printing
    setup_logging(args.log, args.logfile)

    # Get core list
    cores = range_expand(args.cores)

    # Check core range is valid
    if cores is None:
        log_or_print("Invalid core range, Cores: {cores}", level='error')
        sys.exit(1)

    # Read value and print or log
    if args.read:
        for core in cores:
            rdmsr(core, args.msr)

    if args.write:
        # Get hex string without 0x prefix
        writevalue_int = hex_int(args.write)
        # Convert int to bytes
        writevalue = writevalue_int.to_bytes(8, byteorder='little')

        for core in cores:
            wrmsr(core, args.msr, writevalue)

if __name__ == "__main__":
    main()
