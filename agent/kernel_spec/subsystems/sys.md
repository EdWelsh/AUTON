# System Services Specification

## Overview

The system services subsystem provides the SLM-driven init system for service startup ordering, service descriptors for managing daemons and background tasks, a kernel log ring buffer for diagnostics, and resource monitoring for CPU, memory, disk, and network usage. The SLM queries these facilities for runtime system management, troubleshooting, and informed decision-making about system health.

## Data Structures

### Service Descriptors

```c
/* Service state */
typedef enum svc_state {
    SVC_STATE_STOPPED,      /* not running */
    SVC_STATE_STARTING,     /* init in progress */
    SVC_STATE_RUNNING,      /* actively running */
    SVC_STATE_STOPPING,     /* shutdown in progress */
    SVC_STATE_FAILED,       /* crashed or failed to start */
    SVC_STATE_DISABLED,     /* administratively disabled */
} svc_state_t;

/* Service type */
typedef enum svc_type {
    SVC_TYPE_ONESHOT,       /* runs once at startup, then done */
    SVC_TYPE_DAEMON,        /* long-running background process */
    SVC_TYPE_PERIODIC,      /* runs on a schedule (timer-based) */
} svc_type_t;

/* Service restart policy */
typedef enum svc_restart {
    SVC_RESTART_NEVER,      /* do not restart on failure */
    SVC_RESTART_ON_FAILURE, /* restart only on non-zero exit */
    SVC_RESTART_ALWAYS,     /* always restart (daemon mode) */
} svc_restart_t;

/* Service descriptor */
#define SVC_NAME_MAX        64
#define SVC_DESC_MAX        256
#define SVC_MAX_DEPS        8
#define SVC_MAX_SERVICES    64

typedef struct service {
    /* Identity */
    char            name[SVC_NAME_MAX];
    char            description[SVC_DESC_MAX];
    svc_type_t      type;
    svc_state_t     state;
    svc_restart_t   restart_policy;

    /* Entry point */
    void          (*entry)(void);    /* function pointer for kernel service */
    char            exec_path[256];  /* path for userspace service (future) */

    /* Dependencies: services that must be running before this one starts */
    char            depends_on[SVC_MAX_DEPS][SVC_NAME_MAX];
    uint32_t        dep_count;

    /* Process */
    process_t      *process;        /* scheduler process (NULL if stopped) */
    uint64_t        pid;            /* PID when running */

    /* Timing */
    uint64_t        start_time;     /* tick when last started */
    uint64_t        stop_time;      /* tick when last stopped */
    uint32_t        restart_count;  /* number of restarts */
    uint32_t        restart_delay_ms; /* delay before restart (prevents thrashing) */
    uint64_t        periodic_interval_ms; /* for SVC_TYPE_PERIODIC */

    /* Health */
    int32_t         exit_code;      /* last exit code (-1 if crashed) */
    int             healthy;        /* 1 if service reports healthy */
} service_t;
```

### Init System

```c
/* Init configuration: boot-time service ordering */
#define INIT_MAX_STAGES     8

typedef struct init_stage {
    char        name[SVC_NAME_MAX];     /* stage name (e.g., "early", "network", "services") */
    char        services[16][SVC_NAME_MAX]; /* services in this stage */
    uint32_t    service_count;
    int         parallel;               /* 1 = start services in parallel, 0 = sequential */
} init_stage_t;

typedef struct init_config {
    init_stage_t stages[INIT_MAX_STAGES];
    uint32_t     stage_count;
} init_config_t;

/* Default init stages:
 * Stage 0: "early"     - serial, vga, timer, keyboard (already done by boot)
 * Stage 1: "hardware"  - device framework, SLM init
 * Stage 2: "drivers"   - SLM-driven driver loading
 * Stage 3: "storage"   - filesystem mount, swap
 * Stage 4: "network"   - network config (DHCP)
 * Stage 5: "services"  - user-facing services (web server, etc.)
 * Stage 6: "ready"     - final readiness check, SLM reports system ready
 */
```

### Kernel Log

