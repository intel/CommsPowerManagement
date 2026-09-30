/*
 * SPDX-License-Identifier: GPL-2.0 OR BSD-2-Clause
 * Copyright (c) 2026 Intel Corporation
 */

#include <vmlinux.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include "freqtracker.h"

struct {
	__uint(type, BPF_MAP_TYPE_QUEUE);
	__uint(max_entries, 16384);
	__uint(value_size, sizeof(struct freq_stream_event));
} events SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_CPU_NR *FREQ_MAX_HIST_BINS *FREQ_REQ_TYPES);
	__uint(map_flags, BPF_F_NO_PREALLOC);
	__type(key, struct freq_hist_key);
	__type(value, __u64);
} freq_bins SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, FREQ_STAT_MAX);
	__type(key, __u32);
	__type(value, __u64);
} freq_stats SEC(".maps");

struct pending_freq_request {
	__u64 ts_ns;
	__u32 cpu;
	__u32 freq_khz;
	__u32 pid;
	__u32 req_type;
	char comm[TASK_COMM_LEN];
};

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 1024);
	__type(key, __u64);
	__type(value, struct pending_freq_request);
} pending_requests SEC(".maps");

#define MAX_FREQ_INPUT_LEN 32
#define U32_MAX_DIV10 ((__u32)~0U / 10U)
#define U32_MAX_MOD10 ((__u32)~0U % 10U)

static __always_inline void
count_stat(__u32 stat_key)
{
	__u64 *value = bpf_map_lookup_elem(&freq_stats, &stat_key);

	if (value)
		__sync_fetch_and_add(value, 1);
}

static __always_inline void
count_freq_bin(__u32 cpu, __u32 req_type, __u32 freq_khz)
{
	struct freq_hist_key key = {
		.cpu = cpu,
		.req_type = req_type,
		.freq_khz = freq_khz,
	};
	__u64 one = 1;
	__u64 *count;
	int err;

	count = bpf_map_lookup_elem(&freq_bins, &key);
	if (count) {
		__sync_fetch_and_add(count, 1);
		return;
	}

	err = bpf_map_update_elem(&freq_bins, &key, &one, BPF_NOEXIST);
	if (!err)
		return;

	count = bpf_map_lookup_elem(&freq_bins, &key);
	if (count) {
		__sync_fetch_and_add(count, 1);
		return;
	}

	count_stat(FREQ_STAT_DROPPED_BINS);
}

static __always_inline int
parse_req_khz(const char *buf, size_t count, __u32 *freq_khz)
{
	__u32 val = 0;
	__u32 read_len;
	char input[MAX_FREQ_INPUT_LEN] = {};
	char c;
	int i;

	if (!buf || !freq_khz)
		return -1;

	read_len = count < MAX_FREQ_INPUT_LEN ? (__u32)count : MAX_FREQ_INPUT_LEN;
	if (!read_len)
		return -1;

	if (bpf_probe_read_kernel(input, read_len, buf) < 0)
		return -1;

	for (i = 0; i < MAX_FREQ_INPUT_LEN; i++) {
		if (i >= read_len)
			break;
		c = input[i];
		if (c == '\0' || c == '\n')
			break;
		if (c < '0' || c > '9')
			return -1;
		if (val > U32_MAX_DIV10)
			return -1;
		if (val == U32_MAX_DIV10 && (c - '0') > U32_MAX_MOD10)
			return -1;
		val = val * 10 + (c - '0');
	}

	if (i == 0)
		return -1;
	if (i == MAX_FREQ_INPUT_LEN && count > MAX_FREQ_INPUT_LEN)
		return -1;

	*freq_khz = val;
	return 0;
}

static __always_inline int
capture_freq_request(struct cpufreq_policy *policy,
		const char *buf,
		size_t count,
		__u32 req_type,
		struct pending_freq_request *request)
{
	if (!policy || !buf || !request)
		return -1;

	if (bpf_core_read(&request->cpu, sizeof(request->cpu), &policy->cpu) < 0)
		return -1;
	if (request->cpu >= MAX_CPU_NR)
		return -1;

	if (parse_req_khz(buf, count, &request->freq_khz) < 0)
		return -1;

	request->pid = bpf_get_current_pid_tgid() >> 32;
	request->req_type = req_type;
	/* Use the thread group leader's comm so we see the process name, not a thread name. */
	{
		struct task_struct *task = (struct task_struct *)bpf_get_current_task();
		struct task_struct *leader = BPF_CORE_READ(task, group_leader);

		if (leader && bpf_probe_read_kernel_str(request->comm, sizeof(request->comm), leader->comm) < 0)
			bpf_get_current_comm(request->comm, sizeof(request->comm));
	}
	request->ts_ns = bpf_ktime_get_ns();

