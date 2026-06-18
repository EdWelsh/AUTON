"""Kubernetes backend — drive a real cluster via ``kubectl`` from chat.

Natural language like "deploy app.yaml to the cluster", "what's running in k8s",
"scale web to 3", "delete deployment api", or "logs for pod nginx" is parsed into
a ``kubectl`` invocation and executed against whatever cluster ``kubectl`` is
currently pointed at.
"""