```c
/* Log severity levels */
typedef enum log_level {
    LOG_EMERG   = 0,    /* system is unusable */
    LOG_ALERT   = 1,    /* action must be taken immediately */
    LOG_CRIT    = 2,    /* critical conditions */
    LOG_ERR     = 3,    /* error conditions */
    LOG_WARN    = 4,    /* warning conditions */
    LOG_NOTICE  = 5,    /* normal but significant */
    LOG_INFO    = 6,    /* informational */
    LOG_DEBUG   = 7,    /* debug-level messages */
} log_level_t;

/* Log entry */
#define LOG_MSG_MAX         256
#define LOG_SUBSYS_MAX      32

typedef struct log_entry {
    uint64_t    timestamp;          /* scheduler tick when logged */
    log_level_t level;
    char        subsystem[LOG_SUBSYS_MAX]; /* originating subsystem (e.g., "net", "slm") */
    char        message[LOG_MSG_MAX];
    uint64_t    pid;                /* PID of logging process (0 for kernel) */
} log_entry_t;

/* Log ring buffer */
#define LOG_RING_SIZE       1024    /* entries in the ring buffer */

typedef struct log_ring {
    log_entry_t entries[LOG_RING_SIZE];
    uint32_t    head;               /* next write position */
    uint32_t    tail;               /* oldest unread position */
    uint32_t    count;              /* current entry count */
    uint64_t    total_logged;       /* total entries ever logged (wraps) */
    log_level_t min_level;          /* only log entries >= this level */
    int         echo_serial;        /* 1 = also print to serial */
} log_ring_t;
```

### Resource Monitoring

```c
/* CPU statistics */
typedef struct cpu_stats {
    uint64_t total_ticks;           /* total scheduler ticks */
    uint64_t idle_ticks;            /* ticks spent in idle process */
    uint64_t kernel_ticks;          /* ticks in kernel priority */
    uint64_t slm_ticks;            /* ticks in SLM priority */
    uint64_t system_ticks;          /* ticks in system priority */
    uint64_t user_ticks;            /* ticks in user priority */
    uint64_t background_ticks;      /* ticks in background priority */
    uint32_t context_switches;      /* total context switches */
    uint32_t process_count;         /* current number of processes */
    uint8_t  usage_percent;         /* CPU usage 0-100 */
} cpu_stats_t;

/* Memory statistics */
typedef struct mem_stats {
    uint64_t total_bytes;           /* total physical memory */
    uint64_t used_bytes;            /* used physical memory */
    uint64_t free_bytes;            /* free physical memory */
    uint64_t kernel_bytes;          /* memory used by kernel */
    uint64_t slm_pool_total;        /* SLM pool total */
    uint64_t slm_pool_used;         /* SLM pool used */
    uint64_t slab_total;            /* slab allocator total */
    uint64_t slab_used;             /* slab allocator used */
    uint8_t  usage_percent;         /* memory usage 0-100 */
} mem_stats_t;

/* Disk statistics (per block device) */
typedef struct disk_stats {
    uint32_t dev_id;                /* block device ID */
    char     name[32];              /* device name (e.g., "sda") */
    uint64_t total_bytes;           /* total device capacity */
    uint64_t used_bytes;            /* used space (from filesystem) */
    uint64_t free_bytes;            /* free space */
    uint64_t read_count;            /* total sectors read */
    uint64_t write_count;           /* total sectors written */
    uint8_t  usage_percent;         /* disk usage 0-100 */
} disk_stats_t;

/* Network statistics (per interface) */
typedef struct net_stats {
    uint32_t dev_id;                /* network device ID */
    char     name[32];              /* interface name (e.g., "eth0") */
    uint32_t ip_addr;              /* configured IP (0 if not configured) */
    int      link_up;               /* 1 = link up */
    uint64_t rx_bytes;              /* total bytes received */
    uint64_t tx_bytes;              /* total bytes transmitted */
    uint64_t rx_packets;            /* total packets received */
    uint64_t tx_packets;            /* total packets transmitted */
    uint64_t rx_errors;             /* receive errors */
    uint64_t tx_errors;             /* transmit errors */
    uint64_t rx_dropped;            /* dropped on receive */
} net_stats_t;

/* System uptime and load */
typedef struct system_info {
    uint64_t uptime_ticks;          /* ticks since boot */
    uint64_t uptime_seconds;        /* seconds since boot */
    cpu_stats_t cpu;
    mem_stats_t mem;
    disk_stats_t disks[8];          /* up to 8 block devices */
    uint32_t disk_count;
    net_stats_t nets[4];            /* up to 4 network interfaces */
    uint32_t net_count;
    uint32_t service_count;         /* total services */
    uint32_t service_running;       /* running services */
    uint32_t service_failed;        /* failed services */
} system_info_t;
```

