---
subsystem: slm
provides: [scoped, rule-engine, neural, intent-classify, knowledge-base, conversation-context]
depends_on: [mm, sys]
optional: [neural, conversation-context]
# `scoped` is a manifest-narrowed model. The prose lists sched/ipc/dev/boot; in the shipped ring-0 design the SLM is called directly from the terminal loop. See Task 2.
---

# SLM Runtime Specification

## Overview

The SLM (Small Language Model) runtime is the central intelligence of the AUTON kernel. It provides a pluggable architecture with two backends: a rule engine (keyword/pattern matching and decision trees) for minimal hardware, and a neural backend (GGUF/ONNX model loading with CPU-based INT4/INT8 quantized inference) for systems with sufficient RAM. All kernel subsystems communicate with the SLM through a structured intent system. The SLM maintains a knowledge base of devices, drivers, and packages, and preserves conversation context for multi-step operations.

## Data Structures

### Intent System

```c
/* Intent categories: all SLM interactions are classified into one of these */
typedef enum slm_intent {
    SLM_INTENT_HARDWARE_IDENTIFY  = 0,  /* "what is this PCI device?" */
    SLM_INTENT_DRIVER_SELECT      = 1,  /* "which driver for this NIC?" */
    SLM_INTENT_INSTALL_CONFIGURE  = 2,  /* "partition /dev/sda, format ext2" */
    SLM_INTENT_APP_INSTALL        = 3,  /* "install a web server" */
    SLM_INTENT_SYSTEM_MANAGE      = 4,  /* "check disk usage", "restart service" */
    SLM_INTENT_TROUBLESHOOT       = 5,  /* "why is the network down?" */
    SLM_INTENT_COUNT              = 6
} slm_intent_t;

/* Sub-commands per intent (selected examples) */
typedef enum slm_sub_command {
    /* HARDWARE_IDENTIFY */
    SLM_SUB_IDENTIFY_PCI      = 0x0000,
    SLM_SUB_IDENTIFY_PLATFORM = 0x0001,
    SLM_SUB_IDENTIFY_USB      = 0x0002,

    /* DRIVER_SELECT */
    SLM_SUB_DRV_SELECT        = 0x0100,
    SLM_SUB_DRV_CONFIGURE     = 0x0101,
    SLM_SUB_DRV_FALLBACK      = 0x0102,  /* select alternate driver */

    /* INSTALL_CONFIGURE */
    SLM_SUB_PARTITION_DISK    = 0x0200,
    SLM_SUB_FORMAT_FS         = 0x0201,
    SLM_SUB_MOUNT_FS          = 0x0202,
    SLM_SUB_NETWORK_CONFIG    = 0x0203,
    SLM_SUB_HOSTNAME_SET      = 0x0204,

    /* APP_INSTALL */
    SLM_SUB_PKG_SEARCH        = 0x0300,
    SLM_SUB_PKG_INSTALL       = 0x0301,
    SLM_SUB_PKG_REMOVE        = 0x0302,
    SLM_SUB_PKG_UPDATE        = 0x0303,

    /* SYSTEM_MANAGE */
    SLM_SUB_SVC_START         = 0x0400,
    SLM_SUB_SVC_STOP          = 0x0401,
    SLM_SUB_SVC_STATUS        = 0x0402,
    SLM_SUB_RESOURCE_QUERY    = 0x0403,
    SLM_SUB_LOG_QUERY         = 0x0404,

    /* TROUBLESHOOT */
    SLM_SUB_DIAG_NETWORK      = 0x0500,
    SLM_SUB_DIAG_STORAGE      = 0x0501,
    SLM_SUB_DIAG_MEMORY       = 0x0502,
    SLM_SUB_DIAG_GENERAL      = 0x0503,
} slm_sub_command_t;

/* Intent result structure */
typedef struct slm_intent_result {
    slm_intent_t    intent;
    int32_t         status;             /* 0=success, negative=error */
    char            response[2048];     /* human-readable response text */
    uint32_t        response_len;
    char            action_data[1024];  /* machine-parseable action data */
    uint32_t        action_data_len;
    int             requires_followup;  /* 1 if multi-step, more actions needed */
} slm_intent_result_t;
```

### Backend Selection

```c
/* SLM backend type */
typedef enum slm_backend_type {
    SLM_BACKEND_RULE_ENGINE,    /* keyword/pattern matching + decision trees */
    SLM_BACKEND_NEURAL,         /* neural network inference */
} slm_backend_type_t;

/* Backend capabilities */
typedef struct slm_backend_caps {
    slm_backend_type_t type;
    uint64_t min_memory;        /* minimum memory required */
    int      supports_context;  /* 1 if conversation context is maintained */
    int      supports_freeform; /* 1 if free-form text queries work */
    int      accuracy_tier;     /* 0=basic, 1=good, 2=excellent */
} slm_backend_caps_t;

/* Backend interface: both rule engine and neural implement this */
typedef struct slm_backend_ops {
    /* Initialize the backend. Returns 0 on success. */
    int (*init)(uint64_t available_memory);

    /* Process a structured intent request.
     * Reads intent + sub_command + args, writes result. */
    int (*process_intent)(slm_intent_t intent, slm_sub_command_t sub_cmd,
                          const char *args, uint32_t args_len,
                          slm_intent_result_t *result);

    /* Process a free-form text query (neural backend only, rule engine
     * falls back to keyword extraction).
     * Returns classified intent + result. */
    int (*process_text)(const char *text, uint32_t text_len,
                        slm_intent_result_t *result);

    /* Shutdown the backend, free resources. */
    void (*shutdown)(void);

    /* Get backend capabilities. */
    const slm_backend_caps_t *(*get_caps)(void);
} slm_backend_ops_t;
```

