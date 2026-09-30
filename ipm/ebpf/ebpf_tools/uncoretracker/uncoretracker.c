/*
 * SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Intel Corporation
 */

/*
 * uncoretracker.c - live view of per-package/die uncore frequency limits
 * (min/max/current) plus who last changed each limit and to what value.
 *
 * min/max writes are observed via eBPF (fexit hooks on the
 * intel_uncore_frequency driver's write path record pid/comm/timestamp/
 * value into a map); current/min/max are polled from sysfs on a timer.
 *
 * Run with -h for usage.
 */

#define _GNU_SOURCE
#include <argp.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <bpf/bpf.h>
#include <bpf/btf.h>
#include <bpf/libbpf.h>
#include "uncoretracker.h"
#include "uncoretracker.skel.h"

#define UNCORE_BASE_DIR "/sys/devices/system/cpu/intel_uncore_frequency"

#define ANSI_RESET "\033[0m"
#define ANSI_RED "\033[31m"
#define ANSI_GREEN "\033[32m"

#define MAX_UNIQUE_WRITERS 5

static struct env {
	int interval;
	bool no_clear;
	bool verbose;
	char allowed_comm[UNCORE_COMM_LEN];
} env = {
	.interval = 1,
};

static volatile sig_atomic_t exiting;
static bool use_color;

struct cluster_entry {
	char sysfs_dir[512];
	char name[256]; /* basename, e.g. "package_00_die_00" or "uncore00" */
	char agent_types[64]; /* "core", "io", "memory", "cache" or "N/A" */
	int pkg_id;
	int die_id; /* real per-die id; used to key BPF write-event lookups */
	int domain_id; /* TPMI per-package domain/cluster index, else -1; shown as a note */
	int cluster_id; /* fabric_cluster_id if present, else -1 */
};

static struct cluster_entry clusters[MAX_UNCORE_CLUSTERS];
static int nr_clusters;
static bool cursor_hidden;
static int cluster_col_width;

/* Warning message for missing writer tracking due to kernel limitations */
static char writer_tracking_warning[384];

/* Every distinct comm seen writing min/max for a cluster, oldest-evicted-first once full. */
struct unique_writer_list {
	char names[MAX_UNIQUE_WRITERS][UNCORE_COMM_LEN];
	int count;
};

static struct unique_writer_list unique_min_writers[MAX_UNCORE_CLUSTERS];
static struct unique_writer_list unique_max_writers[MAX_UNCORE_CLUSTERS];

static const char argp_program_doc[] =
		"Track per-package/die uncore frequency limits (min/max/current) and who last "
		"changed each limit.\n"
		"\n"
		"USAGE: uncoretracker [--help] [-i SEC] [-C] [-a COMM] [-v]\n"
		"\n"
		"EXAMPLES:\n"
		"    uncoretracker        # live view, refresh every second\n"
		"    uncoretracker -i 2   # refresh every 2 seconds\n"
		"    uncoretracker -C     # do not clear terminal between refreshes\n"
		"    uncoretracker -a myapp  # highlight 'myapp' green as the expected actor; anyone else red\n";

static const struct argp_option opts[] = {
	{ "interval", 'i', "SEC", 0, "Refresh interval in seconds", 0 },
	{ "no-clear", 'C', NULL, 0, "Do not clear terminal each refresh", 0 },
	// clang-format off
	{ "allowed",
			'a',
			"COMM",
			0,
			"Expected process name to color green as the 'good' actor uses kernel task comm format "
			"(16 bytes total, including trailing NUL; max 15 visible chars); any other writer is colored red",
			0 },
	// clang-format on
	{ "verbose", 'v', NULL, 0, "Verbose debug output", 0 },
	{ NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help", 0 },
	{},
};

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
		case 'C':
			env.no_clear = true;
			break;
		case 'a':
			if (!arg || arg[0] == '\0') {
				fprintf(stderr, "invalid allowed process name: %s\n", arg ? arg : "(null)");
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

static const struct argp argp = {
	.options = opts,
	.parser = parse_arg,
	.doc = argp_program_doc,
};

static int
libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	if (level == LIBBPF_DEBUG && !env.verbose)
		return 0;

	return vfprintf(stderr, format, args);
}

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

	printf("\033[?25h");
	fflush(stdout);
	cursor_hidden = false;
}

