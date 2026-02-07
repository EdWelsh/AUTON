# Network Stack Specification

## Overview

The network subsystem implements a minimal TCP/IP stack providing Ethernet frame handling, ARP address resolution, IPv4 routing, ICMP echo, UDP and basic TCP transport, plus application-layer DHCP, DNS, and HTTP clients. The SLM triggers network configuration (DHCP, DNS setup) during system initialization and uses the HTTP client to fetch packages and updates.

## Data Structures

### Ethernet

```c
/* Ethernet frame constants */
#define ETH_ADDR_LEN        6       /* MAC address length */
#define ETH_HEADER_LEN      14      /* dst + src + ethertype */
#define ETH_MTU             1500    /* maximum payload */
#define ETH_FRAME_MAX       (ETH_HEADER_LEN + ETH_MTU)

/* EtherType values */
#define ETHERTYPE_IPV4      0x0800
#define ETHERTYPE_ARP       0x0806
#define ETHERTYPE_IPV6      0x86DD

/* Ethernet header */
typedef struct eth_header {
    uint8_t  dst[ETH_ADDR_LEN];
    uint8_t  src[ETH_ADDR_LEN];
    uint16_t ethertype;         /* big-endian */
} __attribute__((packed)) eth_header_t;

/* Broadcast MAC address */
#define ETH_BROADCAST   ((uint8_t[]){0xFF,0xFF,0xFF,0xFF,0xFF,0xFF})
```

### ARP

```c
/* ARP operation codes */
#define ARP_OP_REQUEST      1
#define ARP_OP_REPLY        2

/* ARP header (for Ethernet + IPv4) */
typedef struct arp_header {
    uint16_t hw_type;           /* 1 = Ethernet */
    uint16_t proto_type;        /* 0x0800 = IPv4 */
    uint8_t  hw_addr_len;      /* 6 for Ethernet */
    uint8_t  proto_addr_len;   /* 4 for IPv4 */
    uint16_t opcode;            /* ARP_OP_REQUEST or ARP_OP_REPLY */
    uint8_t  sender_mac[6];
    uint32_t sender_ip;         /* big-endian */
    uint8_t  target_mac[6];
    uint32_t target_ip;         /* big-endian */
} __attribute__((packed)) arp_header_t;

/* ARP cache entry */
#define ARP_CACHE_SIZE      64
#define ARP_TIMEOUT_TICKS   30000   /* 5 minutes at 100 Hz */

typedef struct arp_entry {
    uint32_t ip;                /* IPv4 address */
    uint8_t  mac[ETH_ADDR_LEN]; /* resolved MAC address */
    uint64_t timestamp;         /* tick when entry was created/refreshed */
    int      valid;             /* 1 if entry is resolved */
    int      pending;           /* 1 if ARP request sent, waiting reply */
} arp_entry_t;
```

### IPv4

```c
/* IPv4 header */
typedef struct ipv4_header {
    uint8_t  version_ihl;       /* version (4 bits) + IHL (4 bits) */
    uint8_t  tos;               /* type of service */
    uint16_t total_length;      /* total packet length (big-endian) */
    uint16_t identification;
    uint16_t flags_fragment;    /* flags (3 bits) + fragment offset (13 bits) */
    uint8_t  ttl;               /* time to live */
    uint8_t  protocol;          /* upper layer protocol */
    uint16_t checksum;          /* header checksum (big-endian) */
    uint32_t src_ip;            /* source IP (big-endian) */
    uint32_t dst_ip;            /* destination IP (big-endian) */
} __attribute__((packed)) ipv4_header_t;

/* IP protocols */
#define IP_PROTO_ICMP       1
#define IP_PROTO_TCP        6
#define IP_PROTO_UDP        17

/* IPv4 configuration for a network interface */
typedef struct net_config {
    uint32_t ip_addr;           /* our IP address (big-endian) */
    uint32_t subnet_mask;       /* subnet mask */
    uint32_t gateway;           /* default gateway */
    uint32_t dns_server;        /* DNS server address */
    uint32_t dev_id;            /* network device ID */
    uint8_t  mac_addr[6];       /* our MAC address */
    int      configured;        /* 1 if DHCP/manual config complete */
} net_config_t;

/* Routing table entry */
#define ROUTE_TABLE_SIZE    16

typedef struct route_entry {
    uint32_t network;           /* destination network */
    uint32_t netmask;           /* network mask */
    uint32_t gateway;           /* next hop (0 = direct) */
    uint32_t dev_id;            /* outgoing device */
    int      active;
} route_entry_t;
```

