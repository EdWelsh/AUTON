# IPC (Inter-Process Communication) Specification

## Overview

Message-passing IPC for agent communication. Messages are natural language strings (UTF-8), not binary data. This aligns with the kernel's natural language-first philosophy.

## Design

- Each agent pair has a ring buffer for messages
- Messages are variable-length UTF-8 strings (max 4KB per message)
- Blocking and non-blocking operations
- No shared memory (security: agent isolation)

## Message Structure

```c
typedef struct ipc_message {
    uint64_t sender_pid;
    uint64_t receiver_pid;
    uint64_t timestamp;
    uint32_t length;          // Message body length in bytes
    char body[IPC_MAX_MSG];   // UTF-8 message content (max 4096 bytes)
} ipc_message_t;
```

## Ring Buffer

```c
#define IPC_RING_SIZE 64  // Messages per channel

typedef struct ipc_channel {
    ipc_message_t messages[IPC_RING_SIZE];
    uint32_t head;        // Next write position
    uint32_t tail;        // Next read position
    uint32_t count;       // Current message count
    // Waiting queues for blocking operations
    process_t *send_waiters;
    process_t *recv_waiters;
} ipc_channel_t;
```

## Interface (`kernel/include/ipc.h`)

```c
void ipc_init(void);
int ipc_send(uint64_t to_pid, const char *message, uint32_t length);
int ipc_receive(uint64_t from_pid, char *buffer, uint32_t *length);
int ipc_send_nonblock(uint64_t to_pid, const char *message, uint32_t length);
int ipc_receive_nonblock(uint64_t from_pid, char *buffer, uint32_t *length);
int ipc_broadcast(const char *message, uint32_t length);
```

## Return Values

- `0`: Success
- `-1`: Channel full (non-blocking send)
- `-2`: No message available (non-blocking receive)
- `-3`: Invalid PID
- `-4`: Message too long

## Acceptance Criteria

- Send/receive round-trip works between two processes
- Ring buffer wraps correctly when full (blocks or returns error)
- Non-blocking operations return immediately
- Messages preserve UTF-8 content correctly
- Broadcast delivers to all active agents
- No data corruption under concurrent send/receive
