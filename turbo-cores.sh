#!/bin/bash
#
#   BSD LICENSE
#
#   Copyright(c) 2017 Intel Corporation.
#
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions
#   are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in
#       the documentation and/or other materials provided with the
#       distribution.
#     * Neither the name of Intel Corporation nor the names of its
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#   A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#   OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

# This script allows enable/disable of Turbo Boost technology on
# particular cores

PLATFORM_INFO="0x0CE"
TURBO_RATIO_LIMIT="0x1AD"
IA32_PERF_CTL="0x199"

if (( $EUID != 0 )); then
	echo "This script must be run as root - Exiting."
	exit
fi

scaling_file=$(find /sys/devices/system -name scaling_driver | tail -1)

# TODO if can't find the file, continue anyway. May not always exist.
scaling=$(cat $scaling_file)
if [[ "$scaling" != "acpi-cpufreq" ]]; then
	echo "intel_pstate kernel driver must be disabled"
	echo "please add 'intel_pstate=disabled' to your kernel boot parameters"
	exit
fi

# Load MSR kernel driver to give us access to MSRs
function load_msr {

	echo "Executing: modprobe msr."
	modprobe msr
}

# Ensure prerequsite packages are installed.
function check_required_utils {

	ret=$(which wrmsr 2>/dev/null)
	if (( $? != 0 )); then
		echo "'wrmsr' not found in path. Please install msr-tools"
		exit
	fi

	ret=$(which rdmsr 2>/dev/null)
	if (( $? != 0 )); then
		echo "'rdmsr' not found in path. Please install msr-tools"
		exit
	fi

	ret=$(which lscpu 2>/dev/null)
	if (( $? != 0 )); then
		echo "'lscpu' not found in path. Please install util-linux"
		exit
	fi
}

# Check we're on a supported processor.
function check_processor {

	echo
	model=$(cat /proc/cpuinfo | grep "model\s\s" | cut -d$'\t' -f 3 | cut -d ' ' -f 2 | tail -n1)
	case $model in
	    85)
		echo "Intel® Xeon® Processor Scalable Family detected"
		;;
	    79)
		echo "Intel® Xeon® CPU E5 v4 detected (BDX)"
		;;
	    63)
		echo "Intel® Xeon® CPU E5 v3 detected (HSX)"
		;;
	    *)
		echo
		echo "---------------------------"
		echo "Unsupported CPU model"
		echo "Proceed at your own risk!!!"
		echo "---------------------------"
		echo
		sleep 2
		;;
	esac
}

# Show current Turbo status for package (socket)
# Bit 38 in msr 1a0h is the TURBO_MODE_DISABLE bit for the whole package.
# If it's 1, then turbo is disabled on the package.
function check_pkg_turbo_config {

	# Set core list to one core from each socket...
	cores=$(lscpu -p | grep -v "#" | sed "s/,/ /g" | cut -d " " -f 1,2,3 | uniq -f 2 | cut -d " " -f 1 | awk '{printf "%d ",$1}')

	# $cores should now have a list of core_ids, one core_id per socket.
	for core in $cores; do
		socket=$(cat /sys/devices/system/cpu/cpu$core/topology/physical_package_id)
		state=$(rdmsr 0x1a0 -f 38:38)
		if [[ $state -eq 1 ]]; then
			echo "------------------------------------"
			echo "Package TURBO disabled for socket $socket"
			echo "------------------------------------"
		else
			echo "-----------------------------------"
			echo "Package TURBO enabled for socket $socket"
			echo "-----------------------------------"
		fi
	done
}

