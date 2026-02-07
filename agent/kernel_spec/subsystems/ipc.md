# IPC (Inter-Process Communication) Specification

## Overview

The IPC subsystem provides structured message-passing communication between kernel processes. Messages use a typed format with a message type header and variable-length payload, replacing the previous natural-language-only approach. A dedicated high-priority SLM command channel provides a fast path for all communication between the SLM runtime and kernel subsystems.

## Data Structures

### Message Types

```c
/* IPC message type identifiers.
 * Each message carries a type that tells the receiver how to interpret
 * the payload without parsing free-form text. */
typedef enum ipc_msg_type {
    /* General */
    IPC_MSG_RAW         = 0x0000,   /* raw byte payload (untyped) */
    IPC_MSG_TEXT        = 0x0001,   /* UTF-8 text string */
    IPC_MSG_ACK         = 0x0002,   /* acknowledgment (no payload) */
    IPC_MSG_ERROR       = 0x0003,   /* error report */

    /* SLM command types */
    IPC_MSG_SLM_COMMAND = 0x0100,   /* SLM intent request */
    IPC_MSG_SLM_RESULT  = 0x0101,   /* SLM intent result */
    IPC_MSG_SLM_QUERY   = 0x0102,   /* SLM query (expects response) */
    IPC_MSG_SLM_EVENT   = 0x0103,   /* asynchronous event to SLM */

    /* Device framework messages */
    IPC_MSG_DEV_DISCOVERED = 0x0200, /* new device found */
    IPC_MSG_DEV_REMOVED    = 0x0201, /* device removed (hot-unplug) */
    IPC_MSG_DEV_STATUS     = 0x0202, /* device status update */

    /* Driver messages */
    IPC_MSG_DRV_LOAD    = 0x0300,   /* request to load a driver */
    IPC_MSG_DRV_UNLOAD  = 0x0301,   /* request to unload a driver */
    IPC_MSG_DRV_STATUS  = 0x0302,   /* driver status report */

    /* System messages */
    IPC_MSG_SYS_LOG     = 0x0400,   /* log entry */
    IPC_MSG_SYS_STATS   = 0x0401,   /* resource statistics */
    IPC_MSG_SYS_ALERT   = 0x0402,   /* alert/warning */

    /* Network messages */
    IPC_MSG_NET_CONFIG  = 0x0500,   /* network configuration change */
    IPC_MSG_NET_STATUS  = 0x0501,   /* network status */

    /* Package messages */
    IPC_MSG_PKG_REQUEST = 0x0600,   /* package install/remove request */
    IPC_MSG_PKG_STATUS  = 0x0601,   /* package operation status */
} ipc_msg_type_t;
```

### Message Structure

```c
#define IPC_MAX_PAYLOAD     4096    /* maximum payload size in bytes */
#define IPC_HEADER_MAGIC    0x49504321  /* "IPC!" */

/* Message header (fixed size, precedes variable payload) */
typedef struct ipc_msg_header {
    uint32_t        magic;          /* IPC_HEADER_MAGIC for validation */
    ipc_msg_type_t  type;           /* message type (uint32_t) */
    uint64_t        sender_pid;     /* PID of sending process */
    uint64_t        receiver_pid;   /* PID of target process (0 = broadcast) */
    uint64_t        timestamp;      /* scheduler tick when sent */
    uint32_t        payload_len;    /* length of payload in bytes */
    uint32_t        sequence;       /* sequence number (per channel) */
    uint32_t        flags;          /* message flags (see below) */
} ipc_msg_header_t;

/* Message flags */
#define IPC_FLAG_URGENT     (1 << 0)  /* high-priority delivery */
#define IPC_FLAG_REPLY_REQ  (1 << 1)  /* sender expects a reply */
#define IPC_FLAG_BROADCAST  (1 << 2)  /* deliver to all processes */
#define IPC_FLAG_SLM_CHAN   (1 << 3)  /* routed via SLM command channel */

/* Complete IPC message (header + payload) */
typedef struct ipc_message {
    ipc_msg_header_t header;
    uint8_t          payload[IPC_MAX_PAYLOAD];
} ipc_message_t;
```

### Channel and Ring Buffer

