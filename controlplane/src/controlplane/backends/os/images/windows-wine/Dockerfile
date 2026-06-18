# AUTON "Windows-style" OS: a noVNC Linux desktop with Wine, so .exe apps run
# in the browser. Builds on any arch; running x86 .exe on ARM additionally needs
# box64/hangover (slow). For REAL Windows use ../windows-dockur/compose.yml on a
# KVM host.
FROM lscr.io/linuxserver/webtop:ubuntu-mate

# Wine + winetricks. On amd64 this runs Windows apps directly; on arm64 it
# installs but needs an x86 translation layer to execute x86 binaries.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        wine64 winetricks cabextract \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

LABEL auton.os="windows-style" \
      auton.runs="Windows .exe via Wine" \
      auton.note="real Windows: see windows-dockur/compose.yml (needs KVM)"

# webtop already exposes the KasmVNC web desktop on 3000.
EXPOSE 3000