### Rule Engine Backend

```c
/* Keyword-to-intent mapping entry */
typedef struct rule_keyword {
    const char     *keyword;        /* keyword string (lowercase) */
    slm_intent_t    intent;         /* mapped intent */
    int             weight;         /* match confidence weight (0-100) */
} rule_keyword_t;

/* Pattern matching rule */
typedef struct rule_pattern {
    const char     *pattern;        /* simple glob-like pattern */
    slm_intent_t    intent;
    slm_sub_command_t sub_cmd;
    const char     *action_template; /* template for action_data */
} rule_pattern_t;

/* Decision tree node for driver selection */
typedef struct rule_decision_node {
    const char *condition_field;    /* field to check (e.g., "class", "vendor") */
    const char *condition_value;    /* value to match */
    const char *result;             /* driver name or NULL if branch */
    struct rule_decision_node *yes_branch;
    struct rule_decision_node *no_branch;
} rule_decision_node_t;

/* Rule engine state */
typedef struct rule_engine {
    rule_keyword_t      *keywords;
    uint32_t             keyword_count;
    rule_pattern_t      *patterns;
    uint32_t             pattern_count;
    rule_decision_node_t *driver_tree;   /* decision tree root for driver selection */
    int                  initialized;
} rule_engine_t;

/* Tokenizer for text processing */
#define TOKEN_MAX_COUNT     64
#define TOKEN_MAX_LEN       32

typedef struct token_list {
    char     tokens[TOKEN_MAX_COUNT][TOKEN_MAX_LEN];
    uint32_t count;
} token_list_t;
```

### Neural Backend

```c
/* Model format.
 *
 * AUTON is the shipping format: a flat, run-in-place layout so a freestanding
 * kernel can execute a model directly out of a boot module with no parsing, no
 * allocation, and no relocation. GGUF and ONNX are container formats that
 * assume a host runtime; they remain aspirational.
 *
 * Every generated kernel MUST implement MODEL_FORMAT_AUTON, on any target. */
typedef enum model_format {
    MODEL_FORMAT_AUTON,     /* AUTON flat format */
    MODEL_FORMAT_GGUF,      /* aspirational */
    MODEL_FORMAT_ONNX,      /* aspirational */
} model_format_t;

/* Quantization level */
typedef enum quant_type {
    QUANT_NONE  = 0,        /* FP32 (not recommended for kernel) */
    QUANT_FP16  = 1,        /* FP16 */
    QUANT_INT8  = 2,        /* 8-bit integer quantization */
    QUANT_INT4  = 3,        /* 4-bit integer quantization (most compact) */
} quant_type_t;

/* AUTON flat model header: ten little-endian u32 fields, no padding.
 *
 * Target-neutral by construction — byte order is fixed little-endian on the
 * wire, so a big-endian target byte-swaps on load rather than forking the
 * format. One exporter serves every generated kernel. */
typedef struct flat_header {
    uint32_t magic;         /* 0x4E4F5455 "UTON" */
    uint32_t version;       /* exact-match; 3 since the device table. See
                             * "Format Versioning" — a v2 reader handed a v3
                             * file parses the table as tokenizer entries. */
    uint32_t dim;
    uint32_t hidden_dim;
    uint32_t n_layers;
    uint32_t n_heads;
    uint32_t n_kv_heads;    /* GQA: n_heads % n_kv_heads == 0 */
    uint32_t vocab_size;
    uint32_t seq_len;
    uint32_t quant;         /* quant_type_t */
} __attribute__((packed)) flat_header_t;

/* Tensor descriptor */
typedef struct tensor_desc {
    char        name[64];       /* tensor name */
    uint32_t    n_dims;         /* number of dimensions */
    uint32_t    dims[4];        /* dimension sizes */
    quant_type_t quant;         /* quantization type */
    uint64_t    offset;         /* offset in weight data */
    uint64_t    size_bytes;     /* size of tensor data */
    void       *data;           /* pointer to weight data in SLM pool */
} tensor_desc_t;

/* Neural model state */
#define MODEL_MAX_TENSORS   512
#define MODEL_MAX_VOCAB     32000
#define MODEL_MAX_CONTEXT   2048    /* max context tokens */

typedef struct neural_model {
    model_format_t  format;
    quant_type_t    quant;

    /* Architecture */
    uint32_t        vocab_size;
    uint32_t        embedding_dim;
    uint32_t        n_layers;
    uint32_t        n_heads;
    uint32_t        n_kv_heads;     /* for GQA (Grouped Query Attention) */
    uint32_t        context_len;    /* max context window */
    uint32_t        hidden_dim;     /* FFN intermediate size */

    /* Tensors */
    tensor_desc_t   tensors[MODEL_MAX_TENSORS];
    uint32_t        tensor_count;

    /* Tokenizer */
    char            vocab[MODEL_MAX_VOCAB][32];  /* token strings */
    float          *token_scores;                /* token merge scores */
    uint32_t        vocab_loaded;

    /* Inference state */
    void           *kv_cache;       /* key-value cache (in SLM pool) */
    uint32_t        kv_cache_pos;   /* current position in KV cache */
    float          *logits;         /* output logits buffer */
    int             model_loaded;
} neural_model_t;

/* Inference configuration */
typedef struct inference_config {
    float    temperature;       /* sampling temperature (0.0 = greedy) */
    float    top_p;             /* nucleus sampling threshold */
    uint32_t max_tokens;        /* max tokens to generate */
    int      greedy;            /* 1 = always pick highest logit */
} inference_config_t;
```