### SLM System Management Queries

```c
/* Query types for SLM system management */
typedef enum sys_query_type {
    SYS_QUERY_OVERVIEW,         /* full system summary */
    SYS_QUERY_CPU,              /* CPU usage details */
    SYS_QUERY_MEMORY,           /* memory usage details */
    SYS_QUERY_DISK,             /* disk usage details */
    SYS_QUERY_NETWORK,          /* network status and stats */
    SYS_QUERY_SERVICES,         /* service status list */
    SYS_QUERY_LOGS,             /* recent log entries */
    SYS_QUERY_UPTIME,           /* system uptime */
    SYS_QUERY_PROCESSES,        /* running process list */
} sys_query_type_t;

/* Query result: formatted as text for SLM consumption */
typedef struct sys_query_result {
    sys_query_type_t type;
    char             text[4096];    /* human-readable result text */
    uint32_t         text_len;
    int              has_alerts;    /* 1 if any alerts/warnings detected */
} sys_query_result_t;
```

## Interface (`kernel/include/sys.h`)

### Init System

```c
/* Initialize the init system. Sets up default init stages.
 * Must be called after sched and ipc are ready. */
void init_system_start(void);

/* Register a service with the init system. */
int svc_register(service_t *svc);

/* Unregister a service. Stops it first if running. */
void svc_unregister(const char *name);

/* Start a service by name. Checks dependencies first.
 * Returns 0 on success, -1 if deps not met, -2 if start fails. */
int svc_start(const char *name);

/* Stop a service by name. Signals the process to terminate.
 * Returns 0 on success. */
int svc_stop(const char *name);

/* Restart a service (stop + start). */
int svc_restart(const char *name);

/* Enable a service (allow it to start). */
int svc_enable(const char *name);

/* Disable a service (prevent it from starting). */
int svc_disable(const char *name);

/* Get service status. Returns NULL if service not found. */
const service_t *svc_status(const char *name);

/* List all services. Fills 'list' with pointers. Returns count. */
uint32_t svc_list(service_t **list, uint32_t max);

/* Print all service statuses to serial (debug). */
void svc_list_all(void);

/* SLM-driven init: let the SLM determine startup order and configuration.
 * The SLM examines available services and hardware, then calls
 * svc_start() for each service in optimal order. */
void svc_slm_init(void);

/* Service health check: verify all running services are healthy. */
int svc_health_check(void);
```

### Kernel Log