	return 0;
}

static __always_inline void
publish_freq_request(const struct pending_freq_request *request)
{
	struct freq_stream_event event = {
		.ts_ns = request->ts_ns,
		.cpu = request->cpu,
		.freq_khz = request->freq_khz,
		.pid = request->pid,
		.req_type = request->req_type,
	};

	count_freq_bin(request->cpu, request->req_type, request->freq_khz);
	__builtin_memcpy(event.comm, request->comm, sizeof(event.comm));
	if (bpf_map_push_elem(&events, &event, 0) < 0)
		count_stat(FREQ_STAT_DROPPED_EVENTS);
}

static __always_inline int
save_pending_request(struct cpufreq_policy *policy, const char *buf, size_t count, __u32 req_type)
{
	struct pending_freq_request request = {};
	__u64 key = bpf_get_current_pid_tgid();

	if (capture_freq_request(policy, buf, count, req_type, &request) < 0) {
		count_stat(FREQ_STAT_DROPPED_REQUESTS);
		return 0;
	}
	if (bpf_map_update_elem(&pending_requests, &key, &request, BPF_ANY) < 0)
		count_stat(FREQ_STAT_DROPPED_REQUESTS);

	return 0;
}

static __always_inline int
complete_pending_request(long ret)
{
	struct pending_freq_request *pending;
	struct pending_freq_request request;
	__u64 key = bpf_get_current_pid_tgid();

	pending = bpf_map_lookup_elem(&pending_requests, &key);
	if (!pending) {
		if (ret >= 0)
			count_stat(FREQ_STAT_DROPPED_REQUESTS);
		return 0;
	}

	__builtin_memcpy(&request, pending, sizeof(request));
	bpf_map_delete_elem(&pending_requests, &key);
	if (ret >= 0)
		publish_freq_request(&request);

	return 0;
}

SEC("tp/power/cpu_frequency")
int
handle_cpu_frequency(struct trace_event_raw_cpu *ctx)
{
	struct freq_stream_event event = {
		.req_type = FREQ_REQ_ACTUAL,
	};
	__u32 cpu, freq_khz;

	if (!ctx)
		return 0;

	cpu = BPF_CORE_READ(ctx, cpu_id);
	if (cpu >= MAX_CPU_NR)
		return 0;

	freq_khz = BPF_CORE_READ(ctx, state);

	count_freq_bin(cpu, FREQ_REQ_ACTUAL, freq_khz);
	event.ts_ns = bpf_ktime_get_ns();
	event.cpu = cpu;
	event.freq_khz = freq_khz;
	if (bpf_map_push_elem(&events, &event, 0) < 0)
		count_stat(FREQ_STAT_DROPPED_EVENTS);

	return 0;
}

SEC("kprobe/store_scaling_max_freq")
int
BPF_KPROBE(store_scaling_max_freq, struct cpufreq_policy *policy, const char *buf, size_t count)
{
	return save_pending_request(policy, buf, count, FREQ_REQ_MAX);
}

SEC("kretprobe/store_scaling_max_freq")
int
BPF_KRETPROBE(kretprobe_store_scaling_max_freq, long ret)
{
	return complete_pending_request(ret);
}

SEC("fexit/store_scaling_max_freq")
int
BPF_PROG(fexit_store_scaling_max_freq, struct cpufreq_policy *policy, const char *buf, size_t count, long ret)
{
	struct pending_freq_request request = {};

	if (ret < 0)
		return 0;
	if (capture_freq_request(policy, buf, count, FREQ_REQ_MAX, &request) < 0) {
		count_stat(FREQ_STAT_DROPPED_REQUESTS);
		return 0;
	}
	publish_freq_request(&request);
	return 0;
}

SEC("kprobe/store_scaling_min_freq")
int
BPF_KPROBE(store_scaling_min_freq, struct cpufreq_policy *policy, const char *buf, size_t count)
{
	return save_pending_request(policy, buf, count, FREQ_REQ_MIN);
}

SEC("kretprobe/store_scaling_min_freq")
int
BPF_KRETPROBE(kretprobe_store_scaling_min_freq, long ret)
{
	return complete_pending_request(ret);
}

SEC("fexit/store_scaling_min_freq")
int
BPF_PROG(fexit_store_scaling_min_freq, struct cpufreq_policy *policy, const char *buf, size_t count, long ret)
{
	struct pending_freq_request request = {};

	if (ret < 0)
		return 0;
	if (capture_freq_request(policy, buf, count, FREQ_REQ_MIN, &request) < 0) {
		count_stat(FREQ_STAT_DROPPED_REQUESTS);
		return 0;
	}
	publish_freq_request(&request);
	return 0;
}

char LICENSE[] SEC("license") = "Dual BSD/GPL";
