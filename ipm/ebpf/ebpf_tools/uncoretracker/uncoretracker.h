/*
 * SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Intel Corporation
 */

/*
 * uncoretracker.h - shared map key/value structs between BPF and user-space.
 */

#ifndef __UNCORETRACKER_H
#define __UNCORETRACKER_H

/* vmlinux.h already defines __u32/__u64; only include linux/types.h for
 * user-space compilation where vmlinux.h is not in scope. */
#ifndef __VMLINUX_H__
#include <linux/types.h>
#endif

#define UNCORE_COMM_LEN 16 /* COMM is the name of the process writing the frequency limit */
#define MAX_UNCORE_CLUSTERS 64

/* Each cluster contributes at most one domain-specific and one broadcast
 * last_writer entry, each of which is tracked separately for min and max. */
#define UNCORE_MINMAX_VARIANTS 2 /* min_freq_khz, max_freq_khz */
#define UNCORE_KEY_KINDS_PER_CLUSTER 2 /* domain-specific (eg uncore00), broadcast (eg package_00_die_00) */
#define UNCORE_MAX_WRITER_KEYS (MAX_UNCORE_CLUSTERS * UNCORE_KEY_KINDS_PER_CLUSTER * UNCORE_MINMAX_VARIANTS)

/* The kernel reports domain_id == -1 for writes made through the legacy
 * package_*_die_* sysfs path, which apply to every cluster sharing that
 * package/die; cast to unsigned for use as a writer_key/write_event field. */
#define UNCORE_DOMAIN_BROADCAST ((__u32)-1)

/* Key into the last_writer map: one entry per (package, die, domain, min|max).
 * die differentiates MSR dies; domain differentiates TPMI clusters that
 * otherwise share the same die (often 0 for non-core agents). */
struct writer_key {
	__u32 pkg;
	__u32 die;
	__u32 domain;
	__u32 is_max; /* 1 = last writer of max_freq_khz, 0 = min_freq_khz */
};

/* Value: who last wrote this limit, what they set it to, and when. */
struct writer_info {
	__u64 ts_ns;
	__u32 pid;
	__u32 freq_khz;
	char comm[UNCORE_COMM_LEN];
};

/* Queue entry: one per successful min/max write, so user-space can build a
 * complete history of writers (last_writer above only keeps the latest). */
struct write_event {
	__u64 ts_ns;
	__u32 pkg;
	__u32 die;
	__u32 domain;
	__u32 is_max;
	__u32 pid;
	__u32 freq_khz;
	char comm[UNCORE_COMM_LEN];
};

#endif /* __UNCORETRACKER_H */