```c
#define IPC_RING_SIZE       64      /* messages per ring buffer */
#define IPC_MAX_CHANNELS    256     /* max concurrent channels */

/* Ring buffer for a single IPC channel */
typedef struct ipc_ring {
    ipc_message_t messages[IPC_RING_SIZE];
    uint32_t      head;         /* next write index */
    uint32_t      tail;         /* next read index */
    uint32_t      count;        /* current message count */
    uint32_t      dropped;      /* messages dropped due to full buffer */
    uint32_t      next_seq;     /* next sequence number to assign */
} ipc_ring_t;

/* IPC channel: bidirectional communication between two processes */
typedef struct ipc_channel {
    uint64_t    pid_a;          /* first endpoint PID */
    uint64_t    pid_b;          /* second endpoint PID */
    ipc_ring_t  ring_a_to_b;   /* messages from A to B */
    ipc_ring_t  ring_b_to_a;   /* messages from B to A */
    int         active;         /* 1 if channel is in use */

    /* Wait queues for blocking operations */
    process_t  *send_waiters_a;  /* processes blocked on send A->B */
    process_t  *send_waiters_b;  /* processes blocked on send B->A */
    process_t  *recv_waiters_a;  /* processes blocked on recv by A */
    process_t  *recv_waiters_b;  /* processes blocked on recv by B */
} ipc_channel_t;
```

### SLM Command Channel

```c
/* Dedicated SLM command channel.
 * This is a special high-priority channel that any process can send to.
 * The SLM process is always the receiver. Responses go back through
 * normal IPC channels. */
#define SLM_CHANNEL_RING_SIZE   128     /* larger ring for SLM commands */

typedef struct slm_command_channel {
    /* Inbound command ring (any process -> SLM) */
    ipc_message_t   commands[SLM_CHANNEL_RING_SIZE];
    uint32_t        cmd_head;
    uint32_t        cmd_tail;
    uint32_t        cmd_count;
    uint32_t        cmd_next_seq;

    /* Priority sub-queues within the command ring */
    uint32_t        urgent_count;   /* count of IPC_FLAG_URGENT messages */

    /* SLM process reference */
    uint64_t        slm_pid;        /* PID of the SLM process */
    process_t      *slm_process;    /* direct pointer for fast unblock */

    /* Wait queue for processes waiting for SLM response */
    process_t      *response_waiters;

    /* Statistics */
    uint64_t        total_commands;
    uint64_t        total_responses;
    uint64_t        avg_latency_ticks;
} slm_command_channel_t;
```

### SLM Command Payload Structures

```c
/* Payload for IPC_MSG_SLM_COMMAND: a structured intent request */
typedef struct slm_command_payload {
    uint32_t intent;            /* slm_intent_t enum value */
    uint32_t sub_command;       /* intent-specific sub-command */
    char     args[3840];        /* JSON-like key=value argument string */
    uint32_t args_len;          /* length of args string */
} slm_command_payload_t;

/* Payload for IPC_MSG_SLM_RESULT: structured intent response */
typedef struct slm_result_payload {
    uint32_t intent;            /* which intent this responds to */
    int32_t  status;            /* 0 = success, negative = error code */
    char     data[3840];        /* result data (format depends on intent) */
    uint32_t data_len;          /* length of data */
} slm_result_payload_t;
```

## Interface (`kernel/include/ipc.h`)

### Core IPC Operations

```c
/* Initialize IPC subsystem. Allocates channel table and SLM command channel.
 * Must be called after sched_init(). */
void ipc_init(void);

/* Open a channel between the calling process and target PID.
 * Returns channel ID (>= 0) on success, -1 if max channels reached,
 * -2 if target PID does not exist. If channel already exists, returns
 * the existing channel ID. */
int ipc_open_channel(uint64_t target_pid);

/* Close a channel. Drains pending messages, wakes blocked waiters
 * with error. Both endpoints must close for full cleanup. */
void ipc_close_channel(int channel_id);

/* Send a typed message (blocking). Blocks if ring buffer is full.
 * Returns 0 on success. Unblocks receiver if waiting. */
int ipc_send(uint64_t to_pid, ipc_msg_type_t type,
             const void *payload, uint32_t payload_len, uint32_t flags);

/* Send a typed message (non-blocking). Returns 0 on success,
 * IPC_ERR_FULL if ring is full, other negative on error. */
int ipc_send_nonblock(uint64_t to_pid, ipc_msg_type_t type,
                      const void *payload, uint32_t payload_len,
                      uint32_t flags);

/* Receive next message from a specific sender (blocking).
 * Copies message into caller-provided buffer. Blocks if no message.
 * Returns 0 on success, fills out_msg with the received message. */
int ipc_receive(uint64_t from_pid, ipc_message_t *out_msg);

/* Receive next message from any sender (blocking).
 * Returns 0 on success, fills out_msg. */
int ipc_receive_any(ipc_message_t *out_msg);

/* Receive (non-blocking). Returns 0 on success,
 * IPC_ERR_EMPTY if no message available. */
int ipc_receive_nonblock(uint64_t from_pid, ipc_message_t *out_msg);

/* Broadcast a message to all active processes.
 * Skips the sender. Sets IPC_FLAG_BROADCAST. */
int ipc_broadcast(ipc_msg_type_t type, const void *payload,
                  uint32_t payload_len);
```