```c
/* Initialize the kernel log ring buffer. */
void klog_init(void);

/* Log a message. Formatted like printf. Thread-safe.
 * Also echoes to serial if echo_serial is enabled. */
void klog(log_level_t level, const char *subsystem, const char *fmt, ...);

/* Convenience macros */
#define KLOG_EMERG(subsys, fmt, ...)   klog(LOG_EMERG, subsys, fmt, ##__VA_ARGS__)
#define KLOG_ERR(subsys, fmt, ...)     klog(LOG_ERR, subsys, fmt, ##__VA_ARGS__)
#define KLOG_WARN(subsys, fmt, ...)    klog(LOG_WARN, subsys, fmt, ##__VA_ARGS__)
#define KLOG_INFO(subsys, fmt, ...)    klog(LOG_INFO, subsys, fmt, ##__VA_ARGS__)
#define KLOG_DEBUG(subsys, fmt, ...)   klog(LOG_DEBUG, subsys, fmt, ##__VA_ARGS__)

/* Read log entries. Returns entries from position 'start' up to 'count'.
 * Fills 'entries' array. Returns actual count read. */
uint32_t klog_read(uint32_t start, log_entry_t *entries, uint32_t count);

/* Read most recent N entries. */
uint32_t klog_read_recent(log_entry_t *entries, uint32_t count);

/* Search logs by subsystem name. Returns matching entries. */
uint32_t klog_search(const char *subsystem, log_level_t min_level,
                     log_entry_t *entries, uint32_t max_entries);

/* Set minimum log level (entries below this are dropped). */
void klog_set_level(log_level_t min_level);

/* Enable/disable echoing to serial. */
void klog_set_echo(int enable);

/* Get total number of entries logged since boot. */
uint64_t klog_total_count(void);

/* Clear the log ring buffer. */
void klog_clear(void);

/* Format a log entry as a human-readable string. */
void klog_format(const log_entry_t *entry, char *buf, uint32_t bufsize);
```

### Resource Monitoring

```c
/* Initialize resource monitoring. Starts background collection thread. */
void resmon_init(void);

/* Get current CPU statistics. */
void resmon_cpu_stats(cpu_stats_t *stats);

/* Get current memory statistics. */
void resmon_mem_stats(mem_stats_t *stats);

/* Get disk statistics for a specific device. */
void resmon_disk_stats(uint32_t dev_id, disk_stats_t *stats);

/* Get network statistics for a specific interface. */
void resmon_net_stats(uint32_t dev_id, net_stats_t *stats);

/* Get comprehensive system info (all stats combined). */
void resmon_system_info(system_info_t *info);

/* Format system info as human-readable text (for SLM). */
void resmon_format_text(const system_info_t *info, char *buf, uint32_t bufsize);

/* Check for resource alerts (high CPU, low memory, disk full, etc.).
 * Returns count of alerts, fills alert descriptions. */
uint32_t resmon_check_alerts(char alerts[][256], uint32_t max_alerts);
```

### SLM System Management Interface

```c
/* Execute a system management query for the SLM.
 * Called when SLM processes a SYSTEM_MANAGE intent.
 * Gathers data from resmon, klog, svc, and formats a response. */
int sys_query(sys_query_type_t type, sys_query_result_t *result);

/* Execute a system management action for the SLM.
 * Actions include starting/stopping services, adjusting log levels,
 * clearing caches, etc. */
int sys_action(const char *action, const char *args, char *result_buf,
               uint32_t bufsize);

/* Build a complete system health report for SLM troubleshooting. */
void sys_health_report(char *buf, uint32_t bufsize);
```

## Behavior

### SLM-Driven Init Sequence

```
init_system_start():
  1. Create default init_config with stages
  2. Send init config to SLM via IPC for review/modification
  3. SLM may reorder stages or add services based on hardware detection

svc_slm_init():
  For each stage in init_config:
    1. SLM reviews services in this stage
    2. If stage.parallel == 1:
       - Start all services concurrently (sched_create_process for each)
       - Wait for all to reach SVC_STATE_RUNNING or timeout
    3. If stage.parallel == 0:
       - Start services sequentially, verify each before next
    4. Log stage completion: KLOG_INFO("init", "Stage '%s' complete", stage.name)
    5. If any service fails:
       - SLM decides: retry, skip, or halt
       - Failed services logged as SVC_STATE_FAILED

  After all stages:
    SLM reports: "System initialization complete. N services running."
```

### Service Start with Dependency Resolution

```
svc_start("nginx"):
  1. Look up service descriptor by name
  2. If state == SVC_STATE_RUNNING: return 0 (already running)
  3. If state == SVC_STATE_DISABLED: return -EPERM
  4. Check dependencies:
     For each dep in depends_on:
       dep_svc = svc_status(dep)
       If dep_svc == NULL or dep_svc->state != SVC_STATE_RUNNING:
         attempt svc_start(dep)  (recursive)
         If dep start fails: return -1 (deps not met)
  5. Set state = SVC_STATE_STARTING
  6. Create process: sched_create_process(svc->name, svc->entry, PRIORITY_SYSTEM)
  7. svc->process = new_process
  8. svc->pid = new_process->pid
  9. svc->start_time = current_tick
  10. Set state = SVC_STATE_RUNNING
  11. KLOG_INFO("init", "Service '%s' started (PID %d)", name, pid)
  12. Return 0
```

