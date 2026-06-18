"""Unified "what's running" status backend.

Aggregates a live snapshot across Docker, Kubernetes, and host server processes
by probing the real local CLIs (missing tools degrade gracefully). See
:mod:`controlplane.backends.status.aggregator`.
"""
