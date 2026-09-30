# freqtracker

Standalone eBPF tool for tracking CPU frequency requests, transitions, and the processes behind them.

## What it does

`freqtracker` tracks, per CPU:
- accepted max frequency writes (`store_scaling_max_freq`)
- accepted min frequency writes (`store_scaling_min_freq`)
- actual frequency transitions (`power:cpu_frequency` tracepoint)

Min/max writes apply to a cpufreq policy rather than one CPU. The BPF program
records each accepted policy write once, and userspace displays it for every CPU
listed in that policy's `related_cpus`. Actual transitions remain CPU-specific.
Rejected min/max writes are not included.

It renders either a grid view for many CPUs or a single-core detail mode.

In single-core detail mode it also shows:
- per-frequency histograms for `min`, `actual`, and `max`
- recent request events (type, frequency, age, process, pid)
- a rolling list of unique process names seen for that CPU

## Prerequisites

Install build dependencies for your distribution:
- clang
- bpftool
- C compiler (`cc`/`gcc`)
- libbpf development package (headers and library)
- libelf development package
- zlib development package
- pkg-config

Kernel/runtime requirements:
- BPF-enabled kernel
- readable host BTF at `/sys/kernel/btf/vmlinux` (or set `BTF_FILE` to a readable BTF file)
- root privileges (or equivalent capabilities) to load BPF programs

## Build

From this directory:

```bash
make
```

Build artifacts:
- `.output/vmlinux.h`
- `.output/freqtracker.bpf.o`
- `.output/freqtracker.skel.h`
- `./freqtracker`

These artifacts are generated locally and ignored by git.

Preflight dependency check:

```bash
make check-deps
```

If your distro `bpftool` wrapper does not match the running kernel, set a direct path:

```bash
make BPFTOOL=/usr/lib/linux-tools/<kernel-version>/bpftool
```

If host BTF is not available at `/sys/kernel/btf/vmlinux`, point the build at a custom BTF file:

```bash
make BTF_FILE=/path/to/vmlinux.btf
```

Optional targets:

```bash
make vmlinux     # only regenerate .output/vmlinux.h
make clean
```

To override architecture autodetection, set the BPF target explicitly:

```bash
make BPF_ARCH=arm64
```

## Run

Help:

```bash
./freqtracker --help
```

Live view:

```bash
./freqtracker
```

Single-core mode:

```bash
./freqtracker -c 3
```

Filter displayed cores:

```bash
./freqtracker -f 0-7
```

Customize refresh interval and grid columns:

```bash
./freqtracker -i 2 -w 6
```

Color process names by allow-listing one command name:

```bash
./freqtracker -a bash
```

Note: `COMM` follows the kernel `task_struct->comm` format, which is 16 bytes total including
the trailing `\0` terminator. That means the maximum visible process name is 15 characters.

Disable screen clearing between refreshes:

```bash
./freqtracker -C
```

Verbose libbpf/debug output:

```bash
./freqtracker -v
```

### CLI options

- `-i SEC`: refresh interval in seconds (must be > 0)
- `-c CPU`: single-core detail mode for one CPU
- `-f CORES`: CPU filter (for example `0-7,12-15`)
- `-w COLS`: number of columns in grid mode (`1-100`, default `4`)
- `-a COMM`: color this process `comm` green, others red (`comm` is 16 bytes total including
  trailing `\0`, so max 15 visible characters)
- `-C`: do not clear terminal each refresh
- `-v`: enable verbose libbpf debug output

## Attach mode

- Attach mode can be selected with `FREQTRACKER_ATTACH`:
  - `auto` (default): try `fexit`, then fall back to paired `kprobe`/`kretprobe` hooks
  - `fexit`: require `fexit` (no fallback)
  - `fentry`: compatibility alias for `fexit`
  - `kprobe`: force paired `kprobe`/`kretprobe` hooks
- Invalid `FREQTRACKER_ATTACH` values are rejected.

Examples:

```bash
FREQTRACKER_ATTACH=auto ./freqtracker
FREQTRACKER_ATTACH=fexit ./freqtracker
FREQTRACKER_ATTACH=kprobe ./freqtracker
```

## Runtime BTF selection

At runtime, you can point CO-RE to a custom BTF file:

```bash
export BTF_FILE=/path/to/vmlinux.btf
./freqtracker
```

## Notes and troubleshooting

- Minimum recommended libbpf version for `fexit` mode: `>= 1.2`.
  - For Linux 6.8 kernels, `0.5.0` is too old; this tool was validated with libbpf `1.4.5`.
- `fexit` requires host kernel BTF plus a libbpf version new enough to parse your kernel's BTF format.
- On Ubuntu 22.04, `apt` typically provides libbpf `0.5.0`, which can be too old for newer kernels.
  If needed, install a newer libbpf from source into `/usr/local` and rebuild; this Makefile uses `pkg-config` and will pick up `/usr/local/lib/pkgconfig/libbpf.pc` automatically.
- In `auto` attach mode, load/attach failures in `fexit` are retried automatically with `kprobe`/`kretprobe`.
- Policy topology is read from sysfs at startup. CPU hotplug or policy changes made while the tool is running are not refreshed.
- Histogram rows begin with frequencies reported by sysfs and grow to include additional observed frequencies.
- Frequency events cross the BPF/userspace boundary through a bounded queue. A warning is displayed if queue pressure drops events.
- When stdout is not a TTY, color is disabled and no-clear behavior is enabled automatically.
- Process terminations are not tracked. Once an event is recorded, it remains in the tool's history until the tool exits.