### Service Failure and Restart

```
When a service process terminates unexpectedly:
  1. sched detects PROC_STATE_TERMINATED
  2. Notify init system: svc_process_exited(pid, exit_code)
  3. Look up service by PID
  4. Set state = SVC_STATE_FAILED
  5. svc->exit_code = exit_code
  6. KLOG_ERR("init", "Service '%s' failed (exit code %d)", name, exit_code)
  7. Check restart policy:
     SVC_RESTART_NEVER: leave as failed
     SVC_RESTART_ON_FAILURE: if exit_code != 0, schedule restart
     SVC_RESTART_ALWAYS: always schedule restart
  8. If restarting:
     a. Wait restart_delay_ms (prevent thrashing)
     b. Increment restart_count
     c. If restart_count > 5: set SVC_STATE_FAILED, notify SLM
     d. Else: svc_start(name)
  9. Send IPC_MSG_SYS_ALERT to SLM if failure occurred
```

### Kernel Log Algorithm

```
klog(level, subsystem, fmt, ...):
  1. If level < min_level: return (filtered out)
  2. Disable interrupts (brief critical section)
  3. Format message via vsnprintf into log_entry
  4. Fill: timestamp = scheduler tick_count
  5. Fill: pid = sched_current()->pid (or 0 if no current)
  6. Copy subsystem string
  7. ring->entries[ring->head] = entry
  8. ring->head = (ring->head + 1) % LOG_RING_SIZE
  9. If ring->count < LOG_RING_SIZE: ring->count++
     Else: ring->tail = (ring->tail + 1) % LOG_RING_SIZE (overwrite oldest)
  10. ring->total_logged++
  11. Enable interrupts
  12. If echo_serial: serial_printf("[%s] %s: %s\n", level_str, subsystem, message)
```

### Resource Monitoring Collection

```
resmon_collection_thread() [runs as PRIORITY_BACKGROUND]:
  Loop every 1 second:
    CPU stats:
      1. Read scheduler tick counters per priority class
      2. Calculate delta since last sample
      3. usage_percent = 100 - (idle_delta * 100 / total_delta)

    Memory stats:
      1. pmm_free_count() * PAGE_SIZE = free_bytes
      2. total = pmm_total_count() * PAGE_SIZE
      3. slm_pool_stats(&slm_total, &slm_used)
      4. slab_dump_stats() for slab usage

    Disk stats (for each block device):
      1. blk_get_info(dev_id, &info) for total size
      2. vfs_statfs(mount_point, &stat) for used/free
      3. Track cumulative read/write sector counts

    Network stats (for each NIC):
      1. Read NIC driver rx/tx counters
      2. net_link_status(dev_id) for link state
      3. net_get_config(dev_id) for IP address
```

### SLM Query Handling

```
sys_query(SYS_QUERY_OVERVIEW, result):
  1. Gather all stats: resmon_system_info(&info)
  2. Format into text:
     "System Status:
      Uptime: 2h 15m
      CPU: 23% (kernel 5%, SLM 8%, user 10%)
      Memory: 156MB / 512MB (30%)
      Disk: /dev/sda - 2.1GB / 10GB (21%)
      Network: eth0 - 192.168.1.100 (link up, rx 15MB tx 2MB)
      Services: 5 running, 0 failed
      SLM: rule engine, 42 requests processed"
  3. Check for alerts: resmon_check_alerts()
  4. If alerts: result->has_alerts = 1, append alert text

sys_query(SYS_QUERY_LOGS, result):
  1. klog_read_recent(entries, 20) -- last 20 entries
  2. Format each entry into text
  3. If errors/warnings present: result->has_alerts = 1
```

### SLM Troubleshooting Flow