### Prompt Contract (REQUIRED)

**The highest-impact contract in this subsystem.** A kernel that gets it wrong ships a model
that looks trained and answers nothing.

The model is trained on a stream of

```
<bos> question <sep> answer <eos>
```

so `<sep>` is the boundary between asking and answering. The kernel MUST build its prompt as
`<bos> question <sep>` and generate from there. Ending the prompt at the separator is what
places generation in *answer* position.

Feeding the bare question makes the model continue the **question**: it emits question
fragments, echoes the prompt, and prints `<sep>` as visible text. Observed directly — a model
whose graded score rose from 42% to 78% on this change alone, with no retraining.

Special token ids are fixed by the vocabulary and MUST NOT be renumbered. Every generated
kernel, on every target, uses these:

| id | token | meaning |
|---|---|---|
| 0 | `<pad>` | stop generation |
| 1 | `<unk>` | out of vocabulary |
| 2 | `<bos>` | prompt start |
| 3 | `<eos>` | stop generation |
| 4 | `<sep>` | question/answer boundary |

Generation stops on `<pad>`, `<eos>`, **or `<sep>`** — a generated separator means the model
has started a new question/answer pair, which is prompt grammar, not answer text.

Output cap: answers run to roughly 30-40 tokens, since a capability note is a full sentence.
A cap that truncates mid-sentence scores as garbage. **The output buffer MUST be at least as
large as the cap** — a real and easily generated buffer-overflow path.

### Untrusted Module Validation (REQUIRED)

A boot module is untrusted input: it is whatever the bootloader was handed. Before any pointer
walks into the weight section, the loader MUST verify the declared geometry fits within the
module, computed for the declared quantization mode:

```
expected_weight_bytes(header) <= module_size - sizeof(flat_header_t)
```

Without this, a truncated module passes the header check and then parses its vocabulary from
whatever memory follows it — observed behaviour, fixed by bounds-checking first. This is a
memory-safety requirement, not a robustness nicety, and it applies identically on every
architecture.

Every rejection MUST be distinguishable. A single "load failed" cannot be told apart from "no
model was supplied", which makes a corrupt module look like an intentional rule-engine boot:

| reason | condition |
|---|---|
| bad arguments / too small | null data, wrong format, smaller than a header |
| bad magic | not an AUTON model |
| unsupported version | see "Format Versioning" |
| unsupported quantization | `quant` not implemented by this kernel |
| geometry out of range | layer/head/vocab caps, `dim % n_heads != 0`, any zero dimension |
| truncated | weights or vocabulary run past the module |
| out of memory | runtime buffers could not be allocated |

The kernel MUST print the reason and continue to the rule engine. Honest degradation is the
project convention (`roles.c`, `CAP_ROADMAP`); a silent fallback is not.

### Degenerate Output Guard (REQUIRED)

Generated tokens are not automatically an answer. A small model that loses the thread emits
runs (`machine machine machine`) or short cycles (`driver: driver: driver:`). Printing that is
worse than admitting ignorance, and the kernel has a working rule engine to fall back to.

Reject the generation and fall back when output is:

- empty;
- four or more identical tokens consecutively;
- a period-2 or period-3 cycle repeating at the tail.

The guard MUST be allocation-free and freestanding — one pass plus a bounded tail check — so
it is implementable on the smallest target. It MUST NOT reject legitimate short answers: a
three-token run, a word repeated non-adjacently, and one- or two-token outputs are all valid.

Test both directions. A guard that only executes when a model misbehaves is a guard nobody has
verified; it needs positive cases (runs, cycles, empty) and negative cases (ordinary
sentences) exercised directly.

### Format Versioning (REQUIRED)

`version` is checked for **exact** equality, never as a minimum. A model whose vocabulary
predates `<sep>` cannot be prompted by a kernel that appends id 4 — it would receive a real
word in that position and produce silently wrong output instead of a load error. Exact
matching converts that into an honest rejection.

Bump `version` whenever the byte layout or the special-token contract changes, and bump the
exporter and every generated loader in the **same change**. An exporter and loader that
disagree produce a plausible-looking model that is wrong — the worst available failure mode,
because nothing reports it.

### Shell Idioms — Deterministic, Before the Model (REQUIRED)

People type Linux commands at an OS prompt. **15 of the 65 graded eval prompts are
exactly this** — `lsmod`, `meminfo`, `ip a`, `netstat -tulnp`, `check hw info` —
drawn from real human sessions.

They must be answered by the deterministic path **before** the model is
consulted, for a reason that is not stylistic:

