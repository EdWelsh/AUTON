# Scheduler Specification

## Overview

The scheduler provides preemptive round-robin scheduling with five priority classes. SLM inference tasks receive elevated priority (second only to kernel threads) to ensure the system's AI brain remains responsive during hardware discovery, driver loading, and runtime management. Timer-driven preemption ensures no single task monopolizes the CPU.

## Data Structures

### Priority Classes

```c
/* Priority classes in descending order of priority.
 * Lower numeric value = higher priority.
 * The scheduler always picks the highest-priority runnable task. */
typedef enum priority_class {
    PRIORITY_KERNEL     = 0,    /* Kernel threads: interrupt handlers, MM */
    PRIORITY_SLM        = 1,    /* SLM inference and intent processing */
    PRIORITY_SYSTEM     = 2,    /* System services: init, logging, monitoring */
    PRIORITY_USER       = 3,    /* User-facing applications */
    PRIORITY_BACKGROUND = 4,    /* Low-priority: garbage collection, idle tasks */
    PRIORITY_CLASS_COUNT = 5
} priority_class_t;

/* Time slice per priority class (in timer ticks, 1 tick = 10ms) */
#define TIMESLICE_KERNEL        1   /* 10ms - short, kernel work is brief */
#define TIMESLICE_SLM           5   /* 50ms - long for inference batches */
#define TIMESLICE_SYSTEM        3   /* 30ms */
#define TIMESLICE_USER          2   /* 20ms */
#define TIMESLICE_BACKGROUND    1   /* 10ms - runs only when nothing else needs CPU */
```

### Process States

```c
typedef enum process_state {
    PROC_STATE_CREATED,     /* just created, not yet runnable */
    PROC_STATE_READY,       /* on run queue, waiting for CPU */
    PROC_STATE_RUNNING,     /* currently executing on CPU */
    PROC_STATE_BLOCKED,     /* waiting for I/O, IPC, or event */
    PROC_STATE_SLEEPING,    /* timed sleep, wakes after N ticks */
    PROC_STATE_TERMINATED   /* finished, awaiting cleanup */
} process_state_t;
```

### Process Control Block

```c
#define PROC_NAME_MAX       64
#define KERNEL_STACK_SIZE   (16 * 1024)  /* 16KB kernel stack per process */

typedef struct process {
    /* Identity */
    uint64_t            pid;
    char                name[PROC_NAME_MAX];
    priority_class_t    priority;
    process_state_t     state;

    /* CPU context (saved on context switch) */
    struct cpu_context {
        uint64_t rsp;       /* stack pointer */
        uint64_t rbp;       /* base pointer */
        uint64_t rip;       /* instruction pointer (return address) */
        uint64_t rax, rbx, rcx, rdx;
        uint64_t rsi, rdi;
        uint64_t r8, r9, r10, r11, r12, r13, r14, r15;
        uint64_t rflags;
        uint64_t cr3;       /* page table root (address space) */
    } context;

    /* Stack */
    uint64_t kernel_stack_base;     /* bottom of kernel stack (allocated) */
    uint64_t kernel_stack_top;      /* top (initial RSP value) */

    /* Scheduling */
    uint32_t timeslice;             /* ticks remaining in current quantum */
    uint32_t timeslice_max;         /* full quantum for this priority */
    uint64_t total_ticks;           /* total CPU ticks consumed (stats) */
    uint64_t wake_tick;             /* tick at which to wake (if sleeping) */

    /* Linkage */
    struct process *next;           /* next in run queue or wait queue */
    struct process *prev;           /* prev in run queue (doubly linked) */

    /* SLM flag */
    int is_slm_task;                /* 1 if this process runs SLM inference */
} process_t;
```

### Run Queue

```c
/* Per-priority run queue (doubly-linked circular list) */
typedef struct run_queue {
    process_t *head;        /* first process in queue */
    uint32_t   count;       /* number of processes in queue */
} run_queue_t;

/* Scheduler global state */
typedef struct scheduler {
    run_queue_t queues[PRIORITY_CLASS_COUNT]; /* one queue per priority */
    process_t  *current;    /* currently running process */
    process_t  *idle;       /* idle process (runs when all queues empty) */
    uint64_t    next_pid;   /* next PID to assign */
    uint64_t    tick_count; /* global tick counter */
    uint64_t    switches;   /* total context switches (stats) */
    int         enabled;    /* 0 during early boot, 1 when scheduler is active */
} scheduler_t;
```