/*
 * kernel_has_function - true if /proc/kallsyms has a text symbol (type
 * 't' or 'T') with this exact name.
 *
 * Used to pick between the two mutually exclusive shapes of the uncore
 * frequency sysfs write path across kernel/compiler versions: on older
 * kernels uncore_write_control_freq() is its own function, on newer ones
 * it is fully inlined into its caller uncore_write() and no longer
 * exists as a symbol at all (see uncoretracker.bpf.c).
 */
static int
kernel_has_function(const char *name)
{
	FILE *f = fopen("/proc/kallsyms", "r");
	char line[256];
	int found = 0;

	if (!f)
		return 0;

	while (fgets(line, sizeof(line), f)) {
		char type;
		char sym[256];

		if (sscanf(line, "%*s %c %255s", &type, sym) != 2)
			continue;
		if ((type == 't' || type == 'T') && strcmp(sym, name) == 0) {
			found = 1;
			break;
		}
	}
	fclose(f);
	return found;
}

static int
sysfs_read_int(const char *path, int *out)
{
	FILE *f = fopen(path, "r");
	int rc;

	if (!f)
		return -1;
	rc = fscanf(f, "%d", out);
	fclose(f);
	return (rc == 1) ? 0 : -1;
}

/*
 * struct_missing_fields - true if struct_name is defined in the BTF of any
 * of the given candidate kernel modules but at least one of the given
 * field names is absent from it; false if no candidate module defines
 * struct_name at all, or if every field is present wherever it is found.
 * missing (if non-NULL) is filled with a comma-separated list of the
 * absent field names.
 *
 * Used to detect a driver build whose 'struct uncore_data' predates
 * package_id/die_id/domain_id: the BPF fexit hooks' CO-RE reads of those
 * fields would otherwise silently fail (or fail BPF verification), so
 * this is checked from user-space up front to give a clear warning.
 */
static bool
struct_missing_fields(const char *const *module_candidates,
		int n_module_candidates,
		const char *struct_name,
		const char *const *field_names,
		int nfields,
		char *missing,
		size_t missing_sz)
{
	struct btf *vmlinux_btf, *mod_btf = NULL;
	const struct btf_type *t;
	struct btf_member *members;
	__s32 type_id = -1;
	int vlen;
	bool any_missing = false;
	size_t off = 0;

	if (missing && missing_sz)
		missing[0] = '\0';

	vmlinux_btf = btf__load_vmlinux_btf();
	if (libbpf_get_error(vmlinux_btf))
		return false;

	for (int m = 0; m < n_module_candidates; m++) {
		struct btf *candidate = btf__load_module_btf(module_candidates[m], vmlinux_btf);

		if (libbpf_get_error(candidate))
			continue;

		type_id = btf__find_by_name_kind(candidate, struct_name, BTF_KIND_STRUCT);
		if (type_id >= 0) {
			mod_btf = candidate;
			break;
		}
		btf__free(candidate);
	}

	if (!mod_btf) {
		btf__free(vmlinux_btf);
		return false;
	}

	t = btf__type_by_id(mod_btf, type_id);
	members = btf_members(t);
	vlen = btf_vlen(t);

	for (int i = 0; i < nfields; i++) {
		bool found = false;

		for (int j = 0; j < vlen; j++) {
			const char *name = btf__name_by_offset(mod_btf, members[j].name_off);

			if (name && strcmp(name, field_names[i]) == 0) {
				found = true;
				break;
			}
		}
		if (!found) {
			any_missing = true;
			if (missing && off < missing_sz) {
				int n = snprintf(missing + off, missing_sz - off, off ? ", %s" : "%s", field_names[i]);

				if (n > 0 && (size_t)n < missing_sz - off)
					off += (size_t)n;
			}
		}
	}

	btf__free(mod_btf);
	btf__free(vmlinux_btf);
	return any_missing;
}

/*
 * enumerate_clusters - find every sysfs entry under UNCORE_BASE_DIR that
 * has a readable min_freq_khz. Prefers per-cluster "uncoreXX" entries
 * (TPMI); the legacy "package_NN_die_MM" aggregate entries are only used as
 * a fallback when no uncoreXX entries exist at all (MSR hosts), since on
 * TPMI hosts they duplicate what their uncoreXX siblings already report.
 */