### ICMP

```c
/* ICMP header */
typedef struct icmp_header {
    uint8_t  type;
    uint8_t  code;
    uint16_t checksum;          /* big-endian */
    uint16_t id;                /* for echo req/reply */
    uint16_t sequence;          /* for echo req/reply */
} __attribute__((packed)) icmp_header_t;

/* ICMP types */
#define ICMP_ECHO_REPLY     0
#define ICMP_DEST_UNREACH   3
#define ICMP_ECHO_REQUEST   8
#define ICMP_TIME_EXCEEDED  11
```

### UDP

```c
/* UDP header */
typedef struct udp_header {
    uint16_t src_port;          /* big-endian */
    uint16_t dst_port;          /* big-endian */
    uint16_t length;            /* header + data length (big-endian) */
    uint16_t checksum;          /* big-endian (optional in IPv4) */
} __attribute__((packed)) udp_header_t;
```

### TCP

```c
/* TCP header */
typedef struct tcp_header {
    uint16_t src_port;          /* big-endian */
    uint16_t dst_port;
    uint32_t seq_num;           /* sequence number */
    uint32_t ack_num;           /* acknowledgment number */
    uint8_t  data_offset;       /* data offset (4 bits) + reserved (4 bits) */
    uint8_t  flags;             /* TCP flags */
    uint16_t window;            /* window size */
    uint16_t checksum;
    uint16_t urgent_ptr;
} __attribute__((packed)) tcp_header_t;

/* TCP flags */
#define TCP_FIN     0x01
#define TCP_SYN     0x02
#define TCP_RST     0x04
#define TCP_PSH     0x08
#define TCP_ACK     0x10
#define TCP_URG     0x20

/* TCP connection state */
typedef enum tcp_state {
    TCP_CLOSED,
    TCP_LISTEN,
    TCP_SYN_SENT,
    TCP_SYN_RECEIVED,
    TCP_ESTABLISHED,
    TCP_FIN_WAIT_1,
    TCP_FIN_WAIT_2,
    TCP_CLOSE_WAIT,
    TCP_CLOSING,
    TCP_LAST_ACK,
    TCP_TIME_WAIT,
} tcp_state_t;

/* TCP connection control block */
#define TCP_RX_BUF_SIZE     65536
#define TCP_TX_BUF_SIZE     65536
#define TCP_MAX_CONNECTIONS 64

typedef struct tcp_conn {
    /* Connection identity (4-tuple) */
    uint32_t    local_ip;
    uint16_t    local_port;
    uint32_t    remote_ip;
    uint16_t    remote_port;

    /* State */
    tcp_state_t state;
    uint32_t    snd_una;        /* oldest unacknowledged sequence number */
    uint32_t    snd_nxt;        /* next sequence number to send */
    uint32_t    rcv_nxt;        /* next expected receive sequence number */
    uint16_t    snd_wnd;        /* send window size */
    uint16_t    rcv_wnd;        /* receive window size */

    /* Buffers */
    uint8_t     rx_buf[TCP_RX_BUF_SIZE];
    uint32_t    rx_head;
    uint32_t    rx_tail;
    uint32_t    rx_count;

    uint8_t     tx_buf[TCP_TX_BUF_SIZE];
    uint32_t    tx_head;
    uint32_t    tx_tail;
    uint32_t    tx_count;

    /* Retransmission */
    uint64_t    rto_ticks;      /* retransmission timeout (ticks) */
    uint64_t    last_send_tick;  /* tick of last send */
    uint32_t    retransmit_count;

    /* Wait queues */
    process_t  *connect_waiter; /* process waiting for connect() */
    process_t  *accept_waiter;  /* process waiting for accept() */
    process_t  *read_waiter;    /* process waiting for data */
    process_t  *write_waiter;   /* process waiting for send buffer space */

    int         active;
} tcp_conn_t;
```

### Socket API

