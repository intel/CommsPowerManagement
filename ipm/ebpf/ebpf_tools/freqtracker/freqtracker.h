/*
 * SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Intel Corporation
 */

#ifndef __FREQTRACKER_H
#define __FREQTRACKER_H

#define MAX_CPU_NR 512
#define FREQ_HISTORY_LEN 16
#define TASK_COMM_LEN 16
#define FREQ_MAX_HIST_BINS 256

enum freq_req_type {
	FREQ_REQ_MAX = 0,
	FREQ_REQ_MIN = 1,
	FREQ_REQ_ACTUAL = 2,
	FREQ_REQ_TYPES = 3,
};

enum freq_stat_key {
	FREQ_STAT_DROPPED_BINS = 0,
	FREQ_STAT_DROPPED_REQUESTS,
	FREQ_STAT_DROPPED_EVENTS,
	FREQ_STAT_MAX,
};

struct freq_hist_key {
	__u32 cpu;
	__u32 req_type;
	__u32 freq_khz;
	__u32 pad;
};

struct freq_event {
	__u64 seq;
	__u64 ts_ns;
	__u32 freq_khz;
	__u32 pid;
	__u32 req_type;
	char comm[TASK_COMM_LEN];
};

struct freq_stream_event {
	__u64 ts_ns;
	__u32 cpu;
	__u32 freq_khz;
	__u32 pid;
	__u32 req_type;
	char comm[TASK_COMM_LEN];
};

struct cpu_freq_history {
	__u64 seq;
	__u64 next_seq;
	__u64 actual_seq;
	__u64 next_actual_seq;
	__u64 actual_ts_ns;
	__u32 actual_freq_khz;
	__u32 pad;
	struct freq_event events[FREQ_HISTORY_LEN];
};

#endif /* __FREQTRACKER_H */