# Enable Turbo on the package (socket)
function enable_pkg_turbo {

	# Set core list to one core from each socket...
	cores=$(lscpu -p | grep -v "#" | sed "s/,/ /g" | cut -d " " -f 1,2,3 | uniq -f 2 | cut -d " " -f 1 | awk '{printf "%d ",$1}')

	# $cores should now have a list of core_ids, one core_id per socket.
	for core in $cores; do
		socket=$(cat /sys/devices/system/cpu/cpu$core/topology/physical_package_id)
		state=$(rdmsr -p${core} 0x1a0 -f 38:38)
		if [[ $state -eq 1 ]]; then
			echo "TURBO disabled on core $socket, attempting to enable..."
			val="0x"$(rdmsr -p0 ${PLATFORM_INFO} -f 15:8)
			# switch off the TURBO_DISABLE bit
			val=$(( val & ~0x4000000000 ))
			val=$(printf '0x%X\n' "$val")
			wrmsr -p${core} 0x1a0 $val
			# check again
			state=$(rdmsr -p${core} 0x1a0 -f 38:38)
			if [[ $state -eq 1 ]]; then
				echo "Failed to enable TURBO on socket $socket, exiting"
				exit
			else
				echo "------------------------------------"
				echo "Package TURBO Enabled for socket $socket"
				echo "------------------------------------"
			fi
		else
			echo "--------------------------------------------"
			echo "Package TURBO already enabled for socket $socket"
			echo "--------------------------------------------"
		fi
	done
}

# Disable Turbo on the package (socket)
function disable_pkg_turbo {

	# Set core list to one core from each socket...
	cores=$(lscpu -p | grep -v "#" | sed "s/,/ /g" | cut -d " " -f 1,2,3 | uniq -f 2 | cut -d " " -f 1 | awk '{printf "%d ",$1}')

	# $cores should now have a list of core_ids, one core_id per socket.
	for core in $cores; do
		socket=$(cat /sys/devices/system/cpu/cpu$core/topology/physical_package_id)
		state=$(rdmsr -p${core} 0x1a0 -f 38:38)
		if [[ $state -eq 0 ]]; then
			echo "TURBO enabled on socket $socket, attempting to disable..."
			val="0x"$(rdmsr -p0 ${PLATFORM_INFO} -f 15:8)
			# switch on the TURBO_DISABLE bit
			val=$(( val | 0x4000000000 ))
			val=$(printf '0x%X\n' "$val")
			wrmsr -p${core} 0x1a0 $val
			# check again
			state=$(rdmsr -p${core} 0x1a0 -f 38:38)
			if [[ $state -eq 0 ]]; then
				echo "Failed to enable TURBO on socket $socket, exiting"
				exit
			else
				echo "-----------------------------------"
				echo "Package TURBO disabled for socket $socket"
				echo "-----------------------------------"
			fi
		else
			echo "-------------------------------------------"
			echo "Package TURBO already disabled for socket $socket"
			echo "-------------------------------------------"
		fi
	done
}

# Print out the Turbo status of each core
function show_per_core_turbo {

	# Now print out the status of all cores
	cores=$(cat /proc/cpuinfo | grep processor | awk '{printf "%d ",$3}')
	for core in $cores; do
		package_state=$(rdmsr -p${core} 0x1a0 -f 38:38)
		if [[ $package_state -eq 0 ]]; then
			# Check bit 32 of 0x199 to see if TURBO_DISABLE is on
			state=$(rdmsr -p${core} ${IA32_PERF_CTL} -f 32:32)
			core=$(printf '%02d' "$core")
			if [[ $state -eq 1 ]]; then
				echo "core ${core}: turbo disabled"
			else
				echo "core ${core}: turbo enabled"
			fi
		fi
	done
}

# Disable per-core turbo based on user input.
function disable_per_core_turbo {

	echo
	echo "Please enter a list of cores to disable: "
	echo -n "E.g. '3 5 7' or 'all': "

	read opt

	if [[ "$opt" == "all" ]]; then
		cores=$(cat /proc/cpuinfo | grep processor | awk '{printf "%d ", $3}')
	else
		cores=$opt
	fi

	if [[ $cores ]]; then
		echo "Disabling Turbo on core(s) $cores"
	fi

	for core in $cores; do
		# Here we're setting all non turbo'd cores to run at the max
		# non turbo frequency, regardlesss of what they were running
		# at before.
		# Get max_non_turbo freq
		val="0x"$(rdmsr -p0 ${PLATFORM_INFO} -f 15:8)"00"
		# set bit 32 high to disable turbo
		val=$(( val | 0x100000000 ))
		val=$(printf '0x%X\n' "$val")
		wrmsr -p${core} ${IA32_PERF_CTL} $val
	done
}