```c
/* Socket types */
typedef enum sock_type {
    SOCK_DGRAM  = 1,    /* UDP */
    SOCK_STREAM = 2,    /* TCP */
    SOCK_RAW    = 3,    /* raw IP */
} sock_type_t;

/* Socket address */
typedef struct sockaddr_in {
    uint32_t sin_addr;          /* IP address (big-endian) */
    uint16_t sin_port;          /* port (big-endian) */
} sockaddr_in_t;

/* Socket descriptor */
#define SOCK_MAX    128

typedef struct socket {
    sock_type_t     type;
    uint32_t        local_ip;
    uint16_t        local_port;
    uint32_t        remote_ip;
    uint16_t        remote_port;
    int             bound;          /* 1 if bind() called */
    int             connected;      /* 1 if connect() called (or accepted) */
    tcp_conn_t     *tcp_conn;       /* TCP connection (if SOCK_STREAM) */

    /* UDP receive queue */
    struct udp_rx_entry {
        uint32_t    from_ip;
        uint16_t    from_port;
        uint8_t     data[ETH_MTU];
        uint32_t    data_len;
    } udp_rx_queue[32];
    uint32_t        udp_rx_head;
    uint32_t        udp_rx_tail;
    uint32_t        udp_rx_count;

    process_t      *rx_waiter;      /* process blocked on recv */
    int             active;
} socket_t;
```

### DHCP

```c
/* DHCP message structure */
#define DHCP_SERVER_PORT    67
#define DHCP_CLIENT_PORT    68
#define DHCP_MAGIC_COOKIE   0x63825363

typedef struct dhcp_message {
    uint8_t  op;            /* 1=request, 2=reply */
    uint8_t  htype;         /* 1=Ethernet */
    uint8_t  hlen;          /* 6 (MAC length) */
    uint8_t  hops;
    uint32_t xid;           /* transaction ID */
    uint16_t secs;
    uint16_t flags;
    uint32_t ciaddr;        /* client IP (if known) */
    uint32_t yiaddr;        /* your (offered) IP */
    uint32_t siaddr;        /* server IP */
    uint32_t giaddr;        /* gateway IP */
    uint8_t  chaddr[16];    /* client hardware address */
    uint8_t  sname[64];     /* server hostname */
    uint8_t  file[128];     /* boot filename */
    uint32_t magic_cookie;  /* 0x63825363 */
    uint8_t  options[312];  /* DHCP options (variable) */
} __attribute__((packed)) dhcp_message_t;

/* DHCP option codes */
#define DHCP_OPT_SUBNET_MASK    1
#define DHCP_OPT_ROUTER         3
#define DHCP_OPT_DNS            6
#define DHCP_OPT_HOSTNAME       12
#define DHCP_OPT_REQUESTED_IP   50
#define DHCP_OPT_LEASE_TIME     51
#define DHCP_OPT_MSG_TYPE       53
#define DHCP_OPT_SERVER_ID      54
#define DHCP_OPT_END            255

/* DHCP message types */
#define DHCP_DISCOVER       1
#define DHCP_OFFER          2
#define DHCP_REQUEST        3
#define DHCP_ACK            5
#define DHCP_NAK            6

/* DHCP client state */
typedef enum dhcp_state {
    DHCP_STATE_INIT,
    DHCP_STATE_SELECTING,
    DHCP_STATE_REQUESTING,
    DHCP_STATE_BOUND,
    DHCP_STATE_RENEWING,
    DHCP_STATE_FAILED,
} dhcp_state_t;
```

### DNS

```c
/* DNS header */
typedef struct dns_header {
    uint16_t id;
    uint16_t flags;
    uint16_t qdcount;       /* question count */
    uint16_t ancount;       /* answer count */
    uint16_t nscount;       /* authority count */
    uint16_t arcount;       /* additional count */
} __attribute__((packed)) dns_header_t;

/* DNS flags */
#define DNS_FLAG_QR     (1 << 15)   /* 0=query, 1=response */
#define DNS_FLAG_RD     (1 << 8)    /* recursion desired */
#define DNS_FLAG_RA     (1 << 7)    /* recursion available */

/* DNS record types */
#define DNS_TYPE_A      1       /* IPv4 address */
#define DNS_TYPE_CNAME  5       /* canonical name */
#define DNS_CLASS_IN    1       /* Internet */

/* DNS cache entry */
#define DNS_CACHE_SIZE  32

typedef struct dns_cache_entry {
    char        name[256];      /* domain name */
    uint32_t    ip;             /* resolved IPv4 address */
    uint32_t    ttl;            /* time-to-live in seconds */
    uint64_t    timestamp;      /* tick when cached */
    int         valid;
} dns_cache_entry_t;
```

