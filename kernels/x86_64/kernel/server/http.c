/* Tiny HTTP/1.0 server. Any request gets one static page identifying AUTON.
 * The OS becomes a web server on the chat command "be a web server". */
#include "server.h"
#include "net.h"
#include "kernel.h"

static const char HTTP_RESPONSE[] =
	"HTTP/1.0 200 OK\r\n"
	"Content-Type: text/html\r\n"
	"Connection: close\r\n"
	"\r\n"
	"<!doctype html><html><head><title>AUTON</title></head><body>"
	"<h1>AUTON</h1>"
	"<p>You are talking to AUTON &mdash; an on-device chat OS. This page is "
	"served straight from the kernel by an in-kernel TCP/IP stack and HTTP "
	"server, with no userspace and no terminal setup.</p>"
	"</body></html>\r\n";

static void http_on_data(const uint8_t *data, uint16_t len)
{
	(void)data;
	(void)len;
	/* One static response regardless of method/path (MVP). */
	tcp_send(HTTP_RESPONSE, (uint16_t)(sizeof(HTTP_RESPONSE) - 1));
	tcp_close();
}

void http_server_run(void)
{
	tcp_listen(80, http_on_data);
	kprintf("[HTTP] listening on :80 (press any key to stop)\n");
	server_serve_loop();
	kprintf("[HTTP] stopped\n");
}