## Interface (`kernel/include/sched.h`)

```c
/* Initialize the scheduler. Creates the idle process.
 * Must be called after mm subsystem is ready. */
void sched_init(void);

/* Create a new process with given name, entry point, and priority.
 * Allocates kernel stack, sets up initial context so that the process
 * begins execution at 'entry' when first scheduled.
 * Returns pointer to the new process, or NULL on failure. */
process_t *sched_create_process(const char *name, void (*entry)(void),
                                priority_class_t priority);

/* Create an SLM inference process. Same as sched_create_process but
 * sets is_slm_task=1 and priority=PRIORITY_SLM automatically. */
process_t *sched_create_slm_process(const char *name, void (*entry)(void));

/* Voluntarily yield the CPU. Puts current process at back of its
 * priority queue and reschedules. */
void sched_yield(void);

/* Timer-driven schedule function. Called from the PIT/APIC timer
 * interrupt handler. Decrements timeslice, reschedules if expired.
 * This is the main preemption point. */
void sched_schedule(void);

/* Block the current process. Removes it from run queue and sets
 * state to BLOCKED. Must be paired with sched_unblock() from
 * another context (e.g., IPC receive, device interrupt). */
void sched_block(process_t *proc);

/* Unblock a blocked process. Sets state to READY and adds it
 * to the appropriate run queue. If the unblocked process has
 * higher priority than current, sets a reschedule flag. */
void sched_unblock(process_t *proc);

/* Put a process to sleep for N milliseconds.
 * Process is removed from run queue; timer handler wakes it. */
void sched_sleep(process_t *proc, uint64_t ms);

/* Terminate a process. Sets state to TERMINATED, frees kernel stack,
 * removes from all queues. Current process must not terminate itself
 * without yielding (use sched_exit() instead). */
void sched_terminate(process_t *proc);

/* Terminate the current process (self-exit). Marks as TERMINATED
 * and immediately reschedules. Stack is freed by idle process. */
void sched_exit(void);

/* Get pointer to the currently running process. */
process_t *sched_current(void);

/* Get a process by PID. Returns NULL if not found. */
process_t *sched_get_by_pid(uint64_t pid);

/* Print all processes and their states to serial (debug). */
void sched_list_processes(void);

/* Get scheduler statistics. */
void sched_stats(uint64_t *total_processes, uint64_t *total_switches,
                 uint64_t *tick_count);

/* Enable/disable the scheduler (used during early boot initialization). */
void sched_enable(void);
void sched_disable(void);
```

### Context Switch (Assembly)

```c
/* Implemented in kernel/sched/switch.asm.
 * Saves callee-saved registers to old stack, switches RSP, restores
 * callee-saved registers from new stack. The return address on the
 * new stack determines where execution resumes. */
extern void context_switch(uint64_t *old_rsp_ptr, uint64_t new_rsp);
```

## Behavior

### Scheduling Algorithm

The scheduler uses **multi-level priority queues with round-robin within each level**.

```
sched_schedule() [called from timer interrupt]:
  1. Increment global tick_count
  2. Check sleep queue: wake any processes whose wake_tick <= tick_count
  3. If scheduler not enabled: return immediately
  4. Decrement current->timeslice
  5. If current->timeslice > 0 AND no higher-priority process was unblocked: return
  6. Reset current->timeslice to current->timeslice_max
  7. Move current to back of its priority queue (if still READY/RUNNING)
  8. Select next process:
     a. For priority = KERNEL down to BACKGROUND:
        If queues[priority].count > 0:
           next = queues[priority].head
           break
     b. If no runnable process found: next = idle
  9. If next == current: return (no switch needed)
  10. Set current->state = READY (if still running)
  11. Set next->state = RUNNING
  12. Update scheduler->current = next
  13. Increment switches counter
  14. context_switch(&current->context.rsp, next->context.rsp)
```

### SLM Priority Boost

SLM inference tasks (processes with `is_slm_task == 1`) receive special handling:

1. They are always created at `PRIORITY_SLM` (priority 1)
2. Their timeslice is 50ms (5 ticks) -- longest of any priority class
3. When an SLM task is unblocked (e.g., new command arrives on SLM channel), it gets an **immediate reschedule** if the current process is `PRIORITY_SYSTEM` or lower
4. During active inference, SLM tasks are not demoted even if they use full timeslice

### Process Creation

