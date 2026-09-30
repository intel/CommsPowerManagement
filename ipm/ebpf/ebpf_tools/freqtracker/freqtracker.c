/*
 * SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Intel Corporation
 */

#define _GNU_SOURCE
#include <argp.h>
#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <limits.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include "freqtracker.h"
#include "freqtracker.skel.h"

struct env {
	int interval;
	const char *cpu_list;
	int detail_cpu;
	bool detail_cpu_set;
	char allowed_comm[TASK_COMM_LEN];
	bool no_clear;
	bool verbose;
	int grid_cols;
} env = {
	.interval = 1,
	.detail_cpu = -1,
	.grid_cols = 4,
};

static volatile sig_atomic_t exiting;
static int nr_cpus;
static struct cpu_freq_history histories[MAX_CPU_NR];
static __u64 change_count[MAX_CPU_NR];
static bool first_pass = true;
static bool use_color;
static bool has_initial_min[MAX_CPU_NR];
static bool has_initial_max[MAX_CPU_NR];
static bool has_initial_cur[MAX_CPU_NR];
static bool has_cpuinfo_min[MAX_CPU_NR];
static bool has_cpuinfo_max[MAX_CPU_NR];
static __u32 initial_min_khz[MAX_CPU_NR];
static __u32 initial_max_khz[MAX_CPU_NR];
static __u32 initial_cur_khz[MAX_CPU_NR];
static __u32 cpuinfo_min_khz[MAX_CPU_NR];
static __u32 cpuinfo_max_khz[MAX_CPU_NR];
static bool has_ebpf_min[MAX_CPU_NR];
static bool has_ebpf_max[MAX_CPU_NR];
static bool has_ebpf_actual[MAX_CPU_NR];
static __u32 ebpf_min_khz[MAX_CPU_NR];
static __u32 ebpf_max_khz[MAX_CPU_NR];
static __u32 ebpf_actual_khz[MAX_CPU_NR];
static bool cpu_filter[MAX_CPU_NR];
static int policy_cpu[MAX_CPU_NR];
static volatile sig_atomic_t cursor_hidden;
static int prev_render_lines;
static int freq_bins_fd = -1;
static int freq_stats_fd = -1;
static __u64 dropped_hist_bins;
static __u64 dropped_requests;
static __u64 dropped_events;
static bool single_core_mode;
static int selected_cpu = -1;
static const char *attach_method = "kprobe";

#define MAX_UNIQUE_PROCESS_NAMES 5
struct unique_process_list {
	char names[MAX_UNIQUE_PROCESS_NAMES][TASK_COMM_LEN];
	int count;
};
static struct unique_process_list unique_processes[MAX_CPU_NR];
static __u64 counted_event_seq[MAX_CPU_NR][FREQ_HISTORY_LEN];
static __u64 unique_event_seq[MAX_CPU_NR][FREQ_HISTORY_LEN];

#define STAR_PLAIN_MAX 14
#define STAR_COL_WIDTH 20
#define CELL_WIDTH 64
#define INIT_SUMMARY_WIDTH 16
#define STAR_BUF_SIZE (STAR_COL_WIDTH + 24)
#define MAX_DETAIL_BINS FREQ_MAX_HIST_BINS
#define DETAIL_TYPES FREQ_REQ_TYPES
#define DETAIL_MAX_EVENTS 10

struct core_view {
	bool has_min;
	bool has_max;
	bool has_actual;
	bool min_is_initial;
	bool max_is_initial;
	bool actual_is_initial;
	bool has_event;
	__u32 min_khz;
	__u32 max_khz;
	__u32 actual_khz;
	__u64 latest_ts_ns;
	__u64 actual_ts_ns;
	__u64 stars;
	char last_comm[TASK_COMM_LEN];
};

struct detail_bin {
	__u32 freq_khz;
	__u64 count;
};

struct detail_hist {
	int nr_bins;
	bool overflow;
	struct detail_bin bins[MAX_DETAIL_BINS];
};

static __u32 avail_freqs_khz[MAX_CPU_NR][MAX_DETAIL_BINS];
static int nr_avail_freqs[MAX_CPU_NR];
#define FRAME_BUF_SIZE (MAX_CPU_NR * (CELL_WIDTH + 64) + 65536)
static char frame[FRAME_BUF_SIZE];
static char out[FRAME_BUF_SIZE + 4096];
#define ANSI_RESET "\033[0m"
#define ANSI_RED "\033[31m"
#define ANSI_GREEN "\033[32m"
#define ANSI_BLUE "\033[34m"
#define ANSI_HIDE_CURSOR "\033[?25l"
#define ANSI_SHOW_CURSOR "\033[?25h"

const char argp_program_doc[] = "Track per-core min/max requests and actual CPU frequency.\n"
				"\n"
				"USAGE: freqtracker [--help] [-i SEC] [-c CPU] [-f CORES] [-w COLS] [-a COMM] [-C]\n"
				"\n"
				"EXAMPLES:\n"
				"    freqtracker        # live view for all CPUs\n"
				"    freqtracker -c 3   # detailed single-core mode for cpu 3\n"
				"    freqtracker -f 0-7 # filter display to cores 0-7\n"
				"    freqtracker -a bash # highlight only processes named bash in green\n"
				"    freqtracker -w 6   # display 6 columns\n"
				"    freqtracker -i 2   # refresh every 2 seconds\n"
				"    freqtracker -C     # do not clear terminal between refreshes\n";

static const struct argp_option opts[] = {
	{ "interval", 'i', "SEC", 0, "Refresh interval in seconds", 0 },
	{ "cpu", 'c', "CORE", 0, "Detailed single-core mode for a single CPU", 0 },
	{ "filter", 'f', "CORES", 0, "Filter cores to display (e.g. 0-7,12-15)", 0 },
	{ "width", 'w', "COLS", 0, "Number of columns in grid display", 0 },
	{ "allowed",
			'a',
			"COMM",
			0,
			"Allowed process name to color green uses kernel task comm format (16 bytes total, including "
			"trailing NUL; max 15 visible chars)",
			0 },
	{ "no-clear", 'C', NULL, 0, "Do not clear terminal each refresh", 0 },
	{ "verbose", 'v', NULL, 0, "Verbose debug output", 0 },
	{ NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help", 0 },
	{},
};

static int
parse_cpu_index(const char *s, int *cpu)
{
	long v;
	char *end;

	if (!s || !*s)
		return -EINVAL;

	errno = 0;
	v = strtol(s, &end, 10);
	if (errno || end == s || *end != '\0' || v < 0 || v > INT_MAX)
		return -EINVAL;

	*cpu = (int)v;
	return 0;
}

/* argp callback: the argp_usage() error paths exit the process. */
static error_t
parse_arg(int key, char *arg, struct argp_state *state)
{
	char *end;
	long v;

	switch (key) {
		case 'h':
			argp_state_help(state, stderr, ARGP_HELP_STD_HELP);
			break;
		case 'i':
			errno = 0;
			v = strtol(arg, &end, 10);
			if (errno || end == arg || *end != '\0' || v <= 0 || v > INT_MAX) {
				fprintf(stderr, "invalid interval: %s\n", arg);
				argp_usage(state);
				break;
			}
			env.interval = (int)v;
			break;
		case 'c':
			if (parse_cpu_index(arg, &env.detail_cpu) < 0) {
				fprintf(stderr, "invalid CPU: %s\n", arg);
				argp_usage(state);
				break;
			}
			env.detail_cpu_set = true;
			break;
		case 'C':
			env.no_clear = true;
			break;
		case 'f':
			env.cpu_list = arg;
			if (!env.cpu_list || env.cpu_list[0] == '\0') {
				fprintf(stderr, "invalid core filter: %s\n", arg);
				argp_usage(state);
				break;
			}
			break;
		case 'w':
			errno = 0;
			v = strtol(arg, &end, 10);
			if (errno || end == arg || *end != '\0' || v <= 0 || v > 100) {
				fprintf(stderr, "invalid width: %s (must be 1-100)\n", arg);
				argp_usage(state);
				break;
			}
			env.grid_cols = (int)v;
			break;
		case 'a':
			if (!arg || arg[0] == '\0') {
				fprintf(stderr, "invalid allowed process name: %s\n", arg ? arg : "");
				argp_usage(state);
				break;
			}
			if (strlen(arg) >= sizeof(env.allowed_comm)) {
				fprintf(stderr,
						"allowed process name must be at most %zu bytes (kernel comm limit)\n",
						sizeof(env.allowed_comm) - 1);
				argp_usage(state);
				break;
			}
			snprintf(env.allowed_comm, sizeof(env.allowed_comm), "%s", arg);
			break;
		case 'v':
			env.verbose = true;
			break;
		default:
			return ARGP_ERR_UNKNOWN;
	}

	return 0;
}

static int
libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	if (level == LIBBPF_DEBUG && !env.verbose)
		return 0;

	return vfprintf(stderr, format, args);
}

