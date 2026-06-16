/* In-kernel servers reachable over the network — the chat turns the machine
 * into these roles on request. */
#ifndef AUTON_SERVER_H
#define AUTON_SERVER_H

/* Listen on TCP :80 and serve a page until a key is pressed on the console.
 * Requires networking to be up (an IP assigned). */
void http_server_run(void);

#endif /* AUTON_SERVER_H */
