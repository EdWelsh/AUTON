# Scheduler Specification

## Overview

Preemptive round-robin scheduler with priority classes, designed to be LLM-aware for agent workload management.

## Priority Classes

```c
enum priority_class {
    PRIORITY_KERNEL = 0,        // Kernel threads (highest)
    PRIORITY_SYSTEM_AGENT = 1,  // System-level agents (LLM runtime)
    PRIORITY_USER_AGENT = 2,    // User agents
    PRIORITY_BACKGROUND = 3,    // Background tasks (lowest)
};
```

## Process Control Block

```c
typedef struct process {
    uint64_t pid;
    char name[64];
    enum priority_class priority;
    enum process_state state;    // READY, RUNNING, BLOCKED, TERMINATED
    uint64_t *stack_top;         // Saved stack pointer
    uint64_t cr3;                // Page table root (address space)
    struct process *next;        // Linked list for run queue
    // Context: saved registers
    uint64_t rsp, rbp, rip;
    uint64_t rax, rbx, rcx, rdx, rsi, rdi;
    uint64_t r8, r9, r10, r11, r12, r13, r14, r15;
    uint64_t rflags;
} process_t;
```

## Interface (`kernel/include/sched.h`)

```c
void sched_init(void);
process_t *sched_create_process(const char *name, void (*entry)(void), enum priority_class prio);
void sched_yield(void);
void sched_schedule(void);          // Called from timer interrupt
void sched_block(process_t *proc);
void sched_unblock(process_t *proc);
void sched_terminate(process_t *proc);
process_t *sched_current(void);
void sched_list_processes(void);    // Print all processes to serial
```

## Context Switch

Assembly routine that saves/restores all general-purpose registers and switches the stack pointer. Called from `sched_schedule()`.

```nasm
; context_switch(old_rsp_ptr, new_rsp)
context_switch:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    mov [rdi], rsp      ; save old stack pointer
    mov rsp, rsi         ; load new stack pointer
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
```

## Scheduling Algorithm

1. Timer interrupt fires (every 10ms)
2. Save current process context
3. Select next process: iterate run queue by priority class
4. Within same priority: round-robin
5. Restore selected process context
6. Return from interrupt

## Acceptance Criteria

- Process creation and destruction works
- Timer-driven preemptive scheduling switches between 2+ processes
- Priority classes are respected (higher priority runs first)
- Context switch preserves all register state
- No stack corruption after multiple switches
- `sched_list_processes()` correctly reports all running processes
