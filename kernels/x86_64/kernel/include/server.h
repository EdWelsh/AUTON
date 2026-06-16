/* In-kernel servers reachable over the network — the chat turns the machine
 * into these roles on request. */
#ifndef AUTON_SERVER_H
#define AUTON_SERVER_H

/* Poll the network, servicing connections, until a key is pressed on the
 * console. Shared by every in-kernel server role. */
void server_serve_loop(void);

/* Listen on TCP :80 and serve an AUTON page. Requires an assigned IP. */
void http_server_run(void);

/* Answer DNS A queries on UDP :53 with this host's IP. Requires an IP. */
void dns_server_run(void);

#endif /* AUTON_SERVER_H */
