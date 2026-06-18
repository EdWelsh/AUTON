# Installing the AUTON Control Plane

Concrete, copy-pasteable steps to install the AUTON host chat control plane on
your machine and reach the same conversation from a **terminal**, a **web UI**,
or a **desktop app**. All three surfaces share one session at
`~/.auton/session.db`, so a chat started in the terminal continues in the
browser and the desktop window.

> Requires **Python ≥ 3.10**. All commands are run from the repository root
> (the directory that contains the `controlplane/` folder).

## TL;DR

```bash
# Isolated global install of the terminal CLI (recommended)
pipx install ./controlplane
auton-chat

# Or a development install (editable) with whichever surfaces you want
pip install -e controlplane                 # core + terminal (auton-chat)
pip install -e 'controlplane[ui]'           # + web UI       (auton-ui)
pip install -e 'controlplane[desktop]'      # + desktop app  (auton-desktop)
pip install -e 'controlplane[llm]'          # + free-form NL intent
```

The convenience wrapper [`scripts/install.sh`](scripts/install.sh) runs the
core install for you (see [One-line installer](#one-line-installer) below).

## 1. Terminal install (`auton-chat`)

The terminal surface is the smallest install — just the core package.

### Option A — `pipx` (recommended for a global CLI)

`pipx` installs the control plane into its own isolated virtualenv and puts the
`auton-chat` command on your `PATH`, without polluting your global site-packages.

```bash
pipx install ./controlplane
auton-chat
```

To add an optional surface or the LLM intent extra to a `pipx` install:

```bash
pipx install './controlplane[ui]'        # web UI as well
pipx install './controlplane[llm]'       # free-form NL intent
```

Upgrade or remove later with:

```bash
pipx upgrade auton-controlplane
pipx uninstall auton-controlplane
```

### Option B — `pip` (editable / development)

```bash
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e controlplane
auton-chat
```

`-e` (editable) means changes to the source under `controlplane/src/` take
effect without reinstalling — ideal while hacking on the control plane.

## 2. Web UI install (`auton-ui`)

The web surface adds a FastAPI + Uvicorn server (the `[ui]` extra) that serves
the same chat in a browser.

```bash
pip install -e 'controlplane[ui]'
auton-ui
```

Then open the URL it prints (a local FastAPI/Uvicorn server). The web session is
the **same** `~/.auton/session.db` the terminal uses.

`pipx` equivalent:

```bash
pipx install './controlplane[ui]'
auton-ui
```

## 3. Desktop app install (`auton-desktop`)

The desktop surface wraps the chat in a native window via `pywebview` (the
`[desktop]` extra).

```bash
pip install -e 'controlplane[desktop]'
auton-desktop
```

`pipx` equivalent:

```bash
pipx install './controlplane[desktop]'
auton-desktop
```

> `pywebview` uses your OS web view (WebKit on macOS, WebKitGTK on Linux,
> WebView2/Edge on Windows). On Linux you may need the GTK/WebKit2 system
> packages (e.g. `gir1.2-webkit2-4.1`) for the native window to open.

## 4. Free-form natural-language intent (`[llm]`)

By default the chat routes sentences to capabilities **deterministically** (no
network, no API key). Installing the `[llm]` extra adds an LLM-backed intent
extractor (via `litellm`) for free-form phrasing, with the deterministic router
as a fallback:

```bash
pip install -e 'controlplane[llm]'
```

Provide your provider key the usual way (e.g. `export ANTHROPIC_API_KEY=...` or
`export OPENAI_API_KEY=...`). With no key configured, the control plane stays on
the deterministic router.

## Combining extras

Extras compose — install several at once:

```bash
pip install -e 'controlplane[ui,desktop,llm]'
# or with pipx:
pipx install './controlplane[ui,desktop,llm]'
```

## The shared session: `~/.auton/session.db`

Every surface reads and writes one session database at `~/.auton/session.db`.
That is what makes the chat continuous across surfaces: start in `auton-chat`,
pick up in `auton-ui`, finish in `auton-desktop`. To reset your session, stop
all surfaces and remove the file:

```bash
rm ~/.auton/session.db
```

## One-line installer

For the core terminal install you can use the bundled wrapper:

```bash
./controlplane/scripts/install.sh           # core (auton-chat)
./controlplane/scripts/install.sh ui        # core + web UI
./controlplane/scripts/install.sh desktop   # core + desktop app
./controlplane/scripts/install.sh ui,desktop,llm
```

It prefers `pipx` when available and falls back to `pip install -e`.

## Verifying the install

```bash
pip show auton-controlplane                 # package metadata
auton-chat --help    || auton-chat          # terminal entrypoint exists
```

After a successful install the three console scripts are on your `PATH`:
`auton-chat`, `auton-ui`, `auton-desktop`.

## Uninstalling

```bash
pip uninstall auton-controlplane            # pip installs
pipx uninstall auton-controlplane           # pipx installs
```

See [README.md](README.md) for architecture, writing backends, and running the
test suite.