```
sched_create_process(name, entry, priority):
  1. Allocate process_t via kmalloc
  2. Assign next_pid, copy name, set priority
  3. Allocate KERNEL_STACK_SIZE bytes for kernel stack
  4. Set kernel_stack_top = stack_base + KERNEL_STACK_SIZE
  5. Initialize context:
     - rsp = kernel_stack_top - sizeof(initial_frame)
     - Push onto stack: entry address (as return addr for context_switch)
     - Push callee-saved registers (all zero initially)
     - rflags = 0x200 (interrupts enabled)
     - cr3 = kernel PML4 (kernel thread) or new address space (user)
  6. Set timeslice_max based on priority class
  7. Set state = READY
  8. Insert into queues[priority]
  9. Return process pointer
```

### Idle Process

The idle process runs at lowest priority and executes `hlt` in a loop:

```c
static void idle_entry(void) {
    while (1) {
        asm volatile("hlt");  /* halt until next interrupt */
    }
}
```

It is created during `sched_init()` and is never placed on any run queue; the scheduler selects it as a fallback when all queues are empty.

### Sleep and Wake

```
sched_sleep(proc, ms):
  1. Convert ms to ticks: ticks = ms / 10 (10ms per tick)
  2. proc->wake_tick = tick_count + ticks
  3. proc->state = SLEEPING
  4. Remove from run queue
  5. (Timer handler checks sleep list each tick)

Timer handler check:
  For each sleeping process:
    if tick_count >= proc->wake_tick:
      sched_unblock(proc)  /* moves to READY, adds to run queue */
```

### Context Switch Assembly

```nasm
; context_switch(old_rsp_ptr [rdi], new_rsp [rsi])
; Called with interrupts disabled (cli in sched_schedule)
context_switch:
    ; Save callee-saved registers on current stack
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    pushfq              ; save rflags

    ; Save current RSP
    mov [rdi], rsp

    ; Load new RSP
    mov rsp, rsi

    ; Restore callee-saved registers from new stack
    popfq
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret                 ; return to the new process's saved RIP
```

### Edge Cases

- **No runnable processes**: idle process runs `hlt` until next interrupt
- **Process terminates while holding resources**: the termination path does NOT automatically release IPC channels or memory; the subsystem that blocked the process is responsible for cleanup
- **Timer interrupt during context switch**: interrupts are disabled (cli) at the start of `sched_schedule()` and re-enabled (sti) after the switch
- **SLM task blocks on I/O**: treated like any blocked process; unblock restores SLM priority
- **Priority inversion**: not handled in V1; future work may add priority inheritance for IPC
- **Stack overflow**: each kernel stack is bounded; guard page (unmapped) below stack base catches overflow as page fault

## Files

| File | Purpose |
|------|---------|
| `kernel/sched/sched.c`    | Scheduler core: init, create, schedule, block/unblock |
| `kernel/sched/switch.asm` | Context switch assembly routine |
| `kernel/include/sched.h`  | Scheduler interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for process_t and kernel stack allocation
- **boot/idt**: timer interrupt (IRQ0) calls `sched_schedule()`
- **drivers/pit**: provides periodic timer tick
- **ipc**: SLM command channel triggers unblock of SLM tasks

## Acceptance Criteria

1. Process creation succeeds: `sched_create_process()` returns valid process with unique PID
2. Two processes round-robin: each runs alternately verified by serial output interleaving
3. Three priority classes tested: KERNEL task always runs before USER task; USER before BACKGROUND
4. SLM task (PRIORITY_SLM) preempts SYSTEM and USER tasks when unblocked
5. SLM timeslice is 50ms: verified by counting ticks between SLM context switches
6. `sched_yield()` immediately switches to next runnable process
7. `sched_block()` / `sched_unblock()` correctly removes and re-adds process to run queue
8. `sched_sleep(proc, 100)` wakes process after ~100ms (10 ticks, +/- 1 tick tolerance)
9. `sched_terminate()` frees kernel stack and removes process from all queues
10. `sched_exit()` terminates current process without crash (stack freed by idle)
11. Context switch preserves all registers: test process writes known values to r12-r15, verifies after being rescheduled
12. No stack corruption after 1000+ context switches between 5 processes
13. `sched_list_processes()` accurately reports PID, name, state, priority for all processes
14. Idle process runs `hlt` when all processes are blocked (CPU usage drops verified by QEMU monitor)
15. Guard page triggers page fault on kernel stack overflow (not silent corruption)