# Enable per-core turbo based on user input.
function enable_per_core_turbo {

	echo
	echo "Please enter a list of cores to enable: "
	echo -n "E.g. '3 5 7' or 'all': "

	read opt

	if [[ "$opt" == "all" ]]; then
		cores=$(cat /proc/cpuinfo | grep processor | awk '{printf "%d ", $3}')
	else
		cores=$opt
	fi

	# bit 32 in IA32_PERF_CTL msr is the TURBO_MODE_DISABLE bit for
	# individual cores. If it's 1, then turbo is disabled on that core.

	# disable_per_core_turbo_all

	# Now enable turbo on some cores. Change 'cores' to the ones on which you
	# want turbo enabled

	if [[ $cores ]]; then
		echo "Enabling Turbo on core(s) $cores"
	else
		echo
		echo "WARNING: No corelist provided, not enabling Turbo on any cores!"
		echo "Usage example: turbo-select \"3 5 7\""
		echo
		echo "Also, fyi, a quick test on particular cores can be done with:"
		echo "taskset -c 3-6 sysbench --num-threads=4 --max-requests=10000000 --test=cpu run"
		echo
		exit 0
	fi

	for core in $cores; do
		# Get the max possible turbo frequency (when 1 core active)
		val="0x"$(rdmsr -p0 ${TURBO_RATIO_LIMIT} -f 7:0)"00"
		# set bit 32 low to enable turbo
		val=$(( val & ~0x100000000 ))
		val=$(printf '0x%X\n' "$val")
		wrmsr -p${core} ${IA32_PERF_CTL} $val
	done
}

# Present the main menu
show_menu(){

	#check if MSR tool is installed
	which wrmsr 2>&1
	MSR_TOOL=$?

    	printf "\n\n$C_YELLOW********************************************************$C_NORMAL\n"
	if [ $MSR_TOOL -ne 0 ]; then
		printf "1)$C_RED MSR tool is not installed$C_NORMAL - option is not available\n"
		printf "2)$C_RED MSR tool is not installed$C_NORMAL - option is not available\n"
		printf "3)$C_RED MSR tool is not installed$C_NORMAL - option is not available"
		printf "4)$C_RED MSR tool is not installed$C_NORMAL - option is not available"
		printf "5)$C_RED MSR tool is not installed$C_NORMAL - option is not available"

	else
		state=$(rdmsr 0x1a0 -f 38:38)
		printf "1) Load msr tools driver\n"
		printf "2) Check Turbo Boost Configuration\n"
		printf "3) Enable package-wide Turbo Boost\n"
		printf "4) Disable package-wide Turbo Boost\n"

		if [[ $state -eq 0 ]]; then
			printf "5) Enable per-core Turbo Boost\n"
			printf "6) Disable per-core Turbo Boost\n"
		else
			printf "5) Package TURBO is disabled - option is not available\n"
			printf "6) Package TURBO is disabled - option is not available\n"
		fi
	 fi
	printf "\nq) Quit\n"
	printf "$C_BLUE\nPlease enter your choice: $C_NORMAL"
    read opt
echo
}

# Call relevant function based on user input
function process_request(){
	#echo "Processing $opt"
	#opt=$1
	state=$(rdmsr 0x1a0 -f 38:38)
	case $opt in
	    1)
		load_msr
		;;
	    2)
		check_pkg_turbo_config
		show_per_core_turbo
		;;
	    3)
		enable_pkg_turbo
		;;
	    4)
		disable_pkg_turbo
		;;
	    5)
		if [[ $state -eq 0 ]]; then
			enable_per_core_turbo
			show_per_core_turbo
		else
			echo "Invalid Option"
		fi
		;;
	    6)
		if [[ $state -eq 0 ]]; then
			disable_per_core_turbo
			show_per_core_turbo
		else
			echo "Invalid Option"
		fi
		;;
	    q)
		exit
		;;
	    *)
		echo "unknown option"
		;;
	esac
}

# main
check_required_utils
check_processor

while [[ 1 ]]; do
	show_menu
	process_request
done

