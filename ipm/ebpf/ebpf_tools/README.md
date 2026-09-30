# eBPF Performance Software v26.09

This tarball contains the eBPF performance software user tools.
Each tool is self contained and is built with its own Makefile.

## Tools

- `usertools/freqtracker` - tracks per-CPU frequency requests and actual frequency transitions.
- `usertools/uncoretracker` - live view of per-package/die uncore frequency config (min/max/current) and who last changed each limit.

## Building

Each tool is built independently, for example:

```
make -C usertools/freqtracker
```

See the README.md inside each tool directory for the build requirements and usage details.

## Structure of this tarball:

```
ebpf_tools/
├── freqtracker
│   ├── freqtracker.bpf.c
│   ├── freqtracker.c
│   ├── freqtracker.h
│   ├── Makefile
│   └── README.md
├── LICENSE
├── licenses_supplementary.txt
├── README.md
└── uncoretracker
    ├── Makefile
    ├── README.md
    ├── uncoretracker.bpf.c
    ├── uncoretracker.c
    └── uncoretracker.h
```
