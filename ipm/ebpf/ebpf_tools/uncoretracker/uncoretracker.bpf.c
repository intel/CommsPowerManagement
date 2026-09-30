/*
 * SPDX-License-Identifier: GPL-2.0 OR BSD-2-Clause
 * Copyright (c) 2026 Intel Corporation
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "uncoretracker.h"

#define UNCORE_INDEX_MIN_FREQ 0U
#define UNCORE_INDEX_MAX_FREQ 1U

/*
 * CO-RE shadow struct for 'struct uncore_data' from the
 * intel_uncore_frequency kernel module. Only the fields we access are
 * declared; BPF CO-RE resolves the actual field offsets at load time
 * from /sys/kernel/btf/intel_uncore_frequency, so no hardcoded offsets.
 */
struct uncore_data {
	int package_id;
	int die_id;
	int domain_id;
} __attribute__((preserve_access_index));

/*
 * Last writer of min_freq_khz/max_freq_khz per (package, die, domain).
 */
struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, UNCORE_MAX_WRITER_KEYS);
	__type(key, struct writer_key);
	__type(value, struct writer_info);
} last_writer SEC(".maps");

/* Every successful min/max write, so user-space can dedup a full writer history. */
struct {
	__uint(type, BPF_MAP_TYPE_QUEUE);
	__uint(max_entries, 4096);
	__type(value, struct write_event);
} events SEC(".maps");

static __always_inline void
record_writer(__u32 pkg, __u32 die, __u32 domain, __u32 is_max, __u32 freq_khz)
{
	struct writer_key key = {
		.pkg = pkg,
		.die = die,
		.domain = domain,
		.is_max = is_max,
	};
	struct writer_info info = {};
	struct write_event ev = {};
	struct task_struct *task, *leader;

	info.ts_ns = bpf_ktime_get_ns();
	info.pid = bpf_get_current_pid_tgid() >> 32;
	info.freq_khz = freq_khz;

	/* Use the thread group leader's comm so we see the process name, not a thread name. */
	task = (struct task_struct *)bpf_get_current_task();
	leader = BPF_CORE_READ(task, group_leader);
	if (!leader || bpf_probe_read_kernel_str(info.comm, sizeof(info.comm), leader->comm) < 0)
		bpf_get_current_comm(info.comm, sizeof(info.comm));

	bpf_map_update_elem(&last_writer, &key, &info, BPF_ANY);

	ev.ts_ns = info.ts_ns;
	ev.pkg = pkg;
	ev.die = die;
	ev.domain = domain;
	ev.is_max = is_max;
	ev.pid = info.pid;
	ev.freq_khz = freq_khz;
	__builtin_memcpy(ev.comm, info.comm, sizeof(ev.comm));
	bpf_map_push_elem(&events, &ev, 0);
}

/*
 * fexit: uncore_write_control_freq  ->  record last writer
 *
 * Older-kernel shape: uncore_write_control_freq() is its own function.
 * Only recorded on success (retval == 0), i.e. the value the hardware
 * actually accepted.
 *
 * Kernel 6.x prototype:
 *   int uncore_write_control_freq(struct uncore_data *data,
 *                                  unsigned int freq_khz,
 *                                  unsigned int min_max)
 */
SEC("fexit/uncore_write_control_freq")
int
BPF_PROG(fexit_uncore_write_control_freq,
		struct uncore_data *data,
		unsigned int freq_khz,
		unsigned int min_max,
		int retval)
{
	if (retval != 0)
		return 0;

	record_writer(BPF_CORE_READ(data, package_id),
			BPF_CORE_READ(data, die_id),
			BPF_CORE_READ(data, domain_id),
			min_max ? 1 : 0,
			freq_khz);
	return 0;
}

/*
 * fexit: uncore_write  ->  record last writer
 *
 * Newer-kernel counterpart: hooks the dispatcher that survives when
 * uncore_write_control_freq() itself gets inlined away, filtered to just
 * the min/max indexes it forwards to.
 *
 * Kernel 6.14+ prototype:
 *   int uncore_write(struct uncore_data *data, unsigned int value,
 *                     enum uncore_index index)
 */
SEC("fexit/uncore_write")
int
BPF_PROG(fexit_uncore_write, struct uncore_data *data, unsigned int value, unsigned int index, int retval)
{
	if (retval != 0)
		return 0;
	if (index != UNCORE_INDEX_MIN_FREQ && index != UNCORE_INDEX_MAX_FREQ)
		return 0;

	record_writer(BPF_CORE_READ(data, package_id),
			BPF_CORE_READ(data, die_id),
			BPF_CORE_READ(data, domain_id),
			index == UNCORE_INDEX_MAX_FREQ ? 1 : 0,
			value);
	return 0;
}

char LICENSE[] SEC("license") = "Dual BSD/GPL";
