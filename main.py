import json
import os
import shutil
import subprocess

try:
    import decky
except ImportError:  # not running under Decky Loader (e.g. the self-check below)
    decky = None

CLI = "warp-cli"
# --accept-tos on every call keeps warp-cli non-interactive.
BASE = [CLI, "--accept-tos"]

# Only tunnel-establishing modes. doh/dot proxy DNS without a tunnel, and proxy
# needs a SOCKS5 port nothing in Game Mode is configured to use -- offering them
# would let the panel report "connected" while no traffic is actually tunnelled.
MODES = {
    "warp": "WARP",
    "warp+doh": "WARP + DoH",
    "warp+dot": "WARP + DoT",
    "tunnel_only": "Tunnel only",
}

# `warp-cli settings` reports modes in a different vocabulary than `warp-cli
# mode` accepts, so the mapping is explicit rather than derived. Captured from
# the device by cycling every mode -- normalising the strings does not work.
SETTINGS_MODES = {
    "Warp": "warp",
    "WarpWithDnsOverHttps": "warp+doh",
    "WarpWithDnsOverTls": "warp+dot",
    "TunnelOnly": "tunnel_only",
}

TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"


def _clean_env(env: dict) -> dict:
    """Undo PyInstaller's LD_LIBRARY_PATH for child processes.

    Decky's PluginLoader is PyInstaller-packed: it repoints LD_LIBRARY_PATH at
    its bundled libs in /tmp/_MEI* and stashes the real value in *_ORIG. Any
    system binary we exec inherits that and loads Decky's older libcrypto --
    systemctl dies on `OPENSSL_3.4.0 not found` before writing to stdout.
    https://pyinstaller.org/en/stable/runtime-information.html
    """
    env = dict(env)
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = orig
    return env


_ENV = _clean_env(os.environ)


def _sh(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, env=_ENV)


def _warp(*args: str) -> subprocess.CompletedProcess:
    return _sh(*BASE, *args)


def _run(*args: str) -> str:
    """Run a warp-cli command; "" on success, else the error text."""
    p = _warp(*args)
    return "" if p.returncode == 0 else (p.stderr.strip() or p.stdout.strip() or "failed")


def _kv(text: str) -> dict:
    """Parse `Key: Value` and `key=value` lines into a dict.

    Covers all three warp-cli surfaces we read: `tunnel stats`, `settings`
    (whose lines carry a `(user set)\t` prefix) and the cdn-cgi/trace body.
    Splitting on ": " rather than ":" keeps colon-heavy values such as an IPv6
    address intact.
    """
    out = {}
    for line in text.splitlines():
        line = line.split("\t")[-1].strip()  # drop the "(source)\t" prefix
        for part in line.split(";"):  # "Sent: 586.3kB; Received: 2.6MB"
            part = part.strip()
            if ": " in part:
                key, _, value = part.partition(": ")
            elif "=" in part:
                key, _, value = part.partition("=")
            else:
                continue
            out[key.strip()] = value.strip()
    return out


def _head(value: str) -> str:
    """`MASQUE (HTTPS via UDP)` -> `MASQUE`; keeps the panel readable."""
    return value.split(" (")[0].strip()


