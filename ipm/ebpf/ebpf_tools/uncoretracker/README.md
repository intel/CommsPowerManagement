# uncoretracker

Live view of per-package/die (or per-cluster, on TPMI systems) uncore
frequency configuration: the current `min_freq_khz` / `max_freq_khz`
limits, the actual `current_freq_khz`, and who last changed each limit
(process name, pid, the value they set, and how long ago).

Min/max writes are captured with eBPF `fexit` hooks on the
`intel_uncore_frequency` driver's write path (`uncore_write_control_freq()`
on older kernels, `uncore_write()` on newer kernels where the former is
inlined away), recording the writing process's pid/comm and the requested
value into a small BPF hash map keyed by `(package, die, domain, min|max)`. Every
successful write is also pushed onto a small BPF queue so user-space can
fold it into a per-limit set of every distinct process name observed
writing it since the tool started (most recent 5, oldest evicted first).
The actual min/max/current values are polled straight from sysfs on a
timer.

`-a/--allowed COMM` names the expected "good" actor: its writes are
colored green and any other writer is colored red (or bracketed as
`!name!` on non-color terminals), both in the last-changed-by column and
in the writer-history summary.

## Build

```sh
make -C ebpf/user-tools/uncoretracker
```

Requires clang, libbpf-dev, bpftool, and a kernel exposing BTF at
`/sys/kernel/btf/vmlinux` (`CONFIG_DEBUG_INFO_BTF=y`), plus the
`intel_uncore_frequency` kernel module loaded (sysfs entries under
`/sys/devices/system/cpu/intel_uncore_frequency/`).

## Usage

```
uncoretracker [--help] [-i SEC] [-C] [-a COMM] [-v]

  -i, --interval=SEC   Refresh interval in seconds (default: 1)
  -C, --no-clear        Do not clear the terminal between refreshes
  -a, --allowed=COMM    Expected "good" actor to color green; any other writer is colored red
  -v, --verbose          Verbose libbpf debug output
```

Example output (min/max rows per package/die/cluster, plus a writer-history
summary below the table so it doesn't clutter each row):

```
uncoretracker - uncore frequency config monitor  (Ctrl-C to exit)
CLUSTER                 MIN(MHz)   MAX(MHz)   CUR(MHz)   LIMIT    LAST CHANGED BY
---------------------------------------------------------------------------------
pkg0/die0                    800       2400       1600   min      no writes observed
                                                         max      cpupower[4213] -> 2400 MHz (12.4s ago)
pkg1/die0 (cluster 3)        800       2000       1400   min      powerctld[318] -> 800 MHz (3.2m ago)
                                                         max      no writes observed

Writer history (since start):
  pkg0/die0             min: -
                        max: cpupower, tuned
  pkg1/die0 (cluster 3) min: powerctld
                        max: -
```

On MSR-based systems each package/die has one sysfs entry
(`package_NN_die_MM`), so `pkg<P>/die<D>` is already a unique label. On
TPMI systems there is one sysfs entry per fabric cluster (`uncoreNN`), and
several clusters can report the same `package_id`/`die_id`/`fabric_cluster_id`
(a known quirk of the driver), so the label appends the TPMI domain/cluster
index as a `(cluster N)` note to disambiguate clusters that share a
package/die — with its `agent_types` (e.g. `io`) appended too when the
driver exposes that sysfs entry, which is kernel-version dependent. Only
if a cluster's package/die couldn't be determined at all does the label
fall back to the raw sysfs directory name.

The BPF write-event hooks key the last-writer/writer-history data by
`(package, die, domain, min|max)`. A write via the legacy
`package_*_die_*` path reports a broadcast domain that applies to every
cluster sharing that package/die, so on a TPMI system those rows can
show identical last-changed-by and history entries even though only one
underlying write occurred.

Run with `-h` for the full help text.