static int
enumerate_clusters(void)
{
	DIR *d;
	struct dirent *ent;
	char names[MAX_UNCORE_CLUSTERS][256];
	bool is_uncore[MAX_UNCORE_CLUSTERS];
	int nr_candidates = 0, nr_uncore = 0;

	nr_clusters = 0;

	d = opendir(UNCORE_BASE_DIR);
	if (!d) {
		fprintf(stderr, "opendir %s: %s\n", UNCORE_BASE_DIR, strerror(errno));
		return -1;
	}

	while ((ent = readdir(d)) != NULL && nr_candidates < MAX_UNCORE_CLUSTERS) {
		char tmp[640];
		int probe;

		if (ent->d_name[0] == '.')
			continue;

		snprintf(tmp, sizeof(tmp), "%s/%s/min_freq_khz", UNCORE_BASE_DIR, ent->d_name);
		if (sysfs_read_int(tmp, &probe) != 0)
			continue;

		snprintf(names[nr_candidates], sizeof(names[0]), "%s", ent->d_name);
		is_uncore[nr_candidates] = strncmp(ent->d_name, "uncore", strlen("uncore")) == 0;
		nr_uncore += is_uncore[nr_candidates];
		nr_candidates++;
	}
	closedir(d);

	/* GCC can't see that names[i] is bounded to 256 bytes once indexed by a
	 * loop variable, and warns every snprintf() below as if it could be huge. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-truncation"
	for (int i = 0; i < nr_candidates && nr_clusters < MAX_UNCORE_CLUSTERS; i++) {
		struct cluster_entry *ce = &clusters[nr_clusters];
		char tmp[640];

		/* Once any uncoreXX entry exists, its package_NN_die_MM sibling(s)
		 * would only duplicate the same writes as a separate row. */
		if (nr_uncore > 0 && !is_uncore[i])
			continue;

		snprintf(ce->sysfs_dir, sizeof(ce->sysfs_dir), "%s/%s", UNCORE_BASE_DIR, names[i]);
		snprintf(ce->name, sizeof(ce->name), "%s", names[i]);

		ce->pkg_id = -1;
		snprintf(tmp, sizeof(tmp), "%s/%s/package_id", UNCORE_BASE_DIR, names[i]);
		sysfs_read_int(tmp, &ce->pkg_id);

		/* The "die_id" attribute is only present for domains with core agents,
		 * so read it first; domain_id (the TPMI per-package domain/cluster
		 * index) is tracked separately below purely for display. */
		ce->die_id = -1;
		snprintf(tmp, sizeof(tmp), "%s/%s/die_id", UNCORE_BASE_DIR, names[i]);
		sysfs_read_int(tmp, &ce->die_id);

		ce->domain_id = -1;
		snprintf(tmp, sizeof(tmp), "%s/%s/domain_id", UNCORE_BASE_DIR, names[i]);
		sysfs_read_int(tmp, &ce->domain_id);

		/* MSR-backed entries have no package_id/die_id attribute files; the
		 * driver only encodes them in the directory name itself. */
		if (ce->pkg_id < 0 || ce->die_id < 0) {
			int scanned_pkg, scanned_die;
			if (sscanf(names[i], "package_%d_die_%d", &scanned_pkg, &scanned_die) == 2) {
				ce->pkg_id = scanned_pkg;
				ce->die_id = scanned_die;
			}
		}

		/* Non-core TPMI domains (io/memory/cache agents) have no die_id
		 * attribute at all; today's TPMI parts are single-die per package,
		 * so default to die 0 rather than mistaking the domain/cluster
		 * index for a die number. */
		if (ce->die_id < 0 && ce->domain_id >= 0)
			ce->die_id = 0;

		ce->cluster_id = -1;
		snprintf(tmp, sizeof(tmp), "%s/%s/fabric_cluster_id", UNCORE_BASE_DIR, names[i]);
		sysfs_read_int(tmp, &ce->cluster_id);

		snprintf(ce->agent_types, sizeof(ce->agent_types), "N/A");
		snprintf(tmp, sizeof(tmp), "%s/%s/agent_types", UNCORE_BASE_DIR, names[i]);
		FILE *f = fopen(tmp, "r");
		if (f) {
			if (fgets(ce->agent_types, sizeof(ce->agent_types), f)) {
				char *nl = strchr(ce->agent_types, '\n');
				if (nl)
					*nl = '\0';
			}
			fclose(f);
		}

		nr_clusters++;
	}
