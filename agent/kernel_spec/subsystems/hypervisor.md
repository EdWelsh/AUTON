# Hypervisor Specification

## Overview

The hypervisor isolates agents into virtual machines with separate address spaces and capability-based security.

## Agent VM Model

Each agent runs in its own:
- **Address space**: Separate PML4 page table
- **Stack**: Dedicated kernel and user stacks
- **Capability set**: Tokens that grant specific permissions
- **Message mailbox**: IPC channel endpoints

## Capabilities

```c
typedef enum {
    CAP_MEMORY    = (1 << 0),  // Allocate/free memory
    CAP_IPC       = (1 << 1),  // Send/receive messages
    CAP_SPAWN     = (1 << 2),  // Create new agents
    CAP_NL_SYSCALL = (1 << 3), // Use NL syscall interface
    CAP_DEVICE    = (1 << 4),  // Access hardware devices
    CAP_ADMIN     = (1 << 5),  // Administrative operations
} capability_t;

#define CAP_DEFAULT (CAP_MEMORY | CAP_IPC | CAP_NL_SYSCALL)
#define CAP_ALL     (0x3F)
```

## Agent Lifecycle

```
CREATE → INIT → READY → RUNNING ↔ SUSPENDED → TERMINATED
                  ↑                     |
                  +---------------------+
```

## Interface (`kernel/include/hypervisor.h`)

```c
typedef struct agent_vm {
    uint64_t agent_id;
    char name[64];
    uint64_t cr3;              // Page table root
    uint32_t capabilities;     // Capability bitmask
    enum agent_state state;
    process_t *process;        // Scheduler process
    ipc_channel_t *mailbox;    // IPC endpoint
} agent_vm_t;

void hypervisor_init(void);
agent_vm_t *agent_create(const char *name, uint32_t capabilities);
int agent_start(agent_vm_t *agent, void (*entry)(void));
int agent_suspend(agent_vm_t *agent);
int agent_resume(agent_vm_t *agent);
int agent_destroy(agent_vm_t *agent);
int agent_check_capability(agent_vm_t *agent, capability_t cap);
agent_vm_t *agent_get_current(void);
void agent_list(void);
```

## Security Model

- Every NL syscall checks capabilities before execution
- Agents cannot access each other's memory (separate page tables)
- Only agents with CAP_ADMIN can manage other agents
- The kernel (system agent) has CAP_ALL

## Acceptance Criteria

- Agents are created with isolated address spaces
- Capability checks prevent unauthorized operations
- Agent lifecycle transitions work correctly
- Memory isolation: agent A cannot read agent B's pages
- NL syscall respects capabilities