### HTTP Client

```c
/* HTTP request/response state */
#define HTTP_MAX_URL        512
#define HTTP_MAX_HEADERS    16
#define HTTP_MAX_BODY       (256 * 1024)    /* 256KB max body */

typedef struct http_header_entry {
    char name[64];
    char value[256];
} http_header_entry_t;

typedef struct http_response {
    int             status_code;        /* e.g., 200, 404 */
    char            status_text[64];    /* e.g., "OK" */
    http_header_entry_t headers[HTTP_MAX_HEADERS];
    uint32_t        header_count;
    uint8_t        *body;               /* response body (kmalloc'd) */
    uint64_t        body_len;
    uint64_t        content_length;     /* from Content-Length header */
} http_response_t;
```

## Interface (`kernel/include/net.h`)

### Network Stack Initialization

```c
/* Initialize the network stack. Sets up protocol handlers, ARP cache,
 * routing table, socket table, DNS cache.
 * Must be called after mm and dev subsystems. */
void net_stack_init(void);

/* Register a network device with the stack. Called when NIC driver loads. */
int net_register_device(uint32_t dev_id);

/* Configure a network interface (manually or from DHCP results).
 * Sets IP, subnet mask, gateway, DNS. */
int net_configure(uint32_t dev_id, uint32_t ip, uint32_t mask,
                  uint32_t gateway, uint32_t dns);

/* Get current network configuration. */
const net_config_t *net_get_config(uint32_t dev_id);
```

### Packet Receive Path

```c
/* Called by NIC driver when a frame is received.
 * Dispatches to appropriate protocol handler based on EtherType. */
void net_rx_frame(uint32_t dev_id, const void *frame, uint32_t length);
```

### ARP

```c
/* Resolve an IP address to a MAC address via ARP.
 * If cached, returns immediately. Otherwise sends ARP request and blocks.
 * Returns 0 on success, -1 on timeout. */
int arp_resolve(uint32_t dev_id, uint32_t ip, uint8_t mac_out[6]);

/* Handle incoming ARP packet. */
void arp_rx(uint32_t dev_id, const void *data, uint32_t length);

/* Flush ARP cache. */
void arp_flush(void);
```

### IPv4

```c
/* Send an IPv4 packet. Adds IP header and resolves next hop.
 * Returns 0 on success. */
int ipv4_send(uint32_t dst_ip, uint8_t protocol,
              const void *payload, uint32_t payload_len);

/* Handle incoming IPv4 packet. Dispatches to ICMP/UDP/TCP. */
void ipv4_rx(uint32_t dev_id, const void *data, uint32_t length);

/* Add a route to the routing table. */
int route_add(uint32_t network, uint32_t netmask, uint32_t gateway,
              uint32_t dev_id);

/* Look up route for destination IP. Returns gateway and dev_id. */
int route_lookup(uint32_t dst_ip, uint32_t *gateway_out, uint32_t *dev_id_out);

/* Compute IPv4 header checksum. */
uint16_t ipv4_checksum(const void *data, uint32_t length);
```

### ICMP

```c
/* Send an ICMP echo request (ping).
 * Returns 0 on success, blocks until reply or timeout. */
int icmp_ping(uint32_t dst_ip, uint16_t id, uint16_t seq,
              uint32_t timeout_ms, uint32_t *rtt_ms);

/* Handle incoming ICMP packet. */
void icmp_rx(uint32_t src_ip, const void *data, uint32_t length);
```

### UDP

```c
/* Send a UDP datagram. */
int udp_send(uint32_t dst_ip, uint16_t dst_port,
             uint16_t src_port, const void *data, uint32_t length);

/* Handle incoming UDP packet. Dispatches to bound sockets. */
void udp_rx(uint32_t src_ip, const void *data, uint32_t length);
```

