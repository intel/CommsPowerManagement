# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Intel Corporation

OUTPUT := .output
BPF_OBJ := $(OUTPUT)/uncoretracker.bpf.o
SKEL := $(OUTPUT)/uncoretracker.skel.h
VMLINUX := $(OUTPUT)/vmlinux.h
BIN := uncoretracker

CC ?= cc
CLANG ?= clang
BPFTOOL ?= bpftool
PKG_CONFIG ?= pkg-config
BTF_FILE ?= /sys/kernel/btf/vmlinux
CFLAGS ?= -O2 -g -Wall -Wextra
LDFLAGS ?=

LIBBPF_CFLAGS := $(shell $(PKG_CONFIG) --cflags libbpf 2>/dev/null)
LIBBPF_LIBS := $(shell $(PKG_CONFIG) --libs libbpf 2>/dev/null)
LIBBPF_LIBDIR := $(shell $(PKG_CONFIG) --variable=libdir libbpf 2>/dev/null)
ifeq ($(strip $(LIBBPF_LIBS)),)
LIBS ?= -lbpf -lelf -lz
else
LIBS ?= $(LIBBPF_LIBS)
endif
ifeq ($(USE_RPATH),1)
ifneq ($(strip $(LIBBPF_LIBDIR)),)
LDFLAGS += -Wl,-rpath,$(LIBBPF_LIBDIR)
endif
endif

UNAME_M := $(shell uname -m)
ifneq ($(UNAME_M),x86_64)
$(error Unsupported architecture: $(UNAME_M) (only x86_64 is supported))
endif
ARCH := x86

INCLUDES := -I$(OUTPUT) -I. $(LIBBPF_CFLAGS)
BPF_CFLAGS := -O2 -g -target bpf -D__TARGET_ARCH_$(ARCH) $(INCLUDES)

BPFTOOL_CANDIDATE := $(shell ls -1d /usr/lib/linux-tools/*/bpftool 2>/dev/null | sort -V | tail -n 1)
BPFTOOL_RUN := $(BPFTOOL)
ifeq ($(BPFTOOL),bpftool)
ifneq ($(wildcard /usr/sbin/bpftool),)
ifneq ($(BPFTOOL_CANDIDATE),)
BPFTOOL_RUN := $(BPFTOOL_CANDIDATE)
endif
endif
endif

.PHONY: all clean vmlinux check-deps

all: check-deps $(BIN)

check-deps:
	$(call ensure_tool,$(CLANG))
	$(call ensure_tool,$(CC))
	$(call ensure_exec,$(BPFTOOL_RUN))
	@if [ ! -r "$(BTF_FILE)" ]; then \
		echo "error: missing readable BTF file: $(BTF_FILE)" 1>&2; \
		echo "hint: enable CONFIG_DEBUG_INFO_BTF or set BTF_FILE=/path/to/vmlinux.btf" 1>&2; \
		exit 1; \
	fi
	@if ! printf '#include <bpf/bpf_core_read.h>\n' | $(CC) -x c -E - >/dev/null 2>&1; then \
		echo "error: missing libbpf development headers (bpf/bpf_core_read.h)" 1>&2; \
		echo "hint: install libbpf-dev (Debian/Ubuntu) or libbpf-devel (RHEL/Fedora/SUSE)" 1>&2; \
		exit 1; \
	fi
	@echo "all required build dependencies look available"

$(OUTPUT):
	mkdir -p $(OUTPUT)

define ensure_tool
	@if ! command -v $(1) >/dev/null 2>&1; then \
		echo "error: missing required tool '$(1)'" 1>&2; \
		exit 1; \
	fi
endef

define ensure_exec
	@if [ ! -x "$(1)" ] && ! command -v $(1) >/dev/null 2>&1; then \
		echo "error: missing required executable '$(1)'" 1>&2; \
		exit 1; \
	fi
endef

$(VMLINUX): | $(OUTPUT)
	$(call ensure_exec,$(BPFTOOL_RUN))
	@if [ -r "$(BTF_FILE)" ]; then \
		$(BPFTOOL_RUN) btf dump file "$(BTF_FILE)" format c > $(VMLINUX); \
	else \
		echo "error: BTF file is not readable: $(BTF_FILE)" 1>&2; \
		echo "hint: enable CONFIG_DEBUG_INFO_BTF or set BTF_FILE=/path/to/vmlinux.btf" 1>&2; \
		exit 1; \
	fi

$(BPF_OBJ): uncoretracker.bpf.c uncoretracker.h $(VMLINUX)
	$(call ensure_tool,$(CLANG))
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

$(SKEL): $(BPF_OBJ)
	$(call ensure_exec,$(BPFTOOL_RUN))
	$(BPFTOOL_RUN) gen skeleton $< > $@

$(BIN): uncoretracker.c uncoretracker.h $(SKEL)
	$(call ensure_tool,$(CC))
	$(CC) $(CFLAGS) $(INCLUDES) uncoretracker.c $(LDFLAGS) $(LIBS) -o $(BIN)

vmlinux: $(VMLINUX)

clean:
	rm -rf $(OUTPUT) $(BIN)
