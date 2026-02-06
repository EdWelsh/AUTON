# Natural Language Syscall Interface Specification

## Overview

The core innovation of AUTON: instead of numeric syscalls, agents issue natural language requests that the kernel parses and executes. This is the bridge between human-readable intent and kernel operations.

## Architecture

```
Agent Process
    |
    | "allocate 4KB of memory"      (natural language string)
    |
    v
NL Syscall Handler (INT 0x81)
    |
    v
Intent Classifier
    |  → MEMORY_ALLOC
    v
Entity Extractor
    |  → size=4096
    v
Syscall Dispatcher
    |  → pmm_alloc_page()
    v
Result Formatter
    |  → "Allocated page at 0x200000"
    v
Return to Agent
```

## Intent Categories

| Intent | Pattern Examples | Kernel Action |
|--------|-----------------|---------------|
| MEMORY_ALLOC | "allocate memory", "give me N bytes" | `pmm_alloc_page()` |
| MEMORY_FREE | "free memory at X", "release page" | `pmm_free_page()` |
| IPC_SEND | "send message to agent N: ..." | `ipc_send()` |
| IPC_RECEIVE | "check messages", "read from agent N" | `ipc_receive()` |
| PROCESS_LIST | "list processes", "who is running" | `sched_list_processes()` |
| PROCESS_SPAWN | "start new agent", "create process" | `sched_create_process()` |
| PROCESS_KILL | "stop agent N", "terminate process" | `sched_terminate()` |
| STATUS | "system status", "how much memory" | status report |
| UNKNOWN | (anything else) | error response |

## Interface

```c
// NL syscall entry point (called from INT 0x81 handler)
void nl_syscall_handler(const char *request, char *response, uint32_t response_max);

// Intent classification
typedef enum {
    INTENT_MEMORY_ALLOC,
    INTENT_MEMORY_FREE,
    INTENT_IPC_SEND,
    INTENT_IPC_RECEIVE,
    INTENT_PROCESS_LIST,
    INTENT_PROCESS_SPAWN,
    INTENT_PROCESS_KILL,
    INTENT_STATUS,
    INTENT_UNKNOWN,
} nl_intent_t;

nl_intent_t nl_classify_intent(const char *request);

// Entity extraction
typedef struct {
    uint64_t number;         // Extracted number (size, PID, etc.)
    char target[64];         // Target name/identifier
    char message[IPC_MAX_MSG]; // Extracted message body
    int has_number;
    int has_target;
    int has_message;
} nl_entities_t;

int nl_extract_entities(const char *request, nl_intent_t intent, nl_entities_t *entities);
```

## Implementation Approach

**Phase 1**: Keyword matching (simple, no ML)
- Pattern match on keywords: "allocate", "free", "send", "list", etc.
- Extract numbers with regex-like scanning
- Extract quoted strings as message bodies

**Phase 2**: (Future) Small embedded model
- Integrate TinyLLM for better understanding
- Handle ambiguous requests
- Learn from usage patterns

## Acceptance Criteria

- "allocate 4KB of memory" → successfully allocates a page
- "free memory at 0x200000" → successfully frees the page
- "send message to agent 2: hello world" → delivers message via IPC
- "list running processes" → returns process list
- Unknown requests return helpful error message
- Response is always a human-readable UTF-8 string