#pragma GCC diagnostic pop

	/* Sort by package, then die, for stable, readable output. */
	for (int i = 1; i < nr_clusters; i++) {
		struct cluster_entry key = clusters[i];
		int j = i - 1;

		while (j >= 0 &&
				(clusters[j].pkg_id > key.pkg_id || (clusters[j].pkg_id == key.pkg_id &&
										    clusters[j].die_id > key.die_id))) {
			clusters[j + 1] = clusters[j];
			j--;
		}
		clusters[j + 1] = key;
	}

	return nr_clusters;
}

static const char *
pick_comm_color(const char *comm)
{
	if (!env.allowed_comm[0] || !comm || !comm[0])
		return NULL;

	return strcmp(comm, env.allowed_comm) == 0 ? ANSI_GREEN : ANSI_RED;
}

static bool
is_unwanted_comm(const char *comm)
{
	if (!env.allowed_comm[0] || !comm || !comm[0])
		return false;

	return strcmp(comm, env.allowed_comm) != 0;
}

/* Write comm into buf, colored/bracketed per -a. */
static void
append_comm_display(char *buf, size_t buf_sz, const char *comm)
{
	const char *color = use_color ? pick_comm_color(comm) : NULL;

	if (color)
		snprintf(buf, buf_sz, "%s%s%s", color, comm, ANSI_RESET);
	else if (!use_color && is_unwanted_comm(comm))
		snprintf(buf, buf_sz, "!%s!", comm);
	else
		snprintf(buf, buf_sz, "%s", comm);
}

/* Record comm as having written this limit, evicting the oldest entry once at capacity. */
static void
add_unique_writer(struct unique_writer_list *list, const char *comm)
{
	int j;

	if (!comm[0])
		return;

	for (j = 0; j < list->count; j++) {
		if (strcmp(list->names[j], comm) == 0)
			return;
	}

	if (list->count < MAX_UNIQUE_WRITERS) {
		snprintf(list->names[list->count], UNCORE_COMM_LEN, "%s", comm);
		list->count++;
		return;
	}

	memmove(list->names[0], list->names[1], (MAX_UNIQUE_WRITERS - 1) * UNCORE_COMM_LEN);
	snprintf(list->names[MAX_UNIQUE_WRITERS - 1], UNCORE_COMM_LEN, "%s", comm);
}

static void
format_unique_writers(const struct unique_writer_list *list, char *buf, size_t buf_sz)
{
	size_t off = 0;
	int n;

	if (list->count == 0) {
		snprintf(buf, buf_sz, "-");
		return;
	}

	for (int j = 0; j < list->count && off < buf_sz; j++) {
		char comm_buf[64];

		append_comm_display(comm_buf, sizeof(comm_buf), list->names[j]);
		n = snprintf(buf + off, buf_sz - off, j == 0 ? "%s" : ", %s", comm_buf);
		if (n < 0 || (size_t)n >= buf_sz - off)
			break;
		off += (size_t)n;
	}
}

/* The kernel's domain_id is 0 by default for MSR dies (no domain concept);
 * treat an unread domain_id attribute the same way so the (pkg, die, domain)
 * match key still lines up with what the BPF hooks record. */
static int
match_domain(const struct cluster_entry *ce)
{
	return ce->domain_id >= 0 ? ce->domain_id : 0;
}

/* Drain the BPF write-event queue and fold new writers into each matching cluster's unique set. */
static void
drain_events(int events_fd)
{
	struct write_event ev;

	if (events_fd < 0)
		return;

	while (bpf_map_lookup_and_delete_elem(events_fd, NULL, &ev) == 0) {
		for (int i = 0; i < nr_clusters; i++) {
			bool same_pkg_die = clusters[i].pkg_id == (int)ev.pkg && clusters[i].die_id == (int)ev.die;
			bool same_domain = (__u32)match_domain(&clusters[i]) == ev.domain;

			/* A write via the legacy package_*_die_* path (domain ==
			 * UNCORE_DOMAIN_BROADCAST) applies to every cluster on that
			 * package/die, not just one domain. */
			if (!same_pkg_die || (!same_domain && ev.domain != UNCORE_DOMAIN_BROADCAST))
				continue;
			add_unique_writer(ev.is_max ? &unique_max_writers[i] : &unique_min_writers[i], ev.comm);
		}
	}
}

