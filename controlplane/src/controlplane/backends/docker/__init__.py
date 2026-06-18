"""Docker backend (Unit 2).

Drives the real ``docker`` CLI from natural-language chat: run, list, stop,
logs, remove. The capability is WORKING — it shells out to ``docker`` via
subprocess. Utterance parsing is a pure function (``parse_command``) so it can
be unit-tested without docker installed.
"""