### TCP

```c
/* Create a new TCP connection (active open / connect).
 * Returns connection ID (>= 0) or negative error. Blocks until connected. */
int tcp_connect(uint32_t dst_ip, uint16_t dst_port, uint16_t src_port);

/* Listen for incoming connections on a port (passive open).
 * Returns connection ID of accepted connection. Blocks. */
int tcp_listen(uint16_t port);
int tcp_accept(int listen_conn_id);

/* Send data on an established TCP connection.
 * Returns bytes sent (may be less than requested if buffer full). */
int tcp_send(int conn_id, const void *data, uint32_t length);

/* Receive data from a TCP connection. Blocks if no data.
 * Returns bytes received, 0 on connection closed, negative on error. */
int tcp_recv(int conn_id, void *buf, uint32_t buf_size);

/* Close a TCP connection (initiates FIN handshake). */
int tcp_close(int conn_id);

/* Handle incoming TCP segment. */
void tcp_rx(uint32_t src_ip, const void *data, uint32_t length);

/* TCP timer: called periodically to handle retransmissions and timeouts. */
void tcp_timer_tick(void);
```

### Socket API (Higher Level)

```c
/* Create a socket. Returns socket fd (>= 0) or negative error. */
int sock_create(sock_type_t type);

/* Bind socket to a local address and port. */
int sock_bind(int sockfd, uint32_t addr, uint16_t port);

/* Connect socket to remote address (TCP: initiates handshake). */
int sock_connect(int sockfd, uint32_t addr, uint16_t port);

/* Listen for connections (TCP only). */
int sock_listen(int sockfd);

/* Accept a connection (TCP only). Returns new socket fd. */
int sock_accept(int sockfd, uint32_t *remote_addr, uint16_t *remote_port);

/* Send data on a connected socket. */
int sock_send(int sockfd, const void *data, uint32_t length);

/* Receive data from a connected socket. */
int sock_recv(int sockfd, void *buf, uint32_t buf_size);

/* Send to specific address (UDP). */
int sock_sendto(int sockfd, const void *data, uint32_t length,
                uint32_t addr, uint16_t port);

/* Receive from any address (UDP). Returns sender info. */
int sock_recvfrom(int sockfd, void *buf, uint32_t buf_size,
                  uint32_t *from_addr, uint16_t *from_port);

/* Close socket. */
int sock_close(int sockfd);
```

### DHCP Client

```c
/* Run DHCP discovery on a network device.
 * Sends DISCOVER, waits for OFFER, sends REQUEST, waits for ACK.
 * On success, configures the interface and returns 0.
 * Timeout after 10 seconds per attempt, 3 attempts. */
int dhcp_configure(uint32_t dev_id);

/* Get DHCP lease info. */
void dhcp_get_lease(uint32_t *ip, uint32_t *mask, uint32_t *gateway,
                    uint32_t *dns, uint32_t *lease_time);

/* Release DHCP lease. */
int dhcp_release(uint32_t dev_id);
```

### DNS Resolver

```c
/* Resolve a hostname to an IPv4 address.
 * Checks cache first, then sends DNS query to configured DNS server.
 * Returns 0 on success, fills *ip_out. Blocks until reply or timeout. */
int dns_resolve(const char *hostname, uint32_t *ip_out);

/* Flush DNS cache. */
void dns_cache_flush(void);
```

### HTTP Client

```c
/* Perform an HTTP GET request.
 * Resolves hostname, connects via TCP, sends GET, receives response.
 * Returns 0 on success, fills response structure.
 * Caller must free response->body via kfree(). */
int http_get(const char *url, http_response_t *response);

/* Perform an HTTP POST request. */
int http_post(const char *url, const void *body, uint32_t body_len,
              const char *content_type, http_response_t *response);

/* Free HTTP response body memory. */
void http_response_free(http_response_t *response);

/* Parse a URL into components. */
int http_parse_url(const char *url, char *host, uint32_t host_size,
                   uint16_t *port, char *path, uint32_t path_size);
```

### Byte Order Utilities