The eval holds its prompts out of the training corpus, so the model never sees
them. The tokenizer builds its vocabulary *from that corpus*. Therefore every
eval-only word is out of vocabulary and arrives as `<unk>`, and a word-level
model cannot act on a token it has no representation for. Measured: **22 of 65
prompts contain a word the model cannot represent, and they fail at 36% against
16% for in-vocabulary prompts** — more than double.

No amount of corpus work fixes this, because the fix is forbidden by the
contamination guard. Substring matching has no vocabulary and is therefore
immune to the problem entirely.

This is the same retrieval-not-generation rule already applied to device facts
and to `is_ip_query`, extended to the class that needs it most.

```c
/* Matched on the raw text with ks_contains, before slm_neural_infer. Returns
 * 1 if the idiom was recognised and answered. */
int slm_shell_idiom(const char *text, slm_intent_result_t *result);
```

| Idiom substrings | Answered from |
|---|---|
| `lsmod`, `modinfo`, `list modules`, `list drivers` | bound drivers, from the driver table |
| `lspci`, `list pci`, `hw info`, `hardware info` | the PCI device list |
| `meminfo`, `free`, `vmstat`, `memory usage` | the memory figure |
| `uname`, `os version`, `kernel version` | self-description; explicitly not Linux |
| `ip a`, `ip addr`, `ifconfig` | the address, where the image has a network |
| `ip route`, `netstat -r`, `routing table` | the gateway |
| `netstat`, `ss -l`, `listening ports`, `net list` | which roles listen, and on what |
| `ps `, `list processes` | there is no process model |
| `df`, `disk usage`, `mount` | what persists, which may be nothing |
| `dmesg`, `boot log`, `klog` | the serial log is not stored |
| `roles`, `what can you be`, `what can you run` | the role list, filtered by manifest |
| `uptime`, `how long` | uptime |

**Rules**

1. **Never invent Linux output.** `ps` is answered by saying there is no process
   model. Emulating `ps` output would be a fabrication, and the rubric grades a
   confident wrong answer worse than an honest decline.
2. **Answer from the same tables the chat already uses**, so an idiom and its
   plain-English equivalent can never disagree.
3. **An idiom for a capability this image lacks is declined by name**, not
   answered generically: `ip a` on an image with no network says there is no
   network, not "I do not know about that".
4. **Longest match wins.** `net list all` must not be caught by a shorter
   pattern that means something else.

## Errata Module (REQUIRED)

"Is this machine safe?" is answered from data the image carries, keyed by its own silicon
identity (hardware-truth H5, `arch/hal.md` category 8). The data is `errata.bin`, a **second boot
module** beside the model, not a section of the model file. Errata change on a vendor's
schedule and models on a training schedule; a separate module is replaced without retraining,
and the model file's exact-version contract is untouched (the PRD's Open Question 3, decided in
w13).

- **Format**: `SLM/tools/errata_format.py`, magic `AERR`, version 1, exact match. Keys are
  `(vendor, family, model, stepping)`, sorted and binary-searched in place. The vendor is part of
  the key: Intel and AMD family/model spaces overlap.
- **Verdicts are precomputed on the host** by `agent/tools/errata_table.py`
  (`build_errata_table.py`). The applicability logic (processor lines; "Plan Fix" is UNKNOWN
  without a microcode revision) exists once. The kernel looks answers up and never re-derives them.
- **Untrusted input**: `errata_open` checks every length before following it, and every record's
  text must be NUL-terminated inside the pool. A module that fails any check is refused whole.
- **No key means not examined.** The answer is never "safe" for silicon no ingested document
  covers. Word it as `machine_safety.py` does: *"This machine has not been examined — that is not
  the same as safe."*
- **Absent module**, same answer, naming the missing module.
- **Every answer cites**: erratum id, title, document, page. The chat never states a verdict
  without the document revision it came from.

Interface: `tests/kernel/errata_lookup_reference/include/errata_lookup.h` is normative
(`errata_open`, `errata_find`, `errata_get`). Verification: `tests/kernel/run_errata_lookup_test.sh`
(a synthetic module, every truncation refused under ASan, the real Intel 682436 module when
cached). Packages ship `assets/errata.bin` scoped to the target's silicon.

## Role table (REQUIRED)

The chat answers "what can you do" and "be an email server" from a table that is **generated**,
not hand-written: `agent/tools/gen_roles.py` emits `build-<svc>/generated/roles_table.c` from
`kernel_spec/catalogue.yaml` during every service build.

A generated tree's `kernel/slm/roles.c` therefore contains the **code and not the data**:

```c
/* Provided by the generated table; never defined here. */
extern const capability_t auton_caps[];
extern const int auton_caps_count;
```

A tree that declares its own `static const capability_t caps[]` cannot link the generated table
(duplicate definition), and `build_service.py` says so rather than failing — but then its
answers are whatever someone last typed into C, which is what this replaces.

### The four statuses, and the exact answer for each

| Status | The answer, verbatim in shape |
|---|---|
| `CAP_IN_IMAGE` | run it. The action pointer is set **only** when this image defines the symbol |
| `CAP_DEDICATED` | `I can't do that in this image. A dedicated AUTON image does: <build command>.` |
| `CAP_ROADMAP` | `Not built. <what blocks it>` — never "coming soon" |
| `CAP_HOST_ONLY` | `The AUTON host control plane does that from chat; this kernel does not.` |

