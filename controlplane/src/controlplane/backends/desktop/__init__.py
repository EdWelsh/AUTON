"""Cross-platform desktop application backend.

Launch, close, and list desktop apps from natural language on macOS, Linux, and
Windows. The adapter is chosen from ``sys.platform`` at runtime; apps launched in
this session are tracked so "what apps are open" can report them.
"""