def _version() -> str:
    """Plugin version from the package.json Decky deploys next to main.py."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "package.json")
        with open(path) as handle:
            return json.load(handle).get("version", "")
    except Exception:  # a missing/!json file must not kill the plugin at import
        return ""


VERSION = _version()


def _parse_status(stdout: str) -> tuple[str, bool]:
    """Turn `warp-cli status` output into (human text, connected)."""
    # ponytail: warp-cli has no --json, so the "Status update: <state>" line is
    # all we get. Swap this out if Cloudflare ships structured output.
    text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            text = line.removeprefix("Status update:").strip()
            break
    return text, text.lower().startswith("connected")


class Plugin:
    async def status(self) -> dict:
        # version first: it is the one field worth having even when every
        # other probe below fails, so it rides on every return path.
        state = {
            "version": VERSION,
            "installed": shutil.which(CLI) is not None,
            "daemon_running": False,
            "registered": False,
            "connected": False,
            "status_text": "",
            "mode": "",
            "always_on": False,
            "protocol": "",
            "latency": "",
            "loss": "",
            "colo": "",
            "sent": "",
            "received": "",
        }

        if not state["installed"]:
            return state

        # warp-cli is the authoritative liveness check: it has to reach warp-svc
        # over its socket to answer at all. Asking systemd instead gave a second,
        # weaker source of truth that disagreed with a demonstrably live daemon.
        p = _warp("status")
        state["daemon_running"] = p.returncode == 0
        if not state["daemon_running"]:
            state["status_text"] = p.stderr.strip() or p.stdout.strip()
            return state

        state["registered"] = _warp("registration", "show").returncode == 0
        state["status_text"], state["connected"] = _parse_status(p.stdout)

        settings = _kv(_warp("settings").stdout)
        state["mode"] = SETTINGS_MODES.get(settings.get("Mode", ""), "")
        state["always_on"] = settings.get("Always On", "").lower() == "true"

        if state["connected"]:
            # ponytail: four warp-cli spawns per 3s poll. Each is a local socket
            # round-trip, so it is cheap; batch or widen the interval if it ever
            # shows up in handheld battery numbers.
            stats = _kv(_warp("tunnel", "stats").stdout)
            state["protocol"] = _head(stats.get("Tunnel Protocol", ""))
            state["latency"] = stats.get("Estimated latency", "")
            state["loss"] = stats.get("Estimated loss", "")
            state["colo"] = _head(stats.get("Colo", ""))
            state["sent"] = stats.get("Sent", "")
            state["received"] = stats.get("Received", "")
        return state

    async def trace(self) -> dict:
        """Egress IP as the internet sees it. The only call that hits the network,
        so the frontend runs it on connect rather than on the status poll.

        Shelled out to curl rather than urllib because Decky's bundled OpenSSL
        breaks Python's own _ssl in this process ("unknown url type: https").
        Only a child process carrying the scrubbed _ENV can negotiate TLS.
        """
        try:
            p = _sh("curl", "-s", "--max-time", "5", TRACE_URL)
        except OSError as error:  # curl absent
            return {"ip": "", "loc": "", "error": str(error)}
        if p.returncode != 0:
            return {"ip": "", "loc": "", "error": p.stderr.strip() or "trace failed"}
        seen = _kv(p.stdout)
        return {"ip": seen.get("ip", ""), "loc": seen.get("loc", ""), "error": ""}

    async def set_mode(self, mode: str) -> str:
        # `mode` crosses from the frontend into an argv entry: only ever pass a
        # value we put in the dropdown ourselves.
        if mode not in MODES:
            return f"refusing unknown mode: {mode}"
        return _run("mode", mode)

    async def connect(self) -> str:
        return _run("connect")

    async def disconnect(self) -> str:
        return _run("disconnect")

    async def register(self) -> str:
        return _run("registration", "new")

    async def _main(self):
        decky.logger.info("WarpDeck loaded")

    async def _unload(self):
        decky.logger.info("WarpDeck unloaded")

    async def _uninstall(self):
        decky.logger.info("WarpDeck uninstalled")


if __name__ == "__main__":  # self-check: python3 main.py
    assert _parse_status("Status update: Connected\nSuccess\n") == ("Connected", True)
    assert _parse_status(
        "Status update: Disconnected. Reason: Manual Disconnection\n"
    ) == ("Disconnected. Reason: Manual Disconnection", False)
    assert _parse_status("") == ("", False)

    # Fixtures are verbatim output captured from warp-cli on a Bazzite handheld.
    stats = _kv(
        "Tunnel Protocol: MASQUE (HTTPS via UDP)\n"
        "Endpoints: 162.159.198.2, ::\n"
        "Sent: 586.3kB; Received: 2.6MB\n"
        "Estimated latency: 87ms\n"
        "Estimated loss: 0.01%\n"
        "TLS Handshake:\n"
        "\tVersion: TLSv1.3\n"
        "Colo: HKG (1176f37)\n"
    )
    assert stats["Estimated latency"] == "87ms"
    assert stats["Estimated loss"] == "0.01%"
    # one line packs two pairs
    assert stats["Sent"] == "586.3kB" and stats["Received"] == "2.6MB"
    assert _head(stats["Tunnel Protocol"]) == "MASQUE"
    assert _head(stats["Colo"]) == "HKG"
    # "TLS Handshake:" has no value and must not become a key
    assert "TLS Handshake" not in stats

    # settings carries a "(source)\t" prefix that changes once a value is set
    assert _kv("(default)\tMode: Warp")["Mode"] == "Warp"
    assert _kv("(user set)\tMode: WarpWithDnsOverHttps")["Mode"] == "WarpWithDnsOverHttps"
    assert _kv("(derived)\tAlways On: true")["Always On"] == "true"

    # the trace endpoint is key=value, and the IPv6 value is full of colons
    trace = _kv("ip=2a09:bac1:7aa0:10::498:25\nloc=VN\ncolo=HKG\nwarp=on\n")
    assert trace["ip"] == "2a09:bac1:7aa0:10::498:25"
    assert trace["loc"] == "VN"

    # settings and `warp-cli mode` use different vocabularies (verified on device)
    assert SETTINGS_MODES["WarpWithDnsOverHttps"] == "warp+doh"
    assert SETTINGS_MODES["TunnelOnly"] == "tunnel_only"
    assert set(SETTINGS_MODES.values()) == set(MODES)
    assert "LD_LIBRARY_PATH" not in _clean_env({"LD_LIBRARY_PATH": "/tmp/_MEI1"})
    assert "LD_LIBRARY_PATH_ORIG" not in _clean_env({"LD_LIBRARY_PATH_ORIG": "/usr/lib"})
    assert _clean_env(
        {"LD_LIBRARY_PATH": "/tmp/_MEI1", "LD_LIBRARY_PATH_ORIG": "/usr/lib64"}
    )["LD_LIBRARY_PATH"] == "/usr/lib64"
    print("ok")
