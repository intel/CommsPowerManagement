# OS/BIOS Mailbox

The OS/BIOS mailbox provides control and discovery support for various Power Management features including ISS, FACT, PBF, and CLOS.

## Mailbox Registers

* OS_MAILBOX_INTERFACE (MSR 0xB0) or (CSR 31:30.1 offset 0xA4)

|  31     | 30:29      | 28:16            | 15:8           | 7:0       |
|---------|------------|------------------|----------------|-----------|
|RUN_BUSY | Reserved   | PARAMETER        |SUB_COMMAND     | COMMAND   |
|1        | 00         | 0 0000 0000 0000 | sub-command ID | 0111 1111 |

* OS_MAILBOX_DATA (MSR 0xB1) OR (CSR 31:30.1 offset 0xA0)

|   31:0   |
|----------|
|   DATA   |
|Data Field|

## Mailbox Command IDs

The OS/BIOS mailbox command IDs are encoded as shown in the table below.

Table: BIOS and OS Mailbox Command IDs

|    |BIOS and OS mailbox command encoding|      |    |   |
|----|------------------------------------|------|----|---|
|    |Main command ID = 0x7F               |subcommand[7:0]|subcmd_type[7:4]|subcmd[3:0]|
|[ISS](#iss):|[CONFIG_TDP_GET_LEVELS_INFO](#config_tdp_get_levels_info)       | 0x0 | 0 | 0 |
|    |[CONFIG_TDP_GET_CONFIG_TDP_CONTROL](#config_tdp_get_config_tdp_control) | 0x1 | 0 | 1 |
|    |[CONFIG_TDP_SET_CONFIG_TDP_CONTROL](#config_tdp_set_config_tdp_control) | 0x2 | 0 | 2 |
|    |[CONFIG_TDP_GET_TDP_INFO](#config_tdp_get_tdp_info)                     | 0x3 | 0 | 3 |
|    |[CONFIG_TDP_GET_PWR_INFO](#config_tdp_get_pwr_info)                     | 0x4 | 0 | 4 |
|    |[CONFIG_TDP_GET_TJMAX_INFO](#config_tdp_get_tjmax_info)                 | 0x5 | 0 | 5 |
|    |[CONFIG_TDP_GET_CORE_MASK](#config_tdp_get_core_mask)                   | 0x6 | 0 | 6 |
|    |[CONFIG_TDP_GET_TURBO_LIMIT_RATIOS](#config_tdp_get_turbo_limit_ratios) | 0x7 | 0 | 7 |
|    |[CONFIG_TDP_SET_LEVEL](#config_tdp_set_level)                           | 0x8 | 0 | 8 |
|    |[CONFIG_TDP_GET_UNCORE_P0_P1_INFO](#config_tdp_get_uncore_p0_p1_info)   | 0x9 | 0 | 9 |
|    |[CONFIG_TDP_GET_P1_INFO](#config_tdp_get_p1_info)                       | 0xa | 0 | a |
|    |[CONFIG_TDP_GET_MEM_FREQ](#config_tdp_get_mem_freq)                     | 0xb | 0 | b |
|[FACT](#fact):|[CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_NUMCORES](#config_tdp_get_fact_hp_turbo_limit_numcores) | 0x10 | 1 | 0 |
|    |[CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_RATIOS](#config_tdp_get_fact_hp_turbo_limit_ratios)               | 0x11 | 1 | 1 |
|    |[CONFIG_TDP_GET_FACT_LP_CLIPPING_RATIO](#config_tdp_get_fact_lp_clipping_ratio)                       | 0x12 | 1 | 2 |
|[PBF](#pbf):|[CONFIG_TDP_PBF_GET_CORE_MASK_INFO](#config_tdp_pbf_get_core_mask_info)                       | 0x20 | 2 | 0 |
|    |[CONFIG_TDP_PBF_GET_P1HI_P1LO_INFO](#config_tdp_pbf_get_p1hi_p1lo_info) | 0x21 | 2 | 1 |
|    |[CONFIG_TDP_PBF_GET_TJ_MAX_INFO](#config_tdp_pbf_get_tj_max_info)       | 0x22 | 2 | 2 |
|    |[CONFIG_TDP_PBF_GET_TDP_INFO](#config_tdp_pbf_get_tdp_info)             | 0x23 | 2 | 3 |
|    |Main command ID = 0xD0                                                  |      |   |   |
|[CLOS](#clos):|[CLOS_PQR_ASSOC](#clos_pqr_assoc)                             | 0x0  | 0 | 0 |
|    |[CLOS_PM_CLOS](#clos_pm_clos)                                           | 0x1  | 0 | 1 |
|    |[CLOS_PM_QOS_CONFIG](#clos_pm_qos_config)                               | 0x2  | 0 | 2 |
|    |[CLOS_STATUS](#clos_status)                                             | 0x3  | 0 | 3 |

The following acronyms are uses in this document:

* ISS = SST-PP
* PBF = SST-BF
* FACT = SST-TF

The following codes may be returned:

* NO_ERROR = 0x0
* INVALID_COMMAND = 0x1
* ILLEGAL_DATA = 0x16

# Command ID Details

## ISS:

### CONFIG_TDP_GET_LEVELS_INFO
This command allows software to discover ISS information.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_LEVELS_INFO|15:8|8|

MAILBOX_DATA

- None

Output:

MAILBOX_DATA

|Bit|Name|Description               |Notes    |
|---|----|--------------------------|---------|
|31   |ENABLED          |RO - Indicates if the processor supports CONFIG_TDP extension (ISS).| |
|30:25|RESERVED         |Reserved| |
|24:24|LOCK|RO - Returns the lock bit setting in CONFIG_TDP_CONTROL MSR||
|23:16|CURRENT_CONFIG_TDP_LEVEL |RO - The currently active Config TDP Level                          | |
|15:8 |CONFIG_TDP_LEVELS|RO - Maximum Config TDP Level supported                             |RO: 4 for ICX and CPX|
|7:0  |VERSION          |RO - Version of CONFIG_TDP supported by the hardware                |RO: 1 for CLX, 2 for CPX, 3 for ICX|

Error Codes: NO_ERROR


### CONFIG_TDP_GET_CONFIG_TDP_CONTROL

This command allows software to discover if PBF/FACT is supported for a particular ConfigTDP level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_CONFIG_TDP_CONTROL|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index | RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|17:17|PBF_ENABLED|RO. Returns if PBF is enabled||
|16:16|FACT_ENABLED|RO. Returns if FACT is enabled||
|1:1|PBF_SUPPORT|RO. Returns if PBF is supported||
|0:0|FACT_SUPPORT|RO. Returns if FACT is supported||

Error Codes: NO_ERROR; ILLEGAL_DATA

### CONFIG_TDP_SET_CONFIG_TDP_CONTROL

This command allows software to enable/disable PBF and FACT for the current active ConfigTDP level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_SET_CONFIG_TDP_CONTROL|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|PBF_ENABLE |RW. Default=0. When set to 1 PBF will be enabled|17:17|1|
|FACT_ENABLE|RW. Default=0. When set to 1 FACT will be enabled|16:16|1|

Output:

MAILBOX_DATA

- None

Error Codes: NO_ERROR; INVALID_COMMAND

### CONFIG_TDP_GET_TDP_INFO

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_TDP_INFO|15:8|8|

MAILBOX_DATA

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|Configuration Index|RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|23:16|TDP_RATIO|ConfigTDP Ratio for this config level||
|14:0 |PKG_TDP|Power for this TDP level. In 1W unit||

Error Codes: NO_ERROR; ILLEGAL_DATA


### CONFIG_TDP_GET_PWR_INFO

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_PWR_INFO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|30:16  |PKG_MIN_PWR| Min pkg power setting allowed for this config TDP level. Lower values will be clamped up to this value. Units defined in PACKAGE_POWER_SKU_MSR[PWR_UNIT]. Similar to PACKAGE_POWER_SKU[PKG_MIN_PWR].||
|14:0   |PKG_MAX_PWR|Max pkg power setting allowed for this config TDP level1. Higher values will be clamped down to this value. Units defined in PACKAGE_POWER_SKU_MSR[PWR_UNIT]. Similar to PACKAGE_POWER_SKU[PKG_MAX_PWR].||

Error Codes: NO_ERROR; ILLEGAL_DATA

### CONFIG_TDP_GET_TJMAX_INFO

This command allows software to discover the Tprochot (Tjmax) of the selected ISS level.

Input:

MAI##CONFIG_TDP_GET_TDP_INFO

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_TDP_INFO|15:8|8|

MAILBOX_DATA

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|Configuration Index|RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|23:16|TDP_RATIO|ConfigTDP Ratio for this config level||
|14:0 |PKG_TDP|Power for this TDP level. In 1W unit||

Error Codes: NO_ERROR; ILLEGAL_DATA

### CONFIG_TDP_GET_CORE_MASK

This command allows software to discover the enabled logical core mask of the selected ISS level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_CORE_MASK|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index |  RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|
|Mask index| RW (default = 0) - word index of core mask. 0 returns bits 31:0, 1 returns bits 63:32 and so on    |15:8|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note    |
|---|---------|-----------------|--------|
|31:0   |CORE_MASK|The logical coremask of the enabled cores.| |

Error Codes: NO_ERROR; ILLEGAL_DATA

### CONFIG_TDP_GET_TURBO_LIMIT_RATIOS

This commands returns the turbo ratio limit of the selected config_tdp level, AVX level, and buckets.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_TURBO_LIMIT_RATIOS|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index  |  RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|
|TRL word index|RW(default =0) - word of turbo ratio limits. 0 returns bits 31:0 (buckets 0-3); 1 returns bits 63:32 (buckets 4-7)|15:8|8|
|AVX Level     |RW (default = 0). A valid AVX level, 0 - SSE, 1- AVX2, 2-AVX3 |16:23|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|31:24|RATIOS_3 or 7|Turbo ratio limit value for the bucket defined by input||
|23:16|RATIOS_2 or 6|Turbo ratio limit value for the bucket defined by input||
|15:8 |RATIOS_1 or 5|Turbo ratio limit value for the bucket defined by input||
|7:0  |RATIOS_0 or 4|Turbo ratio limit value for the bucket defined by input||

Error Codes: NO_ERROR; ILLEGAL_DATA

### CONFIG_TDP_SET_LEVEL

Select configTDP level. BIOS and software must use this mailbox command to select ISS config level.

Pcode should disable this command and return error if CONFIG_TDP_LOCK bit is set in CONFIG_TDP_CONTROL MSR/CFG register.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_SET_LEVEL|15:8|8|

MAILBOX_DATA

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|CONFIG_TDP_LEVEL|A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

- None

Error Codes: NO_ERROR; ILLEGAL_DATA


### CONFIG_TDP_GET_UNCORE_P0_P1_INFO

This commands returns the uncore P0 and P1 frequency of the selected config_tdp level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_UNCORE_P0_P1_INFO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|15:8|Uncore P1|P1 ratio for Uncore||
|7:0|Uncore P0|Max ratio limit for Uncore||

Error Codes: NO_ERROR; ILLEGAL_DATA


### CONFIG_TDP_GET_P1_INFO

This commands returns the P1 ratio for all license classes of the selected config_tdp level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_P1_INFO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|31:24|RESERVED|Reserved| |
|23:16|AVX3 P1|AVX3 P1 ratio for this config level||
|15:8|AVX2 P1|AVX2 P1 ratio for this config level||
|7:0|SSE P1|Non AVX P1 ratio for this config level||


Error Codes: NO_ERROR; ILLEGAL_DATA 

### CONFIG_TDP_GET_MEM_FREQ

This command allows software to discover the max allowed memory frequency of the selected ISS level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_MEM_FREQ|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|31:8|RESERVED|Reserved| |
|7:0|MEMORY FREQ|The max allowed memory frequency for this config level. ||

Error Codes: NO_ERROR; ILLEGAL_DATA

## FACT

### CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_NUMCORES

This command allows software to discover the FACT high priority core count of the specific config.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_NUMCORES|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|
|Word Index        |RW(default =0) - word of turbo ratio limits. 0 returns bits 31:0 (buckets 0-3); 1 returns bits 63:32 (buckets 4-7) |15:8|8|


Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|31:24|Num Cores 3 or 7|RO. Returns the High Priority core count for bucket 3 or 7||
|23:16|Num Cores 2 or 6|RO. Returns the High Priority core count for bucket 2 or 6||
|15:8 |Num Cores 1 or 5|RO. Returns the High Priority core count for bucket 1 or 5||
|7:0  |Num Cores 0 or 4|RO. Returns the High Priority core count for bucket 0 or 4||

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

### CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_RATIOS

This command allows software to discover the Turbo Ratio Limit of FACT high priority cores for the specific config and AVX level.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_FACT_HP_TURBO_LIMIT_RATIOS|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|
|Word Index        |RW(default =0) - word of turbo ratio limits. 0 returns bits 31:0 (buckets 0-3); 1 returns bits 63:32 (buckets 4-7)|15:8|8|
|AVX Level        |RW(default = 0). A valid AVX level|23:16|8|


Output:

MAILBOX_DATA

|Bit|Name |Description            |Note|
|---|-----|-----------------------|----|
|31:24|RATIOS_3 or 7|RO. Returns the turbo ratio limit value of the specified FACT bucket and AVX level||
|23:16|RATIOS_2 or 6|RO. Returns the turbo ratio limit value of the specified FACT bucket and AVX level||
|15:8 |RATIOS_1 or 5|RO. Returns the turbo ratio limit value of the specified FACT bucket and AVX level||
|7:0  |RATIOS_0 or 4|RO. Returns the turbo ratio limit value of the specified FACT bucket and AVX level||

Note
:
Pcode will return 0x0 for the empty buckets. For example, on CPX/ICX, bucket3-7 should return 0.

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

### CONFIG_TDP_GET_FACT_LP_CLIPPING_RATIO

This command allows software to discover the frequency clipping ratio of FACT low priority cores for the specific config.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_GET_FACT_LP_CLIPPING_RATIO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index| RW (default = 0) - A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|31:24|RESERVED|Reserved||
|23:16|LP_Clipping_ratio_AVX3|Returns the value of frequency clipping for the low priority cores of AVX3 license||
|15:8 |LP_Clipping_ratio_AVX2|Returns the value of frequency clipping for the low priority cores of AVX2 license||
|7:0  |LP_Clipping_ratio_SSE |Returns the value of frequency clipping for the low priority cores of SSE license||

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

## PBF

### CONFIG_TDP_PBF_GET_CORE_MASK_INFO

This command allows software to read the PBF_P1_HI_CORE_MASK.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_PBF_GET_CORE_MASK_INFO|15:8|8|

MAILBOX_DATA

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|Configuration index |A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|
|Mask index| Word index of core mask. 0 for bits 31:0, 1 for bits 63:32 and so on    |15:8|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note    |
|---|---------|-----------------|--------|
|31:0   |P1_HI_CORE_MASK|Value of PBF_P1_HI_CORE_MASK for index provided as input. This is a logical core ID mask.||

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

### CONFIG_TDP_PBF_GET_P1HI_P1LO_INFO

Software discovers P1_Hi/P1_Lo using this command.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_PBF_GET_P1HI_P1LO_INFO|15:8|8|

MAILBOX_DATA

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|Configuration Index|A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note    |
|---|---------|-----------------|--------|
|15:8|P1_HI|base frequency for high priority cores||
|7:0|P1_LO|base frequency for low priority cores||

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

### CONFIG_TDP_PBF_GET_TJ_MAX_INFO

Software discovers PBF Tjmax and Tcontrol offset using this command.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_PBF_GET_TJ_MAX_INFO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index |A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|15:8   |T_CONTROL|RO. Fan Temperature Target Offset. (This field is reserved for CPX.)*||
|7:0    |T_PROHOT|RO. Maximum junction temperature in this configuration.||

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND

### CONFIG_TDP_PBF_GET_TDP_INFO

Software discovers PBF TDP using this command.

Input:

MAILBOX_INTERFACE

|Field|Description    |Bits|Width|
|-----| --------------|----|-----|
|COMMAND|0x7F|7:0|8|
|SUB_COMMAND|CONFIG_TDP_PBF_GET_TDP_INFO|15:8|8|

MAILBOX_DATA

|Field|Description      |Bits|Width|
|-----|-----------------|----|-----|
|Configuration index |A valid configuration index in the range specified by the max configurations field in CONFIG_TDP_GET_LEVELS_INFO.|7:0|8|

Output:

MAILBOX_DATA

|Bit|Name     |Description      |Note|
|---|---------|-----------------|----|
|14:0|TDP| TDP = SKU TDP - PBF_CONFIG_0_TDP_OFFSET. Pcode returns the resolved TDP in this configuration. In 1W units||


Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND


## CLOS


### CLOS_PQR_ASSOC

This command provides read/write access to the per core CLOS setting.

Input:

MAILBOX_INTERFACE

|Field      |Description    |  Bits|Width|
|-----------|---------------|------|-----|
|COMMAND    |0x7F           |   7:0|    8|
|SUB_COMMAND|CLOS_PQR_ASSOC |  15:8|    8|
|Core_ID    |Specify core ID| 23:16|	8|
|WRITE      |Specify Read (0) or Write (1) command|24:24|1|

MAILBOX_DATA

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|RMID	|Specify RMID. (Not used for CPX)	|3:0	|4|
|CLOS	|Specify CLOS	|17:16	|2|

Output:

Return current values.

Error Codes: NO_ERROR; ILLEGAL_DATA; INVALID_COMMAND


### CLOS_PM_CLOS

This command provides read/write access to CLOS priority setting per class. Pcode keeps a memory variable array of CLOS priority setting. CPX supports four CLOS classes.

Input:

MAILBOX_INTERFACE

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|COMMAND	|0xD0	|7:0	|8|
|SUB_COMMAND	|CLOS_PM_CLOS	|15:8	|8|
|CLOS_ID	|Specify CLOS ID	|17:16	|2|
|WRITE	|Specify Read (0) or Write (1) command	|24:24	|1|

MAILBOX_DATA

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|EPP	|Used as a hint to the HW. The OS may write a range of values from 0 (performance preference) to 0xF (energy efficiency preference). Influences the result of the hardware's energy efficiency and performance optimization policies.(Not used in CPX)	|3:0	|4|
|CLOS_PROPORTIONAL_PRIORITY	|Used to set frequency weight when CLOS_PRIORITY_TYPE is set to Proportional (freq_weight=15-CLOS_PROPORTIONAL_PRIORITY)	|7:4	|4|
|CLOS_MIN	|Hold the minimum PM CLOS frequency ratio (100MHz bins) for this class of service.	|15:8	|8|
|CLOS_MAX	|Hold the maximum PM CLOS frequency ratio (100MHz bins) for this class of service.	|23:16	|8|
|CLOS_DESIRED	|When set to zero, HW autonomous selection determines the performance target. When set to a non-zero value, in the range of Lowest Performance to Highest Performance, conveys an explicit performance request hint to the hardware; effectively disabling HW Autonomous selection. The Desired Performance input is non-constraining in terms of Performance and Energy Efficiency optimizations, which are independently controlled. (Not used in CPX)	|31:24	|8|

Output:

Return current values.

Error Codes: NO_ERROR; INVALID_COMMAND


### CLOS_PM_QOS_CONFIG

This command provides read/write access to PM_QOS_CONFIG setting of CLOS.

Input:

MAILBOX_INTERFACE

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|COMMAND	|0xD0	|7:0	|8|
|SUB_COMMAND	|CLOS_PM_QOS_CONFIG	|15:8	|8|
|WRITE	|Specify Read (0) or Write (1) command	|24:24	|1|

MAILBOX_DATA

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|DISABLE_ENERGY_REPORTING|RW1S. Set to 1 to disables all energy reporting. Default is 0x0. Not used in CPX.	|0:0	|1|
|ENABLE_CLOS	|RW. This bit allows user to select the inputs ( HWP[0] vs. CLOS[1] ) to RAPL Prioritization.	|1:1	|1|
|CLOS_PRIORITY_TYPE	|RW: 0x0 (Default) =Proportional. 0x1=Ordered Throttling.	|2:2	|1|
|OOB_PRIORITY_ENABLE	|RW. 0x0 (Default)                                              |3:3	|1|

Output:

Return current values.

Error Codes: NO_ERROR; INVALID_COMMAND

### CLOS_STATUS

This command indicates when an Excursion has occurred in CLOS prioritization. All values in this register are updated by Pcode and typically read or cleared by SW.

Input:

MAILBOX_INTERFACE

|Field	|Description	|Bits	|Width|
|-------|---------------|-------|-----|
|COMMAND	|0xD0	|7:0	|8|
|SUB_COMMAND	|CLOS_STATUS	|15:8	|8|
|CLOS_ID	|Specify CLOS ID	|17:16	|2|
|WRITE	|Specify Read (0) or Write (1) command	|24:24	|1|

MAILBOX_DATA

|Field          |Description	|Bits	|Width|
|---------------|---------------|-------|-----|
|Reserved_for_Excursion_To_Desired |	Reserved for future use.	|1:1	|1|
|Excursion_To_Minimum	|If set (1), an excursion to Minimum Performance has occurred. SW must clear this bit by writing a zero (0). Pcode will not allow SW to write a 1 to this field.	|2:2	|1|

Output:

Return current values.

Error Codes: NO_ERROR; INVALID_COMMAND

