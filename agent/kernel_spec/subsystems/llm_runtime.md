# LLM Runtime Specification

## Overview

Lightweight natural language processing engine embedded in the kernel. Phase 1 uses keyword matching; Phase 2 targets a small neural model.

## Phase 1: Keyword-Based NLP

### Tokenizer
```c
// Split input string into lowercase tokens
typedef struct {
    char tokens[64][32];  // Max 64 tokens, 32 chars each
    int count;
} token_list_t;

void tokenize(const char *input, token_list_t *tokens);
```

### Intent Classifier (Keyword Matching)
```c
// Keyword → intent mapping
static const struct {
    const char *keyword;
    nl_intent_t intent;
} keyword_map[] = {
    {"allocate", INTENT_MEMORY_ALLOC},
    {"malloc",   INTENT_MEMORY_ALLOC},
    {"alloc",    INTENT_MEMORY_ALLOC},
    {"free",     INTENT_MEMORY_FREE},
    {"release",  INTENT_MEMORY_FREE},
    {"send",     INTENT_IPC_SEND},
    {"message",  INTENT_IPC_SEND},
    {"receive",  INTENT_IPC_RECEIVE},
    {"check",    INTENT_IPC_RECEIVE},
    {"list",     INTENT_PROCESS_LIST},
    {"processes",INTENT_PROCESS_LIST},
    {"spawn",    INTENT_PROCESS_SPAWN},
    {"create",   INTENT_PROCESS_SPAWN},
    {"kill",     INTENT_PROCESS_KILL},
    {"stop",     INTENT_PROCESS_KILL},
    {"status",   INTENT_STATUS},
    {"memory",   INTENT_STATUS},
};
```

### Entity Extractor
- Extract numbers: scan for digit sequences, parse with strtoul
- Extract sizes: recognize "KB", "MB", "GB" suffixes, convert to bytes
- Extract PIDs: "agent N", "process N"
- Extract messages: text after ":" in send commands

### Response Formatter
```c
void format_response(char *buf, size_t bufsize, nl_intent_t intent,
                     int success, const char *details);
// Example: "OK: Allocated 4096 bytes at 0x200000"
// Example: "ERROR: Not enough memory for 1MB allocation"
```

## Phase 2: Neural NLP (Future)

- Quantized 4-bit model (~1MB weights)
- Runs in kernel address space
- Fixed-size matrix operations only (no dynamic allocation)
- Attention-free architecture for deterministic latency

## Acceptance Criteria

- Tokenizer correctly splits "allocate 4KB of memory" → ["allocate", "4kb", "of", "memory"]
- Intent classifier maps to correct intent ≥90% of test cases
- Entity extractor finds numbers, sizes, PIDs, and messages
- Response formatter produces readable UTF-8 strings
- Total processing time < 1ms for keyword-based phase