Three rules, each of which has already been broken somewhere:

1. **An action pointer is never set for a symbol the image lacks.** The absence stub
   (`gen_absent.py`) prints `[ABSENT] …` and returns, which to a user is indistinguishable from
   the service running and doing nothing. A dedicated-image row has `action = 0`.
2. **The dedicated answer names the build command**, because "a different image does it" without
   saying which is not an answer.
3. **A roadmap answer states the blocker**, which the catalogue requires to be a file that git
   tracks. "Coming soon" is a schedule, and the catalogue holds facts.

### Acceptance

```
auton> what can you do
[ROLES] web server: in this image
[ROLES] email server: a dedicated AUTON image does this: auton build smtp
[ROLES] Doom: not built: blocked on a licence decision
auton> be a database
[ROLES] I can't do that in this image. A dedicated AUTON image does: auton build kvstore.
```

## Knowledge Base

```c
/* Device database entry: maps PCI IDs to human-readable names */
typedef struct kb_device_entry {
    uint16_t vendor_id;
    uint16_t device_id;
    char     vendor_name[32];
    char     device_name[64];
    char     driver_name[32];       /* recommended driver */
    uint8_t  device_type;           /* dev_type_t */
} kb_device_entry_t;

/* Driver catalog entry: describes an available driver */
typedef struct kb_driver_entry {
    char     name[32];              /* driver name */
    char     description[128];      /* human-readable description */
    uint8_t  device_types;          /* bitmask of dev_type_t supported */
    uint16_t supported_vendors[16]; /* list of supported vendor IDs */
    uint16_t supported_devices[32]; /* list of supported device IDs */
    int      is_core;               /* 1 if always-loaded core driver */
} kb_driver_entry_t;

/* Package registry entry */
typedef struct kb_package_entry {
    char     name[64];              /* package name */
    char     version[16];           /* version string */
    char     description[256];      /* package description */
    char     category[32];          /* category (e.g., "web", "database") */
    char     deps[8][64];           /* dependency package names */
    uint32_t dep_count;
    uint64_t size_bytes;            /* download size */
} kb_package_entry_t;

/* Knowledge base state */
typedef struct knowledge_base {
    kb_device_entry_t   *devices;
    uint32_t             device_count;
    kb_driver_entry_t   *drivers;
    uint32_t             driver_count;
    kb_package_entry_t  *packages;
    uint32_t             package_count;
    int                  loaded;
} knowledge_base_t;
```

### Conversation Context

```c
/* Context entry: one step in a multi-step operation */
#define CTX_MAX_STEPS       32
#define CTX_MAX_DATA        512

typedef struct ctx_step {
    slm_intent_t        intent;
    slm_sub_command_t   sub_cmd;
    int32_t             status;         /* result status of this step */
    char                summary[256];   /* human-readable summary */
    uint64_t            timestamp;      /* tick when this step occurred */
} ctx_step_t;

/* Conversation context: tracks multi-step operations */
typedef struct slm_context {
    uint64_t    session_id;             /* unique session identifier */
    uint64_t    requester_pid;          /* PID that initiated the conversation */
    ctx_step_t  steps[CTX_MAX_STEPS];   /* history of steps taken */
    uint32_t    step_count;             /* number of steps completed */
    char        goal[256];              /* high-level goal string */
    int         active;                 /* 1 if conversation is in progress */
    int         awaiting_input;         /* 1 if waiting for user/subsystem input */
} slm_context_t;

/* Context manager */
#define CTX_MAX_SESSIONS    16

typedef struct ctx_manager {
    slm_context_t sessions[CTX_MAX_SESSIONS];
    uint32_t      active_count;
    uint64_t      next_session_id;
} ctx_manager_t;
```

### SLM Runtime State

```c
/* Top-level SLM runtime state */
typedef struct slm_runtime {
    slm_backend_type_t  active_backend;
    slm_backend_ops_t  *backend;            /* current backend ops */
    slm_backend_ops_t   rule_backend;       /* rule engine backend */
    slm_backend_ops_t   neural_backend;     /* neural backend */
    knowledge_base_t    kb;                 /* knowledge base */
    ctx_manager_t       ctx;                /* conversation context manager */
    uint64_t            slm_pid;            /* PID of the SLM process */
    int                 initialized;
    uint64_t            total_requests;     /* statistics */
    uint64_t            total_errors;
} slm_runtime_t;
```

## Interface (`kernel/include/slm.h`)

### Runtime Lifecycle

```c
/* Initialize the SLM runtime. Selects backend based on available memory.
 * Loads knowledge base. Creates the SLM kernel process.
 * 'hw_summary' provides hardware info for initial configuration.
 * Must be called after mm, sched, ipc are ready. */
int slm_init(const hw_summary_t *hw_summary);

/* Shutdown the SLM runtime. Saves context if possible, frees resources. */
void slm_shutdown(void);

/* Get the current backend type. */
slm_backend_type_t slm_get_backend(void);

/* Force switch to a specific backend (e.g., if neural model fails to load). */
int slm_switch_backend(slm_backend_type_t type);
```

### Intent Processing