```c
/* Network byte order (big-endian) conversion */
uint16_t htons(uint16_t host);     /* host to network short */
uint16_t ntohs(uint16_t net);      /* network to host short */
uint32_t htonl(uint32_t host);     /* host to network long */
uint32_t ntohl(uint32_t net);      /* network to host long */

/* IP address formatting */
void ip_to_str(uint32_t ip, char *buf, uint32_t bufsize);
uint32_t str_to_ip(const char *str);
```

## Behavior

### Packet Receive Pipeline

```
NIC driver receives frame
  -> net_rx_frame(dev_id, frame, len)
     -> Parse eth_header
     -> Switch ethertype:
        ETHERTYPE_ARP  -> arp_rx()
        ETHERTYPE_IPV4 -> ipv4_rx()
           -> Validate IP checksum
           -> Check dst_ip matches our config
           -> Switch protocol:
              IP_PROTO_ICMP -> icmp_rx()
              IP_PROTO_UDP  -> udp_rx()
                -> Find bound socket by dst_port
                -> Enqueue to socket rx queue
                -> Unblock recv waiter
              IP_PROTO_TCP  -> tcp_rx()
                -> Find connection by 4-tuple
                -> Process per TCP state machine
```

### TCP State Machine (Simplified)

```
CLOSED --[connect]-> SYN_SENT --[SYN+ACK]-> ESTABLISHED
CLOSED --[listen]-> LISTEN --[SYN]-> SYN_RECEIVED --[ACK]-> ESTABLISHED
ESTABLISHED --[close]-> FIN_WAIT_1 --[ACK]-> FIN_WAIT_2 --[FIN]-> TIME_WAIT -> CLOSED
ESTABLISHED --[recv FIN]-> CLOSE_WAIT --[close]-> LAST_ACK --[ACK]-> CLOSED
```

The TCP implementation is minimal:
- No fast retransmit or congestion control (simple timeout-based retransmit)
- Fixed window size (no sliding window scaling)
- Retransmission timeout: 1 second initial, doubles on each retry, max 3 retries
- No out-of-order segment handling (drop out-of-order segments)

### DHCP Client State Machine

```
INIT -> send DISCOVER -> SELECTING
  -> receive OFFER -> send REQUEST -> REQUESTING
  -> receive ACK -> configure interface -> BOUND
  -> receive NAK -> retry DISCOVER -> SELECTING

Timeout at any stage: retry (up to 3 times)
All 3 retries fail: FAILED (SLM notified)
```

### DNS Resolution Algorithm

```
dns_resolve("example.com"):
  1. Check DNS cache: if valid entry exists and TTL not expired, return cached IP
  2. Build DNS query:
     a. Header: random ID, QR=0 (query), RD=1 (recursion desired), QDCOUNT=1
     b. Question: encode "example.com" as DNS labels (3example3com0)
     c. Type=A, Class=IN
  3. Send UDP to dns_server:53
  4. Wait for response (timeout 5 seconds)
  5. Parse response:
     a. Verify ID matches
     b. Check RCODE == 0 (no error)
     c. Parse answer section: find first A record
     d. Extract 4-byte IPv4 address
  6. Add to DNS cache with TTL
  7. Return IP
  Timeout: retry once, then return -ETIMEOUT
```

### HTTP GET Algorithm

```
http_get("http://example.com/path/file.tar"):
  1. Parse URL: host="example.com", port=80, path="/path/file.tar"
  2. dns_resolve("example.com") -> ip
  3. tcp_connect(ip, 80, ephemeral_port)
  4. Send HTTP request:
     "GET /path/file.tar HTTP/1.0\r\n"
     "Host: example.com\r\n"
     "Connection: close\r\n"
     "\r\n"
  5. Receive response headers:
     a. Read line by line until "\r\n\r\n"
     b. Parse "HTTP/1.x STATUS STATUS_TEXT"
     c. Parse headers (Content-Length, Content-Type, etc.)
  6. Receive response body:
     a. If Content-Length known: read exactly that many bytes
     b. Else: read until connection closed
     c. Allocate body buffer via kmalloc
  7. tcp_close(conn)
  8. Return 0, fill http_response_t
```

### SLM Network Configuration