static int
ensure_core_btf(struct bpf_object_open_opts *open_opts)
{
	const char *custom_btf_path;

	if (!open_opts)
		return -EINVAL;

	custom_btf_path = getenv("BTF_FILE");
	if (custom_btf_path) {
		if (access(custom_btf_path, R_OK) == 0) {
			open_opts->btf_custom_path = custom_btf_path;
			return 0;
		}
		return -errno;
	}

	return 0;
}

enum attach_mode {
	ATTACH_MODE_INVALID = -1,
	ATTACH_MODE_AUTO = 0,
	ATTACH_MODE_KPROBE,
	ATTACH_MODE_FEXIT,
};

static enum attach_mode
parse_attach_mode(const char *mode)
{
	if (!mode || !mode[0] || strcmp(mode, "auto") == 0)
		return ATTACH_MODE_AUTO;
	if (strcmp(mode, "kprobe") == 0)
		return ATTACH_MODE_KPROBE;
	if (strcmp(mode, "fexit") == 0 || strcmp(mode, "fentry") == 0)
		return ATTACH_MODE_FEXIT;

	return ATTACH_MODE_INVALID;
}

static int
resolve_attach_mode(enum attach_mode *mode)
{
	const char *requested = getenv("FREQTRACKER_ATTACH");

	*mode = parse_attach_mode(requested);
	if (*mode == ATTACH_MODE_INVALID) {
		// clang-format off
		fprintf(stderr,
				"invalid FREQTRACKER_ATTACH '%s' (expected auto, fexit, kprobe, or fentry [legacy alias for fexit])\n",
				requested);
		// clang-format on
		return -EINVAL;
	}

	return 0;
}

/* The kernel refuses to load a BPF program for want of privileges the same way
 * whatever it is asked to attach to, so there is nothing useful to fall back to. */
static bool
is_permission_error(int err)
{
	return err == -EPERM || err == -EACCES;
}

/* Not unit-tested: a straight-line table of libbpf autoload toggles on a
 * real skeleton, with no logic a fake could meaningfully exercise. */
// LCOV_EXCL_START
static void
configure_attach_autoload(struct freqtracker_bpf *obj, enum attach_mode mode)
{
	if (mode == ATTACH_MODE_FEXIT) {
		attach_method = "fexit";
		bpf_program__set_autoload(obj->progs.store_scaling_max_freq, false);
		bpf_program__set_autoload(obj->progs.store_scaling_min_freq, false);
		bpf_program__set_autoload(obj->progs.kretprobe_store_scaling_max_freq, false);
		bpf_program__set_autoload(obj->progs.kretprobe_store_scaling_min_freq, false);
		bpf_program__set_autoload(obj->progs.fexit_store_scaling_max_freq, true);
		bpf_program__set_autoload(obj->progs.fexit_store_scaling_min_freq, true);
		return;
	}

	attach_method = "kretprobe";
	bpf_program__set_autoload(obj->progs.fexit_store_scaling_max_freq, false);
	bpf_program__set_autoload(obj->progs.fexit_store_scaling_min_freq, false);
	bpf_program__set_autoload(obj->progs.store_scaling_max_freq, true);
	bpf_program__set_autoload(obj->progs.store_scaling_min_freq, true);
	bpf_program__set_autoload(obj->progs.kretprobe_store_scaling_max_freq, true);
	bpf_program__set_autoload(obj->progs.kretprobe_store_scaling_min_freq, true);
}
// LCOV_EXCL_STOP

static void
sig_handler(int signo)
{
	(void)signo;
	exiting = 1;
}

static void
restore_terminal(void)
{
	if (!cursor_hidden)
		return;

	printf(ANSI_SHOW_CURSOR);
	fflush(stdout);
	cursor_hidden = false;
}

/* Same job as restore_terminal(), but write() is async-signal-safe and printf() is not. */
static void
restore_terminal_from_handler(void)
{
	ssize_t ignored;

	if (!cursor_hidden)
		return;

	cursor_hidden = false;
	ignored = write(STDOUT_FILENO, ANSI_SHOW_CURSOR, sizeof(ANSI_SHOW_CURSOR) - 1);
	(void)ignored;
}

/* Not unit-tested: re-raising the signal would take the test runner down with it. */
// LCOV_EXCL_START
/* SIGQUIT and SIGHUP terminate by default, so atexit() never runs and the
 * terminal would be left without a cursor. Undo that, then die as asked. */
static void
fatal_sig_handler(int signo)
{
	restore_terminal_from_handler();
	signal(signo, SIG_DFL);
	raise(signo);
}
// LCOV_EXCL_STOP

static int
init_cpu_filter(void)
{
	int i, start, end;
	char *spec, *tok, *saveptr = NULL;
	bool any = false;

	for (i = 0; i < nr_cpus; i++)
		cpu_filter[i] = false;

	if (!env.cpu_list) {
		for (i = 0; i < nr_cpus; i++)
			cpu_filter[i] = true;
		return 0;
	}

	spec = strdup(env.cpu_list);
	if (!spec)
		return -ENOMEM;

	for (tok = strtok_r(spec, ",", &saveptr); tok; tok = strtok_r(NULL, ",", &saveptr)) {
		char *dash;

		dash = strchr(tok, '-');
		if (!dash) {
			if (parse_cpu_index(tok, &start) < 0 || start >= nr_cpus) {
				free(spec);
				return -EINVAL;
			}
			cpu_filter[start] = true;
			any = true;
			continue;
		}

		*dash = '\0';
		if (parse_cpu_index(tok, &start) < 0 || parse_cpu_index(dash + 1, &end) < 0 || start > end ||
				end >= nr_cpus) {
			free(spec);
			return -EINVAL;
		}

		for (i = start; i <= end; i++)
			cpu_filter[i] = true;
		any = true;
	}

	free(spec);
	if (!any)
		return -EINVAL;

	return 0;
}

static int
update_selected_cpu_mode(void)
{
	single_core_mode = false;
	selected_cpu = -1;
	if (!env.detail_cpu_set)
		return 0;

	if (env.detail_cpu < 0 || env.detail_cpu >= nr_cpus) {
		fprintf(stderr, "invalid CPU %d for [0, %d]\n", env.detail_cpu, nr_cpus - 1);
		return -EINVAL;
	}

	selected_cpu = env.detail_cpu;
	single_core_mode = true;
	cpu_filter[selected_cpu] = true;
	return 0;
}

static int
parse_related_cpus(const char *text, bool members[MAX_CPU_NR])
{
	const char *cursor = text;
	bool any = false;

	memset(members, 0, sizeof(bool) * MAX_CPU_NR);
	while (cursor && *cursor) {
		char *endptr;
		long start, end;

		while (isspace((unsigned char)*cursor) || *cursor == ',')
			cursor++;
		if (!*cursor)
			break;

		errno = 0;
		start = strtol(cursor, &endptr, 10);
		if (errno || endptr == cursor || start < 0 || start >= nr_cpus)
			return -EINVAL;
		cursor = endptr;
		end = start;
		if (*cursor == '-') {
			cursor++;
			errno = 0;
			end = strtol(cursor, &endptr, 10);
			if (errno || endptr == cursor || end < start || end >= nr_cpus)
				return -EINVAL;
			cursor = endptr;
		}
		if (*cursor && !isspace((unsigned char)*cursor) && *cursor != ',')
			return -EINVAL;

		for (; start <= end; start++)
			members[start] = true;
		any = true;
	}

	return any ? 0 : -EINVAL;
}

