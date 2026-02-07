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
/* Model format */
typedef enum model_format {
    MODEL_FORMAT_GGUF,      /* GGUF (llama.cpp format) */
    MODEL_FORMAT_ONNX,      /* ONNX (Open Neural Network Exchange) */
} model_format_t;

/* Quantization level */
typedef enum quant_type {
    QUANT_NONE  = 0,        /* FP32 (not recommended for kernel) */
    QUANT_FP16  = 1,        /* FP16 */
    QUANT_INT8  = 2,        /* 8-bit integer quantization */
    QUANT_INT4  = 3,        /* 4-bit integer quantization (most compact) */
} quant_type_t;

/* GGUF file header (simplified) */
typedef struct gguf_header {
    uint32_t magic;         /* 0x46475547 "GGUF" */
    uint32_t version;
    uint64_t tensor_count;
    uint64_t metadata_kv_count;
} __attribute__((packed)) gguf_header_t;

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

### Knowledge Base

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
  3. Check available memory from hw_summary->total_ram_bytes:
     - < 128MB:  select RULE_ENGINE backend
     - >= 128MB: attempt NEURAL backend
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
  1. Weights stored as int8_t + scale factor (per-group)
  2. Dequantize on the fly: float_val = int8_val * scale
  3. Accumulate in float32: result += dequant(A[i]) * dequant(B[i])
  4. No SIMD required (pure C loop), but SIMD-friendly layout for future

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