```
SLM INSTALL_CONFIGURE/NETWORK_CONFIG flow:
  1. SLM detects network device via dev framework
  2. SLM loads NIC driver (e1000, virtio-net)
  3. SLM initiates: net_register_device(dev_id)
  4. SLM initiates: dhcp_configure(dev_id)
  5. DHCP completes: SLM receives IP, mask, gateway, DNS
  6. SLM verifies: icmp_ping(gateway, ...) to confirm connectivity
  7. SLM tests DNS: dns_resolve("example.com") to confirm name resolution
  8. SLM reports: "Network configured: IP 192.168.1.100, GW 192.168.1.1"
```

### Edge Cases

- **No DHCP server responds**: 3 retries with increasing timeout (2s, 4s, 8s); then fail, SLM notified
- **DNS server unreachable**: dns_resolve returns -ETIMEOUT; SLM tries alternate DNS or reports error
- **ARP timeout**: arp_resolve returns -1 after 3 requests; IP send fails
- **TCP connection refused**: RST received in SYN_SENT state; tcp_connect returns -ECONNREFUSED
- **TCP connection timeout**: no SYN+ACK after 3 retransmissions; tcp_connect returns -ETIMEOUT
- **Packet too large**: fragment or return -EMSGSIZE (fragmentation not implemented in V1)
- **Checksum mismatch**: silently drop packet (IP or TCP/UDP checksum invalid)
- **Duplicate ARP replies**: update cache entry, no error
- **HTTP redirect (3xx)**: not followed in V1; return status code to caller
- **HTTP large response**: body > HTTP_MAX_BODY truncated; Content-Length checked first

## Files

| File | Purpose |
|------|---------|
| `kernel/net/net.c`        | Network stack core: init, rx dispatch, config |
| `kernel/net/arp.c`        | ARP cache and resolution |
| `kernel/net/ipv4.c`       | IPv4 layer: send, receive, routing, checksum |
| `kernel/net/icmp.c`       | ICMP echo request/reply (ping) |
| `kernel/net/udp.c`        | UDP send/receive |
| `kernel/net/tcp.c`        | TCP state machine, send, receive, retransmit |
| `kernel/net/socket.c`     | Socket API implementation |
| `kernel/net/dhcp.c`       | DHCP client |
| `kernel/net/dns.c`        | DNS resolver |
| `kernel/net/http.c`       | HTTP client (GET/POST) |
| `kernel/include/net.h`    | Network stack interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for packet buffers, HTTP response bodies, socket structures
- **drivers** (netdev): NIC send/receive frame functions
- **dev**: device IDs for network device registration
- **sched**: blocking operations (ARP resolve, TCP connect, DHCP, DNS)
- **ipc**: SLM triggers network configuration via IPC
- **slm**: SLM initiates DHCP, verifies connectivity

## Acceptance Criteria

1. ARP: resolve gateway IP returns correct MAC (verified with QEMU TAP bridge)
2. ARP: cache stores entries; second resolve for same IP returns immediately
3. IPv4: send packet to external host; visible in QEMU network capture (tcpdump/Wireshark)
4. IPv4: receive packet destined for our IP; delivered to correct protocol handler
5. ICMP: `icmp_ping(gateway_ip)` returns RTT; verified via QEMU virtual network
6. UDP: send/receive datagram between AUTON and host via QEMU user-mode networking
7. TCP: `tcp_connect()` completes three-way handshake (SYN, SYN+ACK, ACK)
8. TCP: send and receive data on established connection; data integrity verified
9. TCP: `tcp_close()` performs clean FIN handshake
10. TCP: retransmission works: drop first SYN in QEMU, verify retry succeeds
11. DHCP: `dhcp_configure()` obtains valid IP from QEMU built-in DHCP server
12. DHCP: subnet mask, gateway, and DNS are correctly extracted from DHCP ACK
13. DNS: `dns_resolve("example.com")` returns valid IP address
14. DNS: cache hit returns immediately on second query for same name
15. HTTP: `http_get("http://...")` downloads file, status 200, body matches expected content
16. Socket API: `sock_create()`, `sock_bind()`, `sock_sendto()`, `sock_recvfrom()` work for UDP
17. Byte order: `htons(0x1234) == 0x3412` on little-endian x86
18. Network configured by SLM: end-to-end DHCP + ping gateway passes