```c
/* Process a structured intent. This is the main SLM entry point.
 * Called by subsystems via IPC or directly for kernel-internal requests.
 * Dispatches to the active backend. Returns 0 on success. */
int slm_process_intent(slm_intent_t intent, slm_sub_command_t sub_cmd,
                       const char *args, uint32_t args_len,
                       slm_intent_result_t *result);

/* Process a free-form text query (e.g., from user console input).
 * Classifies intent, extracts entities, dispatches to intent handler.
 * Returns 0 on success. */
int slm_process_text(const char *text, uint32_t text_len,
                     slm_intent_result_t *result);

/* Classify free-form text into an intent (used internally). */
slm_intent_t slm_classify_intent(const char *text, uint32_t text_len);
```

### Knowledge Base

```c
/* Load the knowledge base from embedded data or initramfs.
 * Returns 0 on success, -1 if data not found. */
int slm_kb_load(void);

/* Look up a device by PCI vendor/device ID. Returns entry or NULL. */
const kb_device_entry_t *slm_kb_lookup_device(uint16_t vendor, uint16_t device);

/* Look up a driver by name. Returns entry or NULL. */
const kb_driver_entry_t *slm_kb_lookup_driver(const char *name);

/* Search packages by keyword (searches name, description, category).
 * Fills 'results' array, returns count of matches. */
uint32_t slm_kb_search_packages(const char *keyword,
                                kb_package_entry_t **results,
                                uint32_t max_results);

/* Get all packages in a category. */
uint32_t slm_kb_get_by_category(const char *category,
                                kb_package_entry_t **results,
                                uint32_t max_results);
```

### Context Management

```c
/* Start a new conversation context for a multi-step operation.
 * Returns session_id, or 0 on failure. */
uint64_t slm_ctx_start(uint64_t requester_pid, const char *goal);

/* Add a step to an active conversation context. */
int slm_ctx_add_step(uint64_t session_id, slm_intent_t intent,
                     slm_sub_command_t sub_cmd, int32_t status,
                     const char *summary);

/* Get the current context for a session. Returns NULL if not found. */
const slm_context_t *slm_ctx_get(uint64_t session_id);

/* End a conversation context (mark as inactive). */
void slm_ctx_end(uint64_t session_id);

/* Get the most recent active context for a requester PID. */
const slm_context_t *slm_ctx_get_active(uint64_t requester_pid);
```

### Rule Engine Specific

```c
/* Initialize the rule engine with built-in rules. */
int slm_rule_init(void);

/* Add a keyword mapping (used for extending the rule set). */
int slm_rule_add_keyword(const char *keyword, slm_intent_t intent, int weight);

/* Add a pattern rule. */
int slm_rule_add_pattern(const char *pattern, slm_intent_t intent,
                         slm_sub_command_t sub_cmd, const char *action_template);

/* Tokenize input text into lowercase tokens. */
void slm_rule_tokenize(const char *text, token_list_t *tokens);

/* Extract entities from tokenized text (numbers, sizes, names). */
void slm_rule_extract_entities(const token_list_t *tokens,
                               slm_intent_t intent,
                               char *entity_buf, uint32_t buf_size);
```

### Neural Backend Specific

```c
/* Load a neural model from memory (previously loaded into SLM pool).
 * Parses GGUF/ONNX header, maps tensors to SLM pool regions.
 * Returns 0 on success. */
int slm_neural_load_model(const void *model_data, uint64_t model_size,
                          model_format_t format);

/* Run inference: given input tokens, generate output tokens.
 * Writes output to 'output_buf'. Returns number of tokens generated. */
uint32_t slm_neural_infer(const uint32_t *input_tokens, uint32_t input_len,
                          uint32_t *output_tokens, uint32_t max_output,
                          const inference_config_t *config);

/* Tokenize text into model token IDs. Returns token count. */
uint32_t slm_neural_tokenize(const char *text, uint32_t text_len,
                             uint32_t *token_ids, uint32_t max_tokens);

/* Decode token IDs back to text. Returns string length. */
uint32_t slm_neural_detokenize(const uint32_t *token_ids, uint32_t token_count,
                               char *text_buf, uint32_t buf_size);

/* Reset KV cache (start fresh context). */
void slm_neural_reset_cache(void);

/* Get model info string. */
void slm_neural_model_info(char *buf, uint32_t buf_size);
```

## Behavior

### Backend Selection at Boot

```
slm_init(hw_summary):
  1. Load knowledge base (slm_kb_load)
  2. Initialize context manager
  3. For each candidate model module, compute what THAT MODEL costs:
       need_mb = module_size_mb + NEURAL_HEADROOM_MB
     and select NEURAL only if total_ram_bytes >= need_mb.

     A flat threshold is WRONG and MUST NOT be generated. A fixed 128 MB gate
     refuses a 6 MB quantized model on a 96 MB machine for no reason the
     hardware justifies — which makes quantization pointless, since a lower
     RAM floor is the entire benefit of a smaller model. Headroom covers the
     KV cache, activation buffers, and the kernel itself.

     On refusal, report the shortfall: "needs N MB, have M MB".
  4. If NEURAL selected:
     a. Check if model data exists (boot module or initramfs)
     b. If model found: slm_neural_load_model()
     c. If load fails OR no model: fall back to RULE_ENGINE
  5. Initialize selected backend (backend->init())
  6. Create SLM kernel process (sched_create_slm_process)
  7. Register SLM command channel (ipc_slm_channel_init)
  8. Return 0 on success
```