static void
init_policy_topology(void)
{
	int representative, cpu;

	for (cpu = 0; cpu < nr_cpus; cpu++)
		policy_cpu[cpu] = cpu;

	for (representative = 0; representative < nr_cpus; representative++) {
		char path[128];
		char list[4096];
		bool members[MAX_CPU_NR];
		FILE *file;

		snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpufreq/policy%d/related_cpus", representative);
		file = fopen(path, "r");
		if (!file)
			continue;
		if (!fgets(list, sizeof(list), file) || parse_related_cpus(list, members) < 0) {
			if (env.verbose)
				fprintf(stderr, "failed to parse cpufreq topology from %s\n", path);
			fclose(file);
			continue;
		}
		fclose(file);

		for (cpu = 0; cpu < nr_cpus; cpu++) {
			if (members[cpu])
				policy_cpu[cpu] = representative;
		}
	}
}

static void
append_request_event(int cpu, const struct freq_stream_event *stream_event)
{
	struct cpu_freq_history *history = &histories[cpu];
	struct freq_event *event;
	__u64 seq = ++history->next_seq;

	event = &history->events[(seq - 1) % FREQ_HISTORY_LEN];
	event->ts_ns = stream_event->ts_ns;
	event->freq_khz = stream_event->freq_khz;
	event->pid = stream_event->pid;
	event->req_type = stream_event->req_type;
	memcpy(event->comm, stream_event->comm, sizeof(event->comm));
	event->seq = seq;
	history->seq = seq;
}

static void
consume_stream_event(const struct freq_stream_event *stream_event)
{
	struct cpu_freq_history *history;
	int cpu;

	if (stream_event->cpu >= (__u32)nr_cpus || stream_event->req_type >= FREQ_REQ_TYPES)
		return;
	history = &histories[stream_event->cpu];
	if (stream_event->req_type == FREQ_REQ_ACTUAL) {
		history->actual_freq_khz = stream_event->freq_khz;
		history->actual_ts_ns = stream_event->ts_ns;
		history->actual_seq = ++history->next_actual_seq;
		return;
	}

	for (cpu = 0; cpu < nr_cpus; cpu++) {
		if (policy_cpu[cpu] == (int)stream_event->cpu)
			append_request_event(cpu, stream_event);
	}
}

static int
collect_events(int map_fd)
{
	struct freq_stream_event stream_event;
	int err;

	while (true) {
		err = bpf_map_lookup_and_delete_elem(map_fd, NULL, &stream_event);
		if (err < 0) {
			if (errno == ENOENT)
				break;
			return -errno;
		}
		consume_stream_event(&stream_event);
	}

	return 0;
}

static void
collect_stats(void)
{
	__u32 key;
	__u64 value = 0;

	if (freq_stats_fd < 0)
		return;
	key = FREQ_STAT_DROPPED_BINS;
	if (bpf_map_lookup_elem(freq_stats_fd, &key, &value) == 0)
		dropped_hist_bins = value;
	key = FREQ_STAT_DROPPED_REQUESTS;
	if (bpf_map_lookup_elem(freq_stats_fd, &key, &value) == 0)
		dropped_requests = value;
	key = FREQ_STAT_DROPPED_EVENTS;
	if (bpf_map_lookup_elem(freq_stats_fd, &key, &value) == 0)
		dropped_events = value;
}

static int
read_sysfs_u32(const char *path, __u32 *value)
{
	FILE *f;
	unsigned int tmp;

	f = fopen(path, "r");
	if (!f)
		return -errno;

	if (fscanf(f, "%u", &tmp) != 1) {
		fclose(f);
		return -EINVAL;
	}

	fclose(f);
	*value = (__u32)tmp;
	return 0;
}

static int
read_scaling_freq_khz(int cpu, bool min_freq, __u32 *freq_khz)
{
	char path[128];

	snprintf(path,
			sizeof(path),
			"/sys/devices/system/cpu/cpu%d/cpufreq/scaling_%s_freq",
			cpu,
			min_freq ? "min" : "max");

	return read_sysfs_u32(path, freq_khz);
}

static int
read_cur_freq_khz(int cpu, __u32 *freq_khz)
{
	char path[128];

	snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq", cpu);

	return read_sysfs_u32(path, freq_khz);
}

static int
read_cpuinfo_freq_khz(int cpu, bool min_freq, __u32 *freq_khz)
{
	char path[128];

	snprintf(path,
			sizeof(path),
			"/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_%s_freq",
			cpu,
			min_freq ? "min" : "max");

	return read_sysfs_u32(path, freq_khz);
}

static void
read_avail_freqs(int cpu)
{
	char path[128];
	FILE *f;
	unsigned int val;
	int n = 0;
	int i, j;

	snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_available_frequencies", cpu);
	f = fopen(path, "r");
	if (!f)
		return;

	while (n < MAX_DETAIL_BINS && fscanf(f, "%u", &val) == 1)
		avail_freqs_khz[cpu][n++] = (__u32)val;
	fclose(f);

	for (i = 0; i < n; i++) {
		for (j = i + 1; j < n;) {
			if (avail_freqs_khz[cpu][j] == avail_freqs_khz[cpu][i]) {
				memmove(&avail_freqs_khz[cpu][j],
						&avail_freqs_khz[cpu][j + 1],
						(size_t)(n - j - 1) * sizeof(avail_freqs_khz[cpu][0]));
				n--;
				continue;
			}
			j++;
		}
	}

	for (i = 1; i < n; i++) {
		__u32 key = avail_freqs_khz[cpu][i];
		j = i - 1;

		while (j >= 0 && avail_freqs_khz[cpu][j] > key) {
			avail_freqs_khz[cpu][j + 1] = avail_freqs_khz[cpu][j];
			j--;
		}
		avail_freqs_khz[cpu][j + 1] = key;
	}

	nr_avail_freqs[cpu] = n;
}

static void
synthesize_avail_freqs(int cpu)
{
	__u32 min_khz;
	__u32 max_khz;
	__u32 freq_khz;
	int n = 0;
	const __u32 step_khz = 100000;

	if (nr_avail_freqs[cpu] > 0)
		return;

	if (has_cpuinfo_min[cpu] && has_cpuinfo_max[cpu]) {
		min_khz = cpuinfo_min_khz[cpu];
		max_khz = cpuinfo_max_khz[cpu];
	} else if (has_initial_min[cpu] && has_initial_max[cpu]) {
		min_khz = initial_min_khz[cpu];
		max_khz = initial_max_khz[cpu];
	} else {
		return;
	}

	if (!min_khz || !max_khz || min_khz > max_khz)
		return;

	for (freq_khz = min_khz; freq_khz <= max_khz && n < MAX_DETAIL_BINS; freq_khz += step_khz)
		avail_freqs_khz[cpu][n++] = freq_khz;

	if (n > 0 && avail_freqs_khz[cpu][n - 1] != max_khz && n < MAX_DETAIL_BINS)
		avail_freqs_khz[cpu][n++] = max_khz;

	nr_avail_freqs[cpu] = n;
}

static void
init_sysfs_freq_bounds(void)
{
	int cpu;

	for (cpu = 0; cpu < nr_cpus; cpu++) {
		if (!cpu_filter[cpu])
			continue;

		if (read_scaling_freq_khz(cpu, true, &initial_min_khz[cpu]) == 0)
			has_initial_min[cpu] = true;
		if (read_scaling_freq_khz(cpu, false, &initial_max_khz[cpu]) == 0)
			has_initial_max[cpu] = true;
		if (read_cur_freq_khz(cpu, &initial_cur_khz[cpu]) == 0)
			has_initial_cur[cpu] = true;
		if (read_cpuinfo_freq_khz(cpu, true, &cpuinfo_min_khz[cpu]) == 0)
			has_cpuinfo_min[cpu] = true;
		if (read_cpuinfo_freq_khz(cpu, false, &cpuinfo_max_khz[cpu]) == 0)
			has_cpuinfo_max[cpu] = true;
		read_avail_freqs(cpu);
		synthesize_avail_freqs(cpu);
	}
}
static const char *
req_type_name(__u32 req_type)
{
	switch (req_type) {
		case FREQ_REQ_MAX:
			return "max";
		case FREQ_REQ_MIN:
			return "min";
		case FREQ_REQ_ACTUAL:
			return "actual";
		default:
			return "unknown";
	}
}

