/* Capability/role control plane: the chat's single entry point for turning the
 * machine into a server role. Working roles run on the in-kernel stack; the
 * rest report honest "roadmap" status so the chat already speaks to every role
 * and gains real behavior as subsystems are built. */
#ifndef AUTON_ROLES_H
#define AUTON_ROLES_H

#include <stdint.h>

/* If 'text' is a role command (or a "what can you do" listing), handle it —
 * running the role or printing its status — and return 1. Otherwise return 0. */
int roles_dispatch(const char *text);

#endif /* AUTON_ROLES_H */