### SLM Main Loop

```
slm_main_loop() [SLM process entry point]:
  Loop:
    1. ipc_slm_receive_command(&cmd, &sender_pid)  [blocks until command]
    2. Check if cmd belongs to active context (slm_ctx_get_active)
    3. If new request with no context:
       - Classify intent from cmd
       - For multi-step intents: start new context
    4. Dispatch to intent handler:
       - HARDWARE_IDENTIFY -> handle_hw_identify()
       - DRIVER_SELECT     -> handle_driver_select()
       - INSTALL_CONFIGURE -> handle_install_configure()
       - APP_INSTALL       -> handle_app_install()
       - SYSTEM_MANAGE     -> handle_system_manage()
       - TROUBLESHOOT      -> handle_troubleshoot()
    5. Build slm_intent_result_t
    6. If multi-step: add step to context
    7. ipc_slm_send_result(sender_pid, ...)
    8. If context->requires_followup:
       - SLM initiates next step automatically
       - E.g., after DRIVER_SELECT succeeds, auto-trigger INSTALL_CONFIGURE
```

### Rule Engine Intent Processing

```
rule_process_intent(intent, sub_cmd, args, result):
  For HARDWARE_IDENTIFY:
    1. Parse args for PCI vendor:device string
    2. Look up in knowledge base: slm_kb_lookup_device(vendor, device)
    3. If found: result->response = device name, result->action_data = driver recommendation
    4. If not found: result->response = "Unknown device [vendor:device]"

  For DRIVER_SELECT:
    1. Parse args for device type and identity
    2. Walk driver decision tree:
       - Check class code -> storage? network? display?
       - Check vendor ID -> specific vendor driver?
       - Check subclass -> AHCI? NVMe? USB?
    3. Look up in driver catalog: slm_kb_lookup_driver(result)
    4. result->action_data = driver name

  For INSTALL_CONFIGURE:
    1. Parse sub_command (PARTITION_DISK, FORMAT_FS, etc.)
    2. Apply rule templates for the operation
    3. result->action_data = specific kernel commands to execute

  For APP_INSTALL:
    1. Parse args for package name or description
    2. Search knowledge base: slm_kb_search_packages(keyword)
    3. If found: resolve dependencies, build install plan
    4. result->action_data = list of packages to install in order

  For SYSTEM_MANAGE:
    1. Parse sub_command (SVC_START, RESOURCE_QUERY, etc.)
    2. Query appropriate subsystem (sys, net, etc.)
    3. Format response

  For TROUBLESHOOT:
    1. Parse sub_command for area (network, storage, memory)
    2. Run diagnostic checks via kernel APIs
    3. Build diagnostic report
```

### Neural Backend Inference Pipeline

```
neural_process_intent(intent, sub_cmd, args, result):
  1. Build prompt string from intent + args:
     "[SYSTEM] You are AUTON kernel SLM. Intent: HARDWARE_IDENTIFY
      Device: PCI 8086:100E class=02:00
      Respond with: device_name, driver_name"
  2. Tokenize prompt: slm_neural_tokenize()
  3. Run inference: slm_neural_infer()
     a. For each layer in the model:
        - Attention: Q*K^T/sqrt(d), softmax, *V
        - Use quantized matmul (INT4 or INT8)
        - FFN: gate * up, SiLU activation, down projection
     b. Apply KV cache for efficient generation
     c. Sample next token (greedy or top-p)
     d. Repeat until max_tokens or end token
  4. Detokenize output: slm_neural_detokenize()
  5. Parse response into structured result
  6. Return result
```

### Quantized Matrix Multiplication (INT4/INT8)

```
For INT8 quantization:
  1. int8_t codes preceded by one f32 scale per tensor. 1D norm vectors stay
     f32: quantizing a per-channel scale vector costs accuracy for almost no
     bytes.
  2. Dequantize INLINE, never on load. A hard requirement, not a preference:
     the model runs in place from the boot module, so expanding int8 to f32 at
     load costs the module PLUS an equal-sized allocation. Measured on x86_64:
     5.9 MB module + 23.5 MB expansion = 29.4 MB resident, WORSE than shipping
     f32 at 23.5 MB. Inline keeps 5.9 MB, and is the only strategy that
     delivers the lower RAM floor quantization exists for.
  3. Apply the tensor scale ONCE to the accumulated integer dot product, not
     per weight: sum(code[i] * x[i]) * scale.
  4. Accumulate in float32.
  5. No SIMD required (pure C loop). Where the HAL exposes a vector unit
     (x86 SSE/AVX, AArch64 NEON, RISC-V V) the inner loop MAY use it; the
     layout is deliberately SIMD-friendly. Correctness MUST NOT depend on it —
     a generated kernel for a target without SIMD is still valid.

For INT4 quantization:
  1. Two weights packed per byte (4 bits each)
  2. Unpack: low = byte & 0x0F, high = (byte >> 4) & 0x0F
  3. Subtract zero-point: val = unpacked - 8 (signed range -8 to +7)
  4. Scale and accumulate same as INT8
```

### Multi-Step Operation Example: "Set Up This Machine as a Web Server"