### SLM Command Channel Operations

```c
/* Initialize the SLM command channel. Called once when SLM process starts.
 * Registers 'slm_pid' as the receiver of all SLM commands. */
void ipc_slm_channel_init(uint64_t slm_pid);

/* Send a command to the SLM (any process may call this).
 * Higher priority than normal IPC: message goes to SLM command ring.
 * If SLM process is blocked, it is immediately unblocked.
 * Returns 0 on success. */
int ipc_slm_send_command(uint32_t intent, uint32_t sub_command,
                         const char *args, uint32_t args_len);

/* SLM process receives next command (blocking).
 * Urgent commands (IPC_FLAG_URGENT) are dequeued first. */
int ipc_slm_receive_command(slm_command_payload_t *out_cmd,
                            uint64_t *out_sender_pid);

/* SLM process sends a result back to the command sender. */
int ipc_slm_send_result(uint64_t to_pid, uint32_t intent,
                        int32_t status, const char *data,
                        uint32_t data_len);

/* Synchronous SLM request: send command and block until result arrives.
 * Convenience function for subsystems that need SLM decisions.
 * Returns 0 on success, fills out_result. */
int ipc_slm_request(uint32_t intent, uint32_t sub_command,
                    const char *args, uint32_t args_len,
                    slm_result_payload_t *out_result);

/* Get SLM command channel statistics. */
void ipc_slm_stats(uint64_t *total_cmds, uint64_t *total_resps,
                   uint64_t *avg_latency);
```

### Error Codes

```c
#define IPC_OK              0
#define IPC_ERR_FULL       -1   /* ring buffer full */
#define IPC_ERR_EMPTY      -2   /* no message available */
#define IPC_ERR_BAD_PID    -3   /* target PID does not exist */
#define IPC_ERR_TOO_LONG   -4   /* payload exceeds IPC_MAX_PAYLOAD */
#define IPC_ERR_NO_CHANNEL -5   /* no channel exists to target */
#define IPC_ERR_CLOSED     -6   /* channel was closed while waiting */
#define IPC_ERR_MAX_CHAN   -7   /* maximum channels reached */
#define IPC_ERR_INVALID    -8   /* invalid message (bad magic, etc.) */
```

## Behavior

### Channel Lifecycle

```
CLOSED -> OPEN (ipc_open_channel) -> ACTIVE <-> DRAINING -> CLOSED (ipc_close_channel)
```

1. **OPEN**: Either endpoint calls `ipc_open_channel()`. A channel structure is allocated from the channel table. Both ring buffers are initialized (head=tail=count=0).
2. **ACTIVE**: Messages flow bidirectionally. Senders enqueue to the appropriate ring, receivers dequeue.
3. **DRAINING**: When one endpoint calls `ipc_close_channel()`, pending messages are still deliverable to the other endpoint. New sends fail with `IPC_ERR_CLOSED`.
4. **CLOSED**: Both endpoints have closed, or the draining side has read all pending messages. Channel structure is returned to the free pool.

### Send Algorithm

```
ipc_send(to_pid, type, payload, payload_len, flags):
  1. Validate payload_len <= IPC_MAX_PAYLOAD
  2. Find or open channel to to_pid
  3. Select correct ring (sender's direction)
  4. If ring->count >= IPC_RING_SIZE:
     a. Blocking: add current process to send_waiters, call sched_block()
     b. Non-blocking: return IPC_ERR_FULL
  5. Build ipc_message_t:
     - Fill header: magic, type, sender_pid, receiver_pid, timestamp, payload_len, sequence++, flags
     - Copy payload into message
  6. ring->messages[ring->head] = message
  7. ring->head = (ring->head + 1) % IPC_RING_SIZE
  8. ring->count++
  9. If receiver is blocked in recv_waiters: sched_unblock(receiver)
  10. Return IPC_OK
```

### Receive Algorithm