static void
format_age(char *buf, size_t buf_sz, __u64 ts_ns)
{
	struct timespec now;
	double age_s;

	clock_gettime(CLOCK_MONOTONIC, &now);
	/* ts_ns comes from bpf_ktime_get_ns(), which is CLOCK_MONOTONIC-based. */
	age_s = ((double)now.tv_sec * 1e9 + (double)now.tv_nsec - (double)ts_ns) / 1e9;
	if (age_s < 0)
		age_s = 0;

	if (age_s < 60)
		snprintf(buf, buf_sz, "%.1fs ago", age_s);
	else if (age_s < 3600)
		snprintf(buf, buf_sz, "%.1fm ago", age_s / 60.0);
	else
		snprintf(buf, buf_sz, "%.1fh ago", age_s / 3600.0);
}

static void
format_last_writer(int map_fd, __u32 pkg, __u32 die, __u32 domain, __u32 is_max, char *buf, size_t buf_sz)
{
	struct writer_key key = { .pkg = pkg, .die = die, .domain = domain, .is_max = is_max };
	struct writer_key bcast_key = { .pkg = pkg, .die = die, .domain = UNCORE_DOMAIN_BROADCAST, .is_max = is_max };
	struct writer_info info, bcast_info;
	bool have_info = map_fd >= 0 && bpf_map_lookup_elem(map_fd, &key, &info) == 0;
	bool have_bcast = map_fd >= 0 && bpf_map_lookup_elem(map_fd, &bcast_key, &bcast_info) == 0;
	bool use_bcast = have_bcast && (!have_info || bcast_info.ts_ns > info.ts_ns);
	char age[32];
	char comm_buf[64];

	/* A write via the legacy package_*_die_* path can be older or newer
	 * than a domain-specific write; show whichever happened last. */
	if (use_bcast)
		info = bcast_info;

	if (!have_info && !have_bcast) {
		snprintf(buf, buf_sz, "no writes observed");
		return;
	}

	format_age(age, sizeof(age), info.ts_ns);
	append_comm_display(comm_buf, sizeof(comm_buf), info.comm);
	snprintf(buf, buf_sz, "%s[%u] -> %u MHz (%s)", comm_buf, info.pid, info.freq_khz / 1000, age);
}

/*
 * pkg/die is the primary label on both MSR and TPMI systems. On TPMI,
 * several clusters can share the same package/die (a known driver quirk),
 * so domain_id is appended as a "cluster N" note to distinguish them, and
 * agent_types alongside it when the driver populates it. If neither pkg
 * nor die could be determined at all, fall back to the sysfs directory
 * name, which is always unique.
 */
static void
format_cluster_label(const struct cluster_entry *ce, char *buf, size_t buf_sz)
{
	bool has_agent = ce->agent_types[0] && strcmp(ce->agent_types, "N/A") != 0;
	char note[80] = "";

	if (ce->die_id < 0) {
		snprintf(buf, buf_sz, "pkg%d/%s", ce->pkg_id, ce->name);
		return;
	}

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-truncation"
	if (ce->domain_id >= 0 && has_agent)
		snprintf(note, sizeof(note), " (cluster %d, %s)", ce->domain_id, ce->agent_types);
	else if (ce->domain_id >= 0)
		snprintf(note, sizeof(note), " (cluster %d)", ce->domain_id);
	else if (has_agent)
		snprintf(note, sizeof(note), " (%s)", ce->agent_types);

	snprintf(buf, buf_sz, "pkg%d/die%d%s", ce->pkg_id, ce->die_id, note);
#pragma GCC diagnostic pop
}

/* pkg/die widths and agent_types content vary by system, so the CLUSTER
 * column can't be sized with a fixed guess; compute it from the labels
 * actually enumerated instead. Clusters don't change after enumeration,
 * so this only needs to run once. */
static void
compute_cluster_col_width(void)
{
	size_t max_len = strlen("CLUSTER");

	for (int i = 0; i < nr_clusters; i++) {
		char label[300];

		format_cluster_label(&clusters[i], label, sizeof(label));
		if (strlen(label) > max_len)
			max_len = strlen(label);
	}
	cluster_col_width = (int)max_len;
}

static void
print_separator(int width)
{
	for (int i = 0; i < width; i++)
		putchar('-');
	putchar('\n');
}