```
Step 1: SLM receives free-form text, classifies as INSTALL_CONFIGURE
Step 2: Start context: goal="Set up web server"
Step 3: HARDWARE_IDENTIFY -> enumerate all devices
        Context step: "Identified 5 PCI devices"
Step 4: DRIVER_SELECT -> for each device, select and load driver
        Context step: "Loaded drivers: e1000, ahci"
Step 5: INSTALL_CONFIGURE/NETWORK_CONFIG -> configure DHCP
        Context step: "Network configured: 192.168.1.100"
Step 6: INSTALL_CONFIGURE/PARTITION_DISK -> partition primary drive
        Context step: "Partitioned /dev/sda: 512MB boot, rest root"
Step 7: INSTALL_CONFIGURE/FORMAT_FS -> format partitions
        Context step: "Formatted /dev/sda1 ext2, /dev/sda2 ext2"
Step 8: APP_INSTALL -> install web server package
        Context step: "Installed nginx from package registry"
Step 9: SYSTEM_MANAGE/SVC_START -> start nginx service
        Context step: "nginx running on port 80"
Step 10: End context: "Machine configured as web server. nginx on port 80."
```

### Edge Cases

- **Neural model too large for available memory**: fall back to rule engine, log warning
- **Neural model file corrupted**: GGUF magic/checksum fails, fall back to rule engine
- **Unknown device (not in knowledge base)**: SLM reports "Unknown device" with raw PCI ID; if neural backend, may still attempt classification from class/subclass
- **No matching driver in catalog**: SLM returns error with suggestion to use generic driver or skip device
- **Context overflow (>32 steps)**: oldest steps are evicted; summary preserved
- **Multiple concurrent contexts**: up to 16 sessions; oldest inactive session is evicted if full
- **Intent classification failure (rule engine)**: returns SLM_INTENT_TROUBLESHOOT as fallback
- **Inference timeout**: if neural inference exceeds 5 seconds for a single request, abort and fall back to rule engine for that request
- **SLM pool memory exhaustion during inference**: abort inference, return error, suggest reducing context window

## Files

| File | Purpose |
|------|---------|
| `kernel/slm/slm.c`               | SLM runtime core: init, main loop, intent dispatch |
| `kernel/slm/engine/intent.c`     | Intent classification and routing |
| `kernel/slm/engine/context.c`    | Conversation context manager |
| `kernel/slm/rules/rule_engine.c` | Rule-based backend: tokenizer, keyword matching, decision trees |
| `kernel/slm/rules/driver_rules.c`| Driver selection decision tree |
| `kernel/slm/rules/install_rules.c`| Installation/configuration rule templates |
| `kernel/slm/neural/loader.c`     | GGUF/ONNX model loading and tensor mapping |
| `kernel/slm/neural/inference.c`  | Forward pass: attention, FFN, sampling |
| `kernel/slm/neural/quantize.c`   | INT4/INT8 dequantization and quantized matmul |
| `kernel/slm/neural/tokenizer.c`  | BPE tokenizer for neural models |
| `kernel/slm/knowledge/device_db.c` | Built-in PCI device database |
| `kernel/slm/knowledge/driver_catalog.c` | Driver catalog data |
| `kernel/slm/knowledge/package_registry.c` | Package registry data |
| `kernel/include/slm.h`           | SLM interface and data structures |

## Dependencies

- **mm**: SLM memory pool for weights, KV cache, scratch buffers, context storage
- **sched**: SLM process creation (PRIORITY_SLM), scheduling
- **ipc**: SLM command channel for receiving intents and sending results
- **dev**: device descriptors for HARDWARE_IDENTIFY and DRIVER_SELECT
- **boot**: `hw_summary_t` for initial configuration, boot modules for model data
- **fs**: VFS access for reading model files from initramfs (if not boot module)

## Acceptance Criteria

1. SLM initializes with rule engine backend on systems with < 128MB RAM
2. SLM initializes with neural backend on systems with >= 128MB RAM and valid model file
3. Neural backend falls back to rule engine if model load fails
4. `slm_process_intent(HARDWARE_IDENTIFY, ...)` correctly identifies known PCI devices from knowledge base
5. `slm_process_intent(DRIVER_SELECT, ...)` returns correct driver name for known devices
6. Rule engine tokenizer correctly splits "install a web server" into tokens
7. Rule engine intent classifier maps "install a web server" to APP_INSTALL with >= 90% accuracy on test set
8. Knowledge base lookup returns correct entries for common PCI IDs (8086:100E = Intel e1000, etc.)
9. Driver decision tree selects AHCI driver for class=01 subclass=06 devices
10. Multi-step context tracks all steps: start context, add 5 steps, verify all retrievable
11. Context eviction works: fill all 16 sessions, verify oldest is evicted on 17th
12. `slm_process_text()` correctly classifies at least 20 test phrases into correct intents
13. Neural backend (if loaded): model weights occupy expected space in SLM pool
14. Neural backend: inference produces coherent token output for test prompts
15. INT4/INT8 quantized matmul produces results within 1% of FP32 reference
16. Inference timeout: request taking > 5 seconds is aborted and handled gracefully
17. SLM main loop processes commands from IPC channel continuously without memory leaks
18. Package search returns relevant results for keyword queries ("web server" -> nginx)