#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif

static __u64
monotonic_ns(void)
{
	struct timespec ts = {};

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (__u64)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static void
format_wall_time(char *buf, size_t size)
{
	time_t now;
	struct tm tm = {};

	now = time(NULL);
	if (localtime_r(&now, &tm))
		strftime(buf, size, "%H:%M:%S", &tm);
	else
		snprintf(buf, size, "--:--:--");
}

static void
update_unique_processes(int cpu)
{
	struct cpu_freq_history *history = &histories[cpu];
	__u64 seq = history->seq;
	__u64 start, i;
	int j;

	if (!seq)
		return;

	start = seq > FREQ_HISTORY_LEN ? seq - FREQ_HISTORY_LEN : 0;

	/* Only process each ring slot generation once. */
	for (i = seq; i > start; i--) {
		struct freq_event *event = &history->events[(i - 1) % FREQ_HISTORY_LEN];
		const char *comm;
		bool found = false;

		if (event->seq != i || !event->ts_ns)
			continue;
		if (unique_event_seq[cpu][(i - 1) % FREQ_HISTORY_LEN] == event->seq)
			continue;
		unique_event_seq[cpu][(i - 1) % FREQ_HISTORY_LEN] = event->seq;

		comm = event->comm[0] ? event->comm : "-";

		/* Check if we've already seen this process name */
		for (j = 0; j < unique_processes[cpu].count; j++) {
			if (strcmp(unique_processes[cpu].names[j], comm) == 0) {
				found = true;
				break;
			}
		}

		/* Add new unique process name */
		if (!found) {
			if (unique_processes[cpu].count < MAX_UNIQUE_PROCESS_NAMES) {
				/* We have space, just add it */
				snprintf(unique_processes[cpu].names[unique_processes[cpu].count],
						TASK_COMM_LEN,
						"%s",
						comm);
				unique_processes[cpu].count++;
			} else {
				/* We're at capacity, shift down and add at the end */
				memmove(unique_processes[cpu].names[0],
						unique_processes[cpu].names[1],
						(MAX_UNIQUE_PROCESS_NAMES - 1) *
								sizeof(unique_processes[cpu].names[0]));
				snprintf(unique_processes[cpu].names[MAX_UNIQUE_PROCESS_NAMES - 1],
						TASK_COMM_LEN,
						"%s",
						comm);
			}
		}
	}
}

static void
build_core_view(int cpu, struct core_view *view)
{
	struct cpu_freq_history *history = &histories[cpu];
	__u64 seq = history->seq;
	__u64 actual_seq = history->actual_seq;
	__u64 start, i;
	__u64 new_events = 0;
	bool got_event_min = false, got_event_max = false;

	memset(view, 0, sizeof(*view));
	if (has_ebpf_min[cpu]) {
		view->has_min = true;
		view->min_khz = ebpf_min_khz[cpu];
	} else if (has_initial_min[cpu]) {
		view->has_min = true;
		view->min_khz = initial_min_khz[cpu];
		view->min_is_initial = true;
	}
	if (has_ebpf_max[cpu]) {
		view->has_max = true;
		view->max_khz = ebpf_max_khz[cpu];
	} else if (has_initial_max[cpu]) {
		view->has_max = true;
		view->max_khz = initial_max_khz[cpu];
		view->max_is_initial = true;
	}
	if (has_ebpf_actual[cpu]) {
		view->has_actual = true;
		view->actual_khz = ebpf_actual_khz[cpu];
	} else if (has_initial_cur[cpu]) {
		view->has_actual = true;
		view->actual_khz = initial_cur_khz[cpu];
		view->actual_is_initial = true;
	}

	if (!seq)
		goto out;

	start = seq > FREQ_HISTORY_LEN ? seq - FREQ_HISTORY_LEN : 0;
	for (i = seq; i > start; i--) {
		struct freq_event *event = &history->events[(i - 1) % FREQ_HISTORY_LEN];

		if (event->seq != i)
			continue;
		if (!event->ts_ns)
			continue;
		if (counted_event_seq[cpu][(i - 1) % FREQ_HISTORY_LEN] != event->seq) {
			new_events++;
			counted_event_seq[cpu][(i - 1) % FREQ_HISTORY_LEN] = event->seq;
		}
		if (!view->has_event) {
			view->latest_ts_ns = event->ts_ns;
			view->has_event = true;
		}
		if (view->last_comm[0] == '\0')
			snprintf(view->last_comm, sizeof(view->last_comm), "%s", event->comm);
		if (!got_event_min && event->req_type == FREQ_REQ_MIN) {
			view->min_khz = event->freq_khz;
			view->has_min = true;
			view->min_is_initial = false;
			has_ebpf_min[cpu] = true;
			ebpf_min_khz[cpu] = event->freq_khz;
			got_event_min = true;
		}
		if (!got_event_max && event->req_type == FREQ_REQ_MAX) {
			view->max_khz = event->freq_khz;
			view->has_max = true;
			view->max_is_initial = false;
			has_ebpf_max[cpu] = true;
			ebpf_max_khz[cpu] = event->freq_khz;
			got_event_max = true;
		}
		if (got_event_min && got_event_max)
			break;
	}

	if (!first_pass)
		change_count[cpu] += new_events;
	view->stars = change_count[cpu];

out:
	if (actual_seq) {
		view->has_actual = true;
		view->actual_khz = history->actual_freq_khz;
		view->actual_is_initial = false;
		has_ebpf_actual[cpu] = true;
		ebpf_actual_khz[cpu] = history->actual_freq_khz;
		view->actual_ts_ns = history->actual_ts_ns;
		if (!view->has_event || view->actual_ts_ns > view->latest_ts_ns)
			view->latest_ts_ns = view->actual_ts_ns;
	}
}

static void
format_ghz(char *buf, size_t size, bool has_value, __u32 freq_khz)
{
	if (!has_value) {
		snprintf(buf, size, " - ");
		return;
	}

	snprintf(buf, size, "%2.1f", (double)freq_khz / 1000000.0);
}

static void
format_ghz_display(char *buf, size_t size, bool has_value, __u32 freq_khz, bool initial_value)
{
	char plain[8];

	format_ghz(plain, sizeof(plain), has_value, freq_khz);
	if (use_color && has_value && initial_value)
		snprintf(buf, size, "%s%s%s", ANSI_BLUE, plain, ANSI_RESET);
	else
		snprintf(buf, size, "%s", plain);
}

static void
format_init_summary(char *buf, size_t size, const struct core_view *view)
{
	const char *sep = "";
	size_t off = 0;

	if (!view->min_is_initial && !view->actual_is_initial && !view->max_is_initial) {
		snprintf(buf, size, "init:none");
		return;
	}

	off += snprintf(buf + off, off < size ? size - off : 0, "init:");

	if (view->min_is_initial) {
		off += snprintf(buf + off, off < size ? size - off : 0, "%smin", sep);
		sep = ",";
	}
	if (view->actual_is_initial) {
		off += snprintf(buf + off, off < size ? size - off : 0, "%sact", sep);
		sep = ",";
	}
	if (view->max_is_initial)
		snprintf(buf + off, off < size ? size - off : 0, "%smax", sep);
}

static void
format_stars(char *buf, size_t size, __u64 stars)
{
	__u64 i;
	char count_buf[32];
	int count_len;
	int star_len;
	size_t off = 0;

	if (!stars) {
		buf[0] = '-';
		buf[1] = '\0';
		return;
	}

	if (stars <= STAR_PLAIN_MAX) {
		for (i = 0; i < stars && i < size - 1; i++)
			buf[i] = '*';
		buf[i] = '\0';
		return;
	}

	count_len = snprintf(count_buf, sizeof(count_buf), "%llu", (unsigned long long)stars);
	if (count_len < 0) {
		buf[0] = '\0';
		return;
	}

	/* Fixed 20-char field: <stars>... <count>, count right-aligned. */
	star_len = STAR_COL_WIDTH - 4 - count_len;
	if (star_len > STAR_PLAIN_MAX)
		star_len = STAR_PLAIN_MAX;
	if (star_len < 0)
		star_len = 0;

	for (i = 0; i < (unsigned int)star_len && off < size - 1; i++)
		buf[off++] = '*';

	if (off < size - 1)
		off += snprintf(buf + off, size - off, "... %s", count_buf);
	else
		buf[size - 1] = '\0';
}

static void
format_age(char *buf, size_t size, bool has_event, __u64 now_ns, __u64 ts_ns)
{
	__u64 delta_ns;
	__u64 sec;

	if (!has_event) {
		snprintf(buf, size, "  -  ");
		return;
	}

	delta_ns = now_ns > ts_ns ? now_ns - ts_ns : 0;
	sec = delta_ns / 1000000000ULL;

	if (sec < 1)
		snprintf(buf, size, " <1s ");
	else if (sec < 60)
		snprintf(buf, size, "%3llus", sec);
	else if (sec < 3600)
		snprintf(buf, size, "%2llum%02llus", sec / 60, sec % 60);
	else
		snprintf(buf, size, "%2lluh%02llum", sec / 3600, (sec % 3600) / 60);
}

static void
appendf(char *buf, size_t size, size_t *off, const char *fmt, ...)
{
	va_list args;
	int n;

	if (*off >= size)
		return;

	va_start(args, fmt);
	n = vsnprintf(buf + *off, size - *off, fmt, args);
	va_end(args);

	if (n < 0)
		return;

	if ((size_t)n >= size - *off)
		*off = size;
	else
		*off += n;
}

static const char *
pick_comm_color(const char *comm)
{
	if (!env.allowed_comm[0] || !comm || strcmp(comm, "-") == 0)
		return NULL;

	if (strcmp(comm, env.allowed_comm) == 0)
		return ANSI_GREEN;

	return ANSI_RED;
}

static bool
is_unwanted_comm(const char *comm)
{
	if (!env.allowed_comm[0] || !comm || strcmp(comm, "-") == 0)
		return false;

	return strcmp(comm, env.allowed_comm) != 0;
}

static void
format_comm_display(char *buf, size_t size, const char *comm)
{
	/* In non-color terminals, bracket unwanted names so they still pop. */
	if (!use_color && is_unwanted_comm(comm)) {
		snprintf(buf, size, "!%-14.14s!", comm);
		return;
	}

	snprintf(buf, size, "%-16.16s", comm);
}

static int
detail_bin_cmp(const void *a, const void *b)
{
	const struct detail_bin *ba = a;
	const struct detail_bin *bb = b;

	if (ba->freq_khz < bb->freq_khz)
		return -1;
	if (ba->freq_khz > bb->freq_khz)
		return 1;
	return 0;
}

static void
detail_hist_add_bin(struct detail_hist *hist, __u32 freq_khz, __u64 count)
{
	int i;

	for (i = 0; i < hist->nr_bins; i++) {
		if (hist->bins[i].freq_khz == freq_khz) {
			hist->bins[i].count += count;
			return;
		}
	}

	if (hist->nr_bins >= MAX_DETAIL_BINS) {
		hist->overflow = true;
		return;
	}

	hist->bins[hist->nr_bins].freq_khz = freq_khz;
	hist->bins[hist->nr_bins].count = count;
	hist->nr_bins++;
}

static bool
detail_hist_set_bin_count(struct detail_hist *hist, __u32 freq_khz, __u64 count)
{
	int i;

	for (i = 0; i < hist->nr_bins; i++) {
		if (hist->bins[i].freq_khz == freq_khz) {
			hist->bins[i].count = count;
			return true;
		}
	}

	return false;
}

/* Adds one frequency as a zero-count bin to every histogram type. */
static void
seed_zero_bin(struct detail_hist hists[DETAIL_TYPES], __u32 freq_khz)
{
	int type;

	for (type = 0; type < DETAIL_TYPES; type++)
		detail_hist_add_bin(&hists[type], freq_khz, 0);
}

static int
collect_detail_histograms(int cpu, struct detail_hist hists[DETAIL_TYPES])
{
	struct freq_hist_key key, next_key;
	int err, i;
	bool has_key = false;

	memset(hists, 0, sizeof(struct detail_hist) * DETAIL_TYPES);
	if (freq_bins_fd < 0)
		return -ENOENT;

	/*
	 * Pre-seed every known P-state frequency as a zero-count bin for all
	 * three histogram types.  This fixes the vertical height of the display
	 * from the very first refresh and ensures rows never appear or disappear
	 * as new frequencies are observed at runtime.
	 */
	for (i = 0; i < nr_avail_freqs[cpu]; i++)
		seed_zero_bin(hists, avail_freqs_khz[cpu][i]);

	/* No startup frequency table: fall back to the individual sysfs values. */
	if (!nr_avail_freqs[cpu]) {
		if (has_initial_min[cpu])
			seed_zero_bin(hists, initial_min_khz[cpu]);
		if (has_initial_max[cpu])
			seed_zero_bin(hists, initial_max_khz[cpu]);
		if (has_initial_cur[cpu])
			seed_zero_bin(hists, initial_cur_khz[cpu]);
	}

	while (true) {
		err = bpf_map_get_next_key(freq_bins_fd, has_key ? &key : NULL, &next_key);
		if (err < 0) {
			if (errno == ENOENT)
				break;
			return -errno;
		}

		if (next_key.req_type < DETAIL_TYPES &&
				(int)next_key.cpu == (next_key.req_type == FREQ_REQ_ACTUAL ? cpu : policy_cpu[cpu])) {
			__u64 count = 0;

			if (bpf_map_lookup_elem(freq_bins_fd, &next_key, &count) == 0) {
				if (!detail_hist_set_bin_count(&hists[next_key.req_type], next_key.freq_khz, count))
					detail_hist_add_bin(&hists[next_key.req_type], next_key.freq_khz, count);
			}
		}

		key = next_key;
		has_key = true;
	}

	for (i = 0; i < DETAIL_TYPES; i++) {
		if (hists[i].nr_bins > 1)
			qsort(hists[i].bins, hists[i].nr_bins, sizeof(hists[i].bins[0]), detail_bin_cmp);
	}

	return 0;
}

/*
 * Side-by-side histogram renderer.
 *
 * When startup frequency steps are available from sysfs, those rows define the
 * fixed histogram height for the entire run. Otherwise we fall back to the
 * frequencies present in the collected histogram data.
 *
 * Cell format: "X.X GHz |<bar padded to BAR_W> <6-digit count>"
 */
#define COL_SEP " | "
#define COL_BAR_W 20
#define MAX_UNION_BINS (MAX_DETAIL_BINS * DETAIL_TYPES)
/* prefix "X.X GHz |" = 9, bar = COL_BAR_W, " " = 1, count = 6 */
#define COL_INNER (9 + COL_BAR_W + 1 + 6) /* 36 */

static int
build_hist_union(int cpu, const struct detail_hist *cols[DETAIL_TYPES], __u32 *union_freqs, int max_union)
{
	int nr_union = 0;
	int c, k;

	for (k = 0; k < nr_avail_freqs[cpu] && nr_union < max_union; k++)
		union_freqs[nr_union++] = avail_freqs_khz[cpu][k];

	for (c = 0; c < DETAIL_TYPES; c++) {
		for (k = 0; k < cols[c]->nr_bins; k++) {
			__u32 freq_khz = cols[c]->bins[k].freq_khz;
			bool found = false;
			int i;

			for (i = 0; i < nr_union; i++) {
				if (union_freqs[i] == freq_khz) {
					found = true;
					break;
				}
			}
			if (!found && nr_union < max_union)
				union_freqs[nr_union++] = freq_khz;
		}
	}

	for (k = 1; k < nr_union; k++) {
		__u32 freq_khz = union_freqs[k];
		int i = k - 1;

		while (i >= 0 && union_freqs[i] > freq_khz) {
			union_freqs[i + 1] = union_freqs[i];
			i--;
		}
		union_freqs[i + 1] = freq_khz;
	}

	return nr_union;
}

/* Look up a bin count by frequency; returns 0 if not present. */
static __u64
hist_lookup(__u32 freq_khz, const struct detail_hist *hist)
{
	int i;

	for (i = 0; i < hist->nr_bins; i++) {
		if (hist->bins[i].freq_khz == freq_khz)
			return hist->bins[i].count;
	}
	return 0;
}

/* Render one histogram cell (COL_INNER chars, no newline). */
static void
render_hist_cell(char *cell, __u32 freq_khz, __u64 count, __u64 max_count)
{
	char bar[COL_BAR_W + 1];
	int w = 0;
	int j;

	if (count && max_count)
		w = (int)((count * COL_BAR_W) / max_count);
	if (w < 1 && count)
		w = 1;
	if (w > COL_BAR_W)
		w = COL_BAR_W;

	for (j = 0; j < w; j++)
		bar[j] = '*';
	bar[w] = '\0';

	snprintf(cell,
			COL_INNER + 1,
			"%3.1f GHz |%-*s %6llu",
			(double)freq_khz / 1000000.0,
			COL_BAR_W,
			bar,
			(unsigned long long)count);
}

static void
print_hist_columns(char *buf,
		size_t size,
		size_t *off,
		int cpu,
		const struct detail_hist *hmin,
		const struct detail_hist *hact,
		const struct detail_hist *hmax)
{
	__u32 union_freqs[MAX_UNION_BINS];
	int nr_union;
	const struct detail_hist *cols[DETAIL_TYPES] = { hmin, hact, hmax };
	__u64 max_count[DETAIL_TYPES] = { 0, 0, 0 };
	int c, k, r;

	nr_union = build_hist_union(cpu, cols, union_freqs, MAX_UNION_BINS);

	for (c = 0; c < DETAIL_TYPES; c++) {
		for (k = 0; k < cols[c]->nr_bins; k++) {
			if (cols[c]->bins[k].count > max_count[c])
				max_count[c] = cols[c]->bins[k].count;
		}
	}

	/* Header */
	appendf(buf,
			size,
			off,
			"%-*s%s%-*s%s%-*s\n",
			COL_INNER,
			"-- min requests --",
			COL_SEP,
			COL_INNER,
			"-- actual freq --",
			COL_SEP,
			COL_INNER,
			"-- max requests --");

	if (nr_union == 0) {
		appendf(buf, size, off, "(no samples)\n\n");
		return;
	}

	for (r = 0; r < nr_union; r++) {
		__u32 f = union_freqs[r];
		char cell[DETAIL_TYPES][COL_INNER + 1];

		for (c = 0; c < DETAIL_TYPES; c++)
			render_hist_cell(cell[c], f, hist_lookup(f, cols[c]), max_count[c]);

		appendf(buf, size, off, "%s%s%s%s%s\n", cell[0], COL_SEP, cell[1], COL_SEP, cell[2]);
	}
	if (hmin->overflow || hact->overflow || hmax->overflow)
		appendf(buf,
				size,
				off,
				"warning: histogram has more than %d bins; some rows are hidden\n",
				MAX_DETAIL_BINS);
	appendf(buf, size, off, "\n");
}

static void
print_recent_events(char *buf, size_t size, size_t *off, int cpu, __u64 now_ns)
{
	struct cpu_freq_history *history = &histories[cpu];
	__u64 seq = history->seq;
	__u64 start, i;
	int shown = 0;

	appendf(buf, size, off, "recent: seq  type  freq(GHz)  age   comm             pid\n");
	if (!seq) {
		appendf(buf, size, off, "  (none)\n\n");
		return;
	}

	start = seq > FREQ_HISTORY_LEN ? seq - FREQ_HISTORY_LEN : 0;
	for (i = seq; i > start && shown < DETAIL_MAX_EVENTS; i--) {
		struct freq_event *event = &history->events[(i - 1) % FREQ_HISTORY_LEN];
		char age[16];
		char comm_display[TASK_COMM_LEN + 1];
		const char *comm;
		const char *comm_color;

		if (event->seq != i || !event->ts_ns)
			continue;
		format_age(age, sizeof(age), true, now_ns, event->ts_ns);
		comm = event->comm[0] ? event->comm : "-";
		comm_color = pick_comm_color(comm);
		format_comm_display(comm_display, sizeof(comm_display), comm);

		appendf(buf,
				size,
				off,
				"       %4llu  %-6s  %5.3f  %5s  ",
				(unsigned long long)event->seq,
				req_type_name(event->req_type),
				(double)event->freq_khz / 1000000.0,
				age);
		if (use_color && comm_color)
			appendf(buf, size, off, "%s%s%s %u\n", comm_color, comm_display, ANSI_RESET, event->pid);
		else
			appendf(buf, size, off, "%s %u\n", comm_display, event->pid);
		shown++;
	}

	if (!shown)
		appendf(buf, size, off, "  (none)\n");
	appendf(buf, size, off, "\n");
}

static void
print_unique_process_names(char *buf, size_t size, size_t *off, int cpu, int max_names)
{
	int j;
	int display_count;

	if (unique_processes[cpu].count == 0) {
		appendf(buf, size, off, "unique processes: (none)\n");
		return;
	}

	display_count = unique_processes[cpu].count;
	if (max_names > 0 && display_count > max_names)
		display_count = max_names;

	appendf(buf, size, off, "unique processes (all-time, last %d):", display_count);
	for (j = unique_processes[cpu].count - display_count; j < unique_processes[cpu].count; j++) {
		const char *comm_color = pick_comm_color(unique_processes[cpu].names[j]);

		if (use_color && comm_color)
			appendf(buf, size, off, " %s%s%s", comm_color, unique_processes[cpu].names[j], ANSI_RESET);
		else if (!use_color && is_unwanted_comm(unique_processes[cpu].names[j]))
			appendf(buf, size, off, " !%s!", unique_processes[cpu].names[j]);
		else
			appendf(buf, size, off, " %s", unique_processes[cpu].names[j]);
	}
	appendf(buf, size, off, "\n");
}

static void
print_single_core_detail(char *buf, size_t size, size_t *off, int cpu, __u64 now_ns)
{
	struct core_view view;
	struct detail_hist hists[DETAIL_TYPES];
	char min_disp[32], act_disp[32], max_disp[32], age[16];
	char init_summary[32];
	char comm_display[TASK_COMM_LEN + 1];
	const char *last_comm;
	const char *comm_color;
	int err;

	update_unique_processes(cpu);
	build_core_view(cpu, &view);
	format_ghz_display(min_disp, sizeof(min_disp), view.has_min, view.min_khz, view.min_is_initial);
	format_ghz_display(act_disp, sizeof(act_disp), view.has_actual, view.actual_khz, view.actual_is_initial);
	format_ghz_display(max_disp, sizeof(max_disp), view.has_max, view.max_khz, view.max_is_initial);
	format_init_summary(init_summary, sizeof(init_summary), &view);
	format_age(age, sizeof(age), view.has_event, now_ns, view.latest_ts_ns);

	if (use_color)
		appendf(buf,
				size,
				off,
				"cpu %d  policy=%d  mode=%s  [min/act/max GHz]: %s / %s / %s  age:%s\n",
				cpu,
				policy_cpu[cpu],
				attach_method,
				min_disp,
				act_disp,
				max_disp,
				age);
	else
		appendf(buf,
				size,
				off,
				"cpu %d  policy=%d  mode=%s  [min/act/max GHz]: %s / %s / %s  %-*s  age:%s\n",
				cpu,
				policy_cpu[cpu],
				attach_method,
				min_disp,
				act_disp,
				max_disp,
				INIT_SUMMARY_WIDTH,
				init_summary,
				age);

	last_comm = view.last_comm[0] ? view.last_comm : "-";
	comm_color = pick_comm_color(last_comm);
	format_comm_display(comm_display, sizeof(comm_display), last_comm);

	appendf(buf,
			size,
			off,
			"req_changes:%llu  actual_changes:%llu  last_comm:",
			(unsigned long long)change_count[cpu],
			(unsigned long long)histories[cpu].actual_seq);
	if (use_color && comm_color)
		appendf(buf, size, off, "%s%s%s\n", comm_color, comm_display, ANSI_RESET);
	else
		appendf(buf, size, off, "%s\n", comm_display);
	appendf(buf, size, off, "\n");

	err = collect_detail_histograms(cpu, hists);
	if (err) {
		appendf(buf, size, off, "histogram unavailable: %s\n", strerror(-err));
		return;
	}

	print_hist_columns(buf, size, off, cpu, &hists[FREQ_REQ_MIN], &hists[FREQ_REQ_ACTUAL], &hists[FREQ_REQ_MAX]);

	print_recent_events(buf, size, off, cpu, now_ns);

	appendf(buf, size, off, "\n");
	print_unique_process_names(buf, size, off, cpu, 5);
}

/*
 * Formats everything on a grid row before the comm column. Called twice per
 * core: once with plain values to measure the visible width, once with the
 * (possibly ANSI-wrapped) display values that actually get printed.
 */
static int
format_core_prefix(char *buf,
		size_t size,
		int cpu,
		const char *min_ghz,
		const char *act_ghz,
		const char *max_ghz,
		const char *init_summary,
		const char *stars,
		const char *age)
{
	if (use_color)
		return snprintf(buf,
				size,
				"%3d [ %s/%s/%sGHz ] %-*s %-7s ",
				cpu,
				min_ghz,
				act_ghz,
				max_ghz,
				STAR_COL_WIDTH,
				stars,
				age);

	return snprintf(buf,
			size,
			"%3d [ %s/%s/%sGHz %-*s ] %-*s %-7s ",
			cpu,
			min_ghz,
			act_ghz,
			max_ghz,
			INIT_SUMMARY_WIDTH,
			init_summary,
			STAR_COL_WIDTH,
			stars,
			age);
}

static void
print_grid(char *buf, size_t size, size_t *off, __u64 now_ns, int grid_cols)
{
	int visible_cpus[MAX_CPU_NR];
	int nr_visible = 0;
	int cpu, row, col, rows;

	for (cpu = 0; cpu < nr_cpus; cpu++) {
		if (cpu_filter[cpu])
			visible_cpus[nr_visible++] = cpu;
	}

	if (!nr_visible)
		return;

	rows = (nr_visible + grid_cols - 1) / grid_cols;

	for (row = 0; row < rows; row++) {
		for (col = 0; col < grid_cols; col++) {
			struct core_view view;
			char min_ghz[8], act_ghz[8], max_ghz[8], stars[STAR_BUF_SIZE], age[16];
			char min_disp[32], act_disp[32], max_disp[32];
			char init_summary[32];
			char plain[128], display[256], comm_display[TASK_COMM_LEN + 1];
			const char *comm;
			const char *comm_color;
			int idx = col * rows + row;
			int prefix_len, total_visible, padding;

			if (idx >= nr_visible)
				continue;
			cpu = visible_cpus[idx];

			update_unique_processes(cpu);
			build_core_view(cpu, &view);
			format_ghz(min_ghz, sizeof(min_ghz), view.has_min, view.min_khz);
			format_ghz(act_ghz, sizeof(act_ghz), view.has_actual, view.actual_khz);
			format_ghz(max_ghz, sizeof(max_ghz), view.has_max, view.max_khz);
			format_ghz_display(min_disp, sizeof(min_disp), view.has_min, view.min_khz, view.min_is_initial);
			format_ghz_display(act_disp,
					sizeof(act_disp),
					view.has_actual,
					view.actual_khz,
					view.actual_is_initial);
			format_ghz_display(max_disp, sizeof(max_disp), view.has_max, view.max_khz, view.max_is_initial);
			format_init_summary(init_summary, sizeof(init_summary), &view);
			format_stars(stars, sizeof(stars), view.stars);
			format_age(age, sizeof(age), view.has_event, now_ns, view.latest_ts_ns);
			comm = view.last_comm[0] ? view.last_comm : "-";
			comm_color = pick_comm_color(comm);
			format_comm_display(comm_display, sizeof(comm_display), comm);

			prefix_len = format_core_prefix(
					plain, sizeof(plain), cpu, min_ghz, act_ghz, max_ghz, init_summary, stars, age);
			if (prefix_len < 0)
				prefix_len = 0;

			format_core_prefix(display,
					sizeof(display),
					cpu,
					min_disp,
					act_disp,
					max_disp,
					init_summary,
					stars,
					age);
			appendf(buf, size, off, "%s", display);
			if (use_color && comm_color)
				appendf(buf, size, off, "%s%s%s", comm_color, comm_display, ANSI_RESET);
			else
				appendf(buf, size, off, "%s", comm_display);

			total_visible = prefix_len + TASK_COMM_LEN;
			padding = CELL_WIDTH - total_visible;
			if (padding < 0)
				padding = 0;
			appendf(buf, size, off, "%*s", padding, "");
		}
		appendf(buf, size, off, "\n");
	}
}

static void
append_drop_warnings(char *buf, size_t size, size_t *off)
{
	if (dropped_hist_bins)
		appendf(buf,
				size,
				off,
				"warning: dropped %llu histogram bin updates\n\n",
				(unsigned long long)dropped_hist_bins);
	if (dropped_events)
		appendf(buf,
				size,
				off,
				"warning: dropped %llu frequency events\n\n",
				(unsigned long long)dropped_events);
	if (dropped_requests)
		appendf(buf,
				size,
				off,
				"warning: dropped %llu accepted request correlations\n\n",
				(unsigned long long)dropped_requests);
}

static void
render_snapshot(void)
{
	__u64 now_ns = monotonic_ns();
	char wall_time[16];
	size_t off = 0, out_off = 0;
	size_t i;
	bool at_line_start = true;
	int line_count = 0;

	format_wall_time(wall_time, sizeof(wall_time));

	if (single_core_mode) {
		appendf(frame,
				sizeof(frame),
				&off,
				"freqtracker: refresh=%ds history=%d time=%s\n\n",
				env.interval,
				FREQ_HISTORY_LEN,
				wall_time);
		append_drop_warnings(frame, sizeof(frame), &off);
		print_single_core_detail(frame, sizeof(frame), &off, selected_cpu, now_ns);
	} else {
		appendf(frame,
				sizeof(frame),
				&off,
				"freqtracker: mode=%s refresh=%ds history=%d cols=%d time=%s\n",
				attach_method,
				env.interval,
				FREQ_HISTORY_LEN,
				env.grid_cols,
				wall_time);
		appendf(frame, sizeof(frame), &off, "core [ min/act/max GHz ] changes age last_comm (");
		if (use_color)
			appendf(frame, sizeof(frame), &off, "%sblue%s=init)\n\n", ANSI_BLUE, ANSI_RESET);
		else
			appendf(frame,
					sizeof(frame),
					&off,
					"no-color: init shown as init:min,act,max or init:none)\n\n");
		append_drop_warnings(frame, sizeof(frame), &off);
		print_grid(frame, sizeof(frame), &off, now_ns, env.grid_cols);
	}
	if (off > sizeof(frame))
		off = sizeof(frame);

	if (env.no_clear) {
		fwrite(frame, 1, off, stdout);
		fflush(stdout);
		first_pass = false;
		return;
	}

	appendf(out, sizeof(out), &out_off, "\033[H");
	for (i = 0; i < off; i++) {
		if (at_line_start)
			appendf(out, sizeof(out), &out_off, "\033[2K");

		appendf(out, sizeof(out), &out_off, "%c", frame[i]);
		if (frame[i] == '\n') {
			line_count++;
			at_line_start = true;
		} else {
			at_line_start = false;
		}
	}

	for (i = line_count; i < (size_t)prev_render_lines; i++)
		appendf(out, sizeof(out), &out_off, "\033[2K\n");

	if (out_off > sizeof(out))
		out_off = sizeof(out);
	fwrite(out, 1, out_off, stdout);
	fflush(stdout);
	prev_render_lines = line_count;

	first_pass = false;
}

/* Everything main() does before it needs a BPF skeleton. */
static int
setup_runtime(void)
{
	int err;

	use_color = isatty(STDOUT_FILENO);
	if (!use_color)
		env.no_clear = true;

	nr_cpus = libbpf_num_possible_cpus();
	if (nr_cpus < 0) {
		fprintf(stderr, "failed to get # of possible cpus: %s\n", strerror(-nr_cpus));
		return nr_cpus;
	}

	err = init_cpu_filter();
	if (err) {
		const char *spec = env.cpu_list ? env.cpu_list : "";

		if (err == -ENOMEM)
			fprintf(stderr, "failed to parse CPU list: out of memory\n");
		else
			fprintf(stderr, "invalid CPU list '%s' for [0, %d]\n", spec, nr_cpus - 1);
		return err;
	}

	err = update_selected_cpu_mode();
	if (err)
		return err;

	init_policy_topology();

	if (single_core_mode)
		fprintf(stderr, "single-core detail mode enabled for cpu %d\n", selected_cpu);

	init_sysfs_freq_bounds();

	return 0;
}

/* Resolves the three map fds the render loop reads from. */
static int
init_map_fds(struct freqtracker_bpf *obj, int *events_fd)
{
	struct bpf_map *stats_map;

	*events_fd = bpf_map__fd(obj->maps.events);
	if (*events_fd < 0) {
		fprintf(stderr, "failed to get events map fd: %s\n", strerror(-*events_fd));
		return *events_fd;
	}

	freq_bins_fd = bpf_map__fd(obj->maps.freq_bins);
	if (freq_bins_fd < 0) {
		fprintf(stderr, "failed to get freq_bins map fd: %s\n", strerror(-freq_bins_fd));
		return freq_bins_fd;
	}

	stats_map = bpf_object__find_map_by_name(obj->obj, "freq_stats");
	if (!stats_map) {
		fprintf(stderr, "failed to find freq_stats map\n");
		return -ENOENT;
	}

	freq_stats_fd = bpf_map__fd(stats_map);
	if (freq_stats_fd < 0) {
		fprintf(stderr, "failed to get freq_stats map fd: %s\n", strerror(-freq_stats_fd));
		return freq_stats_fd;
	}

	return 0;
}

static int
install_signal_handlers(void)
{
	if (signal(SIGINT, sig_handler) == SIG_ERR || signal(SIGTERM, sig_handler) == SIG_ERR ||
			signal(SIGQUIT, fatal_sig_handler) == SIG_ERR || signal(SIGHUP, fatal_sig_handler) == SIG_ERR) {
		int err = errno; /* fprintf() may clobber errno */

		fprintf(stderr, "failed to install signal handler: %s\n", strerror(err));
		return -err;
	}

	return 0;
}

static void
hide_cursor(void)
{
	if (env.no_clear || !use_color)
		return;

	printf("\033[2J\033[H" ANSI_HIDE_CURSOR);
	cursor_hidden = true;
	atexit(restore_terminal);
}

// LCOV_EXCL_START
/* Destroys obj and reopens/loads it in kprobe mode; NULL on failure. */
static struct freqtracker_bpf *
reload_as_kprobe(struct freqtracker_bpf *obj, struct bpf_object_open_opts *open_opts)
{
	int err;

	freqtracker_bpf__destroy(obj);
	obj = freqtracker_bpf__open_opts(open_opts);
	if (!obj) {
		fprintf(stderr, "failed to reopen BPF object\n");
		return NULL;
	}

	configure_attach_autoload(obj, ATTACH_MODE_KPROBE);
	err = freqtracker_bpf__load(obj);
	if (err) {
		fprintf(stderr, "failed to load BPF object in kprobe/kretprobe mode: %d\n", err);
		freqtracker_bpf__destroy(obj);
		return NULL;
	}

	return obj;
}

int
main(int argc, char **argv)
{
	enum attach_mode requested_mode;
	static const struct argp argp = {
		.options = opts,
		.parser = parse_arg,
		.doc = argp_program_doc,
	};
	struct freqtracker_bpf *obj = NULL;
	int map_fd, err = 0;

	DECLARE_LIBBPF_OPTS(bpf_object_open_opts, open_opts);
	if (resolve_attach_mode(&requested_mode))
		return EXIT_FAILURE;

	err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
	if (err)
		return err;

	libbpf_set_print(libbpf_print_fn);

	if (setup_runtime())
		return EXIT_FAILURE;

	err = ensure_core_btf(&open_opts);
	if (err) {
		fprintf(stderr, "failed to fetch CO-RE BTF: %s\n", strerror(-err));
		return EXIT_FAILURE;
	}

	obj = freqtracker_bpf__open_opts(&open_opts);
	if (!obj) {
		fprintf(stderr, "failed to open BPF object\n");
		return EXIT_FAILURE;
	}

	if (requested_mode == ATTACH_MODE_AUTO) {
		configure_attach_autoload(obj, ATTACH_MODE_FEXIT);
		err = freqtracker_bpf__load(obj);
		if (err && is_permission_error(err) && geteuid() != 0) {
			fprintf(stderr,
					"failed to load BPF programs: %s\n"
					"hint: freqtracker needs to run as root, or with CAP_BPF and CAP_PERFMON.\n",
					strerror(-err));
			goto cleanup;
		}
		if (err) {
			fprintf(stderr,
					"fexit load failed (%d: %s), falling back to kprobe/kretprobe. "
					"Set FREQTRACKER_ATTACH=fexit to require fexit.\n",
					err,
					strerror(-err));
			obj = reload_as_kprobe(obj, &open_opts);
			if (!obj)
				return EXIT_FAILURE;
		}
	} else {
		configure_attach_autoload(obj, requested_mode);
		err = freqtracker_bpf__load(obj);
		if (err) {
			if (is_permission_error(err) && geteuid() != 0) {
				// clang-format off
				fprintf(stderr,
						"failed to load BPF programs: %s\n"
						"hint: freqtracker needs to run as root, or with CAP_BPF and CAP_PERFMON.\n",
						strerror(-err));
				// clang-format on
			} else if (requested_mode == ATTACH_MODE_FEXIT) {
				fprintf(stderr,
						"failed to load BPF object in fexit mode: %s\n"
						"hint: upgrade libbpf for newer kernel BTF support.\n",
						strerror(-err));
			} else {
				fprintf(stderr, "failed to load BPF object: %s\n", strerror(-err));
			}
			goto cleanup;
		}
	}

	err = freqtracker_bpf__attach(obj);
	if (err && requested_mode == ATTACH_MODE_AUTO && strcmp(attach_method, "fexit") == 0) {
		fprintf(stderr,
				"fexit attach failed (%s), falling back to kprobe/kretprobe. "
				"Set FREQTRACKER_ATTACH=fexit to require fexit.\n",
				strerror(-err));
		obj = reload_as_kprobe(obj, &open_opts);
		if (!obj)
			return EXIT_FAILURE;
		err = freqtracker_bpf__attach(obj);
	}
	if (err) {
		fprintf(stderr, "failed to attach BPF programs: %s\n", strerror(-err));
		goto cleanup;
	}

	err = init_map_fds(obj, &map_fd);
	if (err)
		goto cleanup;

	/* Install first: nothing would restore the cursor if a signal landed between the two. */
	err = install_signal_handlers();
	if (err)
		goto cleanup;

	hide_cursor();

	while (!exiting) {
		err = collect_events(map_fd);
		if (err) {
			fprintf(stderr, "failed to read events map: %s\n", strerror(-err));
			break;
		}
		collect_stats();
		render_snapshot();
		sleep(env.interval);
	}

cleanup:
	restore_terminal();
	freqtracker_bpf__destroy(obj);
	return err ? EXIT_FAILURE : EXIT_SUCCESS;
}
// LCOV_EXCL_STOP