```
ipc_receive(from_pid, out_msg):
  1. Find channel with from_pid
  2. Select correct ring (receiver's direction)
  3. If ring->count == 0:
     a. Blocking: add current process to recv_waiters, call sched_block()
     b. Non-blocking: return IPC_ERR_EMPTY
  4. Copy ring->messages[ring->tail] into out_msg
  5. ring->tail = (ring->tail + 1) % IPC_RING_SIZE
  6. ring->count--
  7. If sender is blocked in send_waiters: sched_unblock(sender)
  8. Return IPC_OK
```

### SLM Command Channel Behavior

The SLM command channel is a **many-to-one** channel: any process can send commands, but only the SLM process receives them.

```
ipc_slm_send_command(intent, sub_command, args, args_len):
  1. Build slm_command_payload_t in message payload
  2. Enqueue to slm_command_channel.commands[] ring
  3. If message has IPC_FLAG_URGENT: increment urgent_count
  4. If SLM process is blocked: sched_unblock(slm_process)
     - SLM is at PRIORITY_SLM, so it preempts SYSTEM/USER/BACKGROUND immediately
  5. Return IPC_OK

ipc_slm_receive_command(out_cmd, out_sender_pid):
  1. If urgent_count > 0: scan ring for first URGENT message, dequeue it
  2. Else if cmd_count > 0: dequeue from cmd_tail (FIFO)
  3. Else: block SLM process until a command arrives
  4. Decrement cmd_count (and urgent_count if applicable)
  5. Copy payload to out_cmd, set out_sender_pid
  6. Return IPC_OK
```

### Synchronous SLM Request

```
ipc_slm_request(intent, sub_command, args, args_len, out_result):
  1. ipc_slm_send_command(intent, sub_command, args, args_len)
  2. Add current process to response_waiters
  3. sched_block(current)
  4. [SLM processes command, calls ipc_slm_send_result]
  5. On unblock: copy result from response into out_result
  6. Return result status
```

### Message Validation

Every received message is validated before delivery:
1. `header.magic == IPC_HEADER_MAGIC` -- reject corrupted messages
2. `header.payload_len <= IPC_MAX_PAYLOAD` -- reject oversized
3. `header.sender_pid` must be a valid, existing process
4. If channel is closed: return `IPC_ERR_CLOSED`

### Edge Cases

- **Sender terminated while receiver is blocked**: unblock receiver with `IPC_ERR_CLOSED`
- **Receiver terminated while sender has pending messages**: messages are dropped, sender is unblocked if blocked
- **SLM process terminated**: all `ipc_slm_request()` waiters are unblocked with error status
- **Ring buffer full + non-blocking send**: returns `IPC_ERR_FULL`, increments `ring->dropped`
- **Broadcast to many processes**: iterates all active processes, sends individually; tolerates individual failures
- **Message to self**: allowed; uses a self-loopback ring

## Files

| File | Purpose |
|------|---------|
| `kernel/ipc/ipc.c`          | Core IPC: channels, send, receive |
| `kernel/ipc/slm_channel.c`  | SLM command channel implementation |
| `kernel/include/ipc.h`      | IPC interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for channel allocation
- **sched**: `sched_block()`/`sched_unblock()` for blocking operations, `sched_current()` for sender PID
- **sched**: timer ticks for message timestamps

## Acceptance Criteria

1. Two processes exchange typed messages: sender sends `IPC_MSG_TEXT`, receiver gets same type and payload
2. Ring buffer wraps correctly: send 64 messages, receive 64, send 64 more -- all arrive intact
3. Blocking send blocks when ring is full; unblocks when receiver reads
4. Blocking receive blocks when ring is empty; unblocks when sender writes
5. Non-blocking send returns `IPC_ERR_FULL` immediately when ring is full
6. Non-blocking receive returns `IPC_ERR_EMPTY` immediately when ring is empty
7. Message payload integrity: 4KB payload sent == 4KB payload received (byte-for-byte)
8. `ipc_broadcast()` delivers to all active processes except sender
9. SLM command channel: command sent by any process is received by SLM process
10. SLM urgent commands are dequeued before normal commands
11. `ipc_slm_request()` blocks caller until SLM sends result, then returns correct result
12. SLM command channel unblocks SLM process immediately on command arrival
13. Channel close while blocked: blocked process wakes with `IPC_ERR_CLOSED`
14. Invalid PID send returns `IPC_ERR_BAD_PID`
15. Message magic validation rejects corrupted messages
16. SLM channel stats track total commands/responses/latency accurately