/* Render a sysfs khz reading as whole MHz, or "N/A" if it wasn't read. */
static void
format_khz_mhz(int khz, char *buf, size_t buf_sz)
{
	if (khz < 0)
		snprintf(buf, buf_sz, "N/A");
	else
		snprintf(buf, buf_sz, "%d", khz / 1000);
}

static void
render(int map_fd)
{
	if (!env.no_clear)
		printf("\033[H\033[J");

	printf("uncoretracker - uncore frequency config monitor  (Ctrl-C to exit)\n");
	if (writer_tracking_warning[0])
		printf("Warning: %s\n", writer_tracking_warning);
	printf("%-*s %10s %10s %10s   %-8s %s\n",
			cluster_col_width,
			"CLUSTER",
			"MIN(MHz)",
			"MAX(MHz)",
			"CUR(MHz)",
			"LIMIT",
			"LAST CHANGED BY");
	/* Matches the fixed portion of the header row (spaces/columns before
	 * the free-form LAST CHANGED BY field) plus its header text width. */
	print_separator(cluster_col_width + 60);

	for (int i = 0; i < nr_clusters; i++) {
		struct cluster_entry *ce = &clusters[i];
		char tmp[640];
		int min_khz = -1, max_khz = -1, cur_khz = -1;
		char min_mhz[16], max_mhz[16], cur_mhz[16];
		char label[300];
		char min_writer[128], max_writer[128];

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-truncation"
		snprintf(tmp, sizeof(tmp), "%s/min_freq_khz", ce->sysfs_dir);
		sysfs_read_int(tmp, &min_khz);
		snprintf(tmp, sizeof(tmp), "%s/max_freq_khz", ce->sysfs_dir);
		sysfs_read_int(tmp, &max_khz);
		snprintf(tmp, sizeof(tmp), "%s/current_freq_khz", ce->sysfs_dir);
		sysfs_read_int(tmp, &cur_khz);
#pragma GCC diagnostic pop
		format_khz_mhz(min_khz, min_mhz, sizeof(min_mhz));
		format_khz_mhz(max_khz, max_mhz, sizeof(max_mhz));
		format_khz_mhz(cur_khz, cur_mhz, sizeof(cur_mhz));
		format_cluster_label(ce, label, sizeof(label));

		format_last_writer(map_fd,
				(__u32)ce->pkg_id,
				(__u32)ce->die_id,
				(__u32)match_domain(ce),
				0,
				min_writer,
				sizeof(min_writer));
		format_last_writer(map_fd,
				(__u32)ce->pkg_id,
				(__u32)ce->die_id,
				(__u32)match_domain(ce),
				1,
				max_writer,
				sizeof(max_writer));

		printf("%-*s %10s %10s %10s   %-8s %s\n",
				cluster_col_width,
				label,
				min_mhz,
				max_mhz,
				cur_mhz,
				"min",
				min_writer);
		printf("%-*s %10s %10s %10s   %-8s %s\n", cluster_col_width, "", "", "", "", "max", max_writer);
	}

	printf("\nWriter history (since start):\n");
	for (int i = 0; i < nr_clusters; i++) {
		struct cluster_entry *ce = &clusters[i];
		char label[300];
		char min_seen[256], max_seen[256];

		format_cluster_label(ce, label, sizeof(label));

		format_unique_writers(&unique_min_writers[i], min_seen, sizeof(min_seen));
		format_unique_writers(&unique_max_writers[i], max_seen, sizeof(max_seen));

		printf("  %-*s min: %s\n", cluster_col_width, label, min_seen);
		printf("  %-*s max: %s\n", cluster_col_width, "", max_seen);
	}

	fflush(stdout);
}

// LCOV_EXCL_START
/* Orchestrates the real BPF skeleton lifecycle and the live polling
 * loop; needs a kernel/verifier and isn't host-unit-testable. Every
 * helper it calls (enumerate_clusters, compute_cluster_col_width,
 * kernel_has_function, drain_events, render, ...) is unit-tested on
 * its own. */