```
SLM receives TROUBLESHOOT intent: "why is the network down?"

  1. sys_query(SYS_QUERY_NETWORK, &net_result)
     -> Check link status: is NIC link up?
     -> Check IP config: is DHCP configured?
     -> Check gateway ping: can we reach gateway?

  2. klog_search("net", LOG_ERR, ...)
     -> Find recent network errors

  3. Build diagnosis:
     - If link down: "Network cable disconnected or NIC driver not loaded"
     - If no IP: "DHCP failed. Check network connectivity"
     - If no gateway: "Gateway unreachable. Check router"
     - If DNS fails: "DNS resolution failing. Check DNS server"

  4. Return diagnostic report to user
```

### Edge Cases

- **Service dependency cycle**: `svc_start()` tracks visited set; returns -1 on cycle
- **Service start timeout**: if service doesn't reach RUNNING within 30 seconds, mark as FAILED
- **Log ring full**: oldest entries are overwritten (ring buffer); total_logged still increments
- **Resource monitor during early boot**: returns partial data until all subsystems initialize
- **All services fail**: SLM enters emergency mode, attempts diagnostics, reports to serial
- **Disk full**: resmon detects usage > 90%, sends SYS_ALERT to SLM before 100%
- **Memory pressure**: resmon detects free < 10%, alerts SLM, which may stop non-essential services
- **SLM process crashes**: init system restarts SLM process (SVC_RESTART_ALWAYS); critical for system operation

## Files

| File | Purpose |
|------|---------|
| `kernel/sys/init.c`       | Init system: stage management, SLM-driven startup |
| `kernel/sys/service.c`    | Service manager: register, start, stop, restart, health |
| `kernel/sys/klog.c`       | Kernel log ring buffer |
| `kernel/sys/resmon.c`     | Resource monitoring: CPU, memory, disk, network stats |
| `kernel/sys/query.c`      | SLM system management query/action handling |
| `kernel/include/sys.h`    | System services interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for service descriptors, log entries
- **sched**: process creation for services (PRIORITY_SYSTEM), tick counter for uptime
- **ipc**: SLM command channel for management intents, alert messages
- **slm**: SLM processes SYSTEM_MANAGE and TROUBLESHOOT intents
- **drivers**: timer ticks for periodic services, serial for log echo
- **fs**: VFS for procfs entries (exposes stats as files)
- **net**: network statistics from NIC drivers
- **dev**: block device info for disk statistics

## Acceptance Criteria

1. Init system starts services in correct stage order
2. Service with dependencies: dep is started before dependent
3. `svc_start("nginx")` creates process and transitions to SVC_STATE_RUNNING
4. `svc_stop("nginx")` terminates process and transitions to SVC_STATE_STOPPED
5. Service restart: kill service process, verify it auto-restarts (SVC_RESTART_ON_FAILURE)
6. Restart thrashing prevention: after 5 consecutive failures, service stays FAILED
7. `klog(LOG_INFO, "test", "hello %d", 42)` writes entry to ring buffer
8. `klog_read_recent(entries, 10)` returns the 10 most recent entries in order
9. `klog_search("net", LOG_ERR, ...)` returns only network error entries
10. Log echo to serial: klog messages appear on serial output when echo enabled
11. Log ring wraps correctly: write 1025 entries, verify oldest was overwritten
12. `resmon_cpu_stats()` returns non-zero idle and total ticks
13. `resmon_mem_stats()` total matches boot-detected RAM; used + free = total
14. `resmon_disk_stats()` reports correct capacity for QEMU disk
15. `resmon_net_stats()` tracks rx/tx bytes after sending test packets
16. `sys_query(SYS_QUERY_OVERVIEW)` returns formatted text covering all subsystems
17. Alert detection: artificially fill memory to >90%, verify resmon_check_alerts fires
18. SLM troubleshoot flow: simulate network down (unload driver), SLM diagnoses "NIC driver not loaded"
19. Procfs: `/proc/meminfo` read returns current memory statistics
20. SLM init sequence completes without hangs; all services reachable via svc_status