int
main(int argc, char **argv)
{
	static const char *const topology_fields[] = { "package_id", "die_id", "domain_id" };
	/* Older/MSR-only kernels ship the driver as a single module; newer
	 * TPMI-capable kernels split the shared struct into _common. */
	static const char *const uncore_module_candidates[] = {
		"intel_uncore_frequency",
		"intel_uncore_frequency_common",
	};
	int n_uncore_module_candidates = sizeof(uncore_module_candidates) / sizeof(uncore_module_candidates[0]);
	int n_topology_fields = sizeof(topology_fields) / sizeof(topology_fields[0]);
	struct uncoretracker_bpf *skel;
	int map_fd, events_fd;
	int have_control_freq, have_write;
	char missing[128];
	int err;

	if (argp_parse(&argp, argc, argv, 0, NULL, NULL))
		return 1;

	use_color = isatty(STDOUT_FILENO);

	if (enumerate_clusters() <= 0) {
		if (access(UNCORE_BASE_DIR, F_OK) != 0)
			fprintf(stderr,
					"%s does not exist; is the intel_uncore_frequency kernel module loaded?\n",
					UNCORE_BASE_DIR);
		else
			fprintf(stderr, "No entries with a readable min_freq_khz found under %s\n", UNCORE_BASE_DIR);
		return 1;
	}
	compute_cluster_col_width();

	libbpf_set_print(libbpf_print_fn);

	skel = uncoretracker_bpf__open();
	if (!skel) {
		fprintf(stderr, "Failed to open BPF skeleton: %s\n", strerror(errno));
		return 1;
	}

	/*
	 * uncore_write_control_freq() is either its own standalone function
	 * (older kernels) or fully inlined into its dispatcher caller,
	 * uncore_write() (newer kernels/compilers). Disable whichever hook
	 * doesn't apply so skeleton load doesn't fail trying to resolve a
	 * BTF function that doesn't exist.
	 */
	have_control_freq = kernel_has_function("uncore_write_control_freq");
	have_write = !have_control_freq && kernel_has_function("uncore_write");

	if (have_control_freq) {
		bpf_program__set_autoload(skel->progs.fexit_uncore_write, false);
	} else if (have_write) {
		bpf_program__set_autoload(skel->progs.fexit_uncore_write_control_freq, false);
	} else {
		// clang-format off
		snprintf(writer_tracking_warning,
				sizeof(writer_tracking_warning),
				"neither uncore_write_control_freq nor uncore_write found in kallsyms - last-writer tracking will not be captured");
		// clang-format on
		bpf_program__set_autoload(skel->progs.fexit_uncore_write_control_freq, false);
		bpf_program__set_autoload(skel->progs.fexit_uncore_write, false);
	}

	/* Check for missing fields in struct uncore_data, wherever it's defined. */
	if (struct_missing_fields(uncore_module_candidates,
			    n_uncore_module_candidates,
			    "uncore_data",
			    topology_fields,
			    n_topology_fields,
			    missing,
			    sizeof(missing))) {
		size_t off = strlen(writer_tracking_warning);

		// clang-format off
		snprintf(writer_tracking_warning + off,
				sizeof(writer_tracking_warning) - off,
				"%sthe intel_uncore_frequency driver's struct uncore_data is missing field(s) %s on this kernel - last-writer tracking cannot attribute writes to a package/die/domain and will not be captured",
				off ? " - " : "",
				missing);
		// clang-format on
		bpf_program__set_autoload(skel->progs.fexit_uncore_write_control_freq, false);
		bpf_program__set_autoload(skel->progs.fexit_uncore_write, false);
	}

	if (uncoretracker_bpf__load(skel)) {
		fprintf(stderr, "Failed to load BPF skeleton: %s\n", strerror(errno));
		uncoretracker_bpf__destroy(skel);
		return 1;
	}

	err = uncoretracker_bpf__attach(skel);
	if (err) {
		fprintf(stderr, "Failed to attach BPF programs: %s\n", strerror(-err));
		uncoretracker_bpf__destroy(skel);
		return 1;
	}

	map_fd = bpf_map__fd(skel->maps.last_writer);
	events_fd = bpf_map__fd(skel->maps.events);

	signal(SIGINT, sig_handler);
	signal(SIGTERM, sig_handler);

	if (!env.no_clear) {
		printf("\033[?25l");
		cursor_hidden = true;
	}

	while (!exiting) {
		drain_events(events_fd);
		render(map_fd);
		sleep((unsigned int)env.interval);
	}

	restore_terminal();
	uncoretracker_bpf__destroy(skel);
	return 0;
}
// LCOV_EXCL_STOP
