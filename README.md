# WarpDeck

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that toggles Cloudflare's [1.1.1.1 WARP](https://developers.cloudflare.com/warp-client/) VPN from the SteamOS Game Mode Quick Access Menu.

The plugin **does not install WARP** — it drives an existing `warp-cli` on the device. Install the client first: [docs/install-warp-on-bazzite.md](docs/install-warp-on-bazzite.md).

| | |
|---|---|
| Frontend | [src/index.tsx](src/index.tsx) — one QAM panel (`@decky/ui` + `@decky/api` v1) |
| Backend | [main.py](main.py) — `subprocess` wrapper around `warp-cli`, no dbus, no bindings |
| Manifest | [plugin.json](plugin.json) — `flags: ["debug", "root"]`; root is required |
| Deploy | [scripts/deploy.sh](scripts/deploy.sh) — build + rsync + restart `plugin_loader` |

## Backend API

Every method on `Plugin` is exposed to the frontend through `callable()`. Actions return `""` on success, or `warp-cli`'s error text.

| Method | Shells out to | Returns |
|---|---|---|
| `status()` | `warp-cli status`, `registration show`, `settings`, `tunnel stats` | full state dict (see `Status` in [src/index.tsx](src/index.tsx#L28)) |
| `trace()` | `curl https://www.cloudflare.com/cdn-cgi/trace` | `{ ip, loc, error }` — the only call that hits the network |
| `set_mode(mode)` | `warp-cli mode <mode>` | error text; rejects anything outside `MODES` |
| `connect()` / `disconnect()` | `warp-cli connect` / `disconnect` | error text |
| `register()` | `warp-cli registration new` | error text |

The panel polls `status()` every 3s while open, and fetches `trace()` only when the connection flips.

## Deployment

### Device prerequisites

1. Decky Loader installed and running (`systemctl status plugin_loader`).
2. Cloudflare WARP installed, `warp-svc` enabled — see [docs/install-warp-on-bazzite.md](docs/install-warp-on-bazzite.md). On Fedora atomic (Bazzite) this is an `rpm-ostree` layer and needs a reboot.
3. SSH reachable, with your key authorised: `ssh-copy-id -i ~/.ssh/id_ed25519.pub bazzite@<ip>`

### Deploy

```bash
DECK_HOST=192.168.1.42 DECK_USER=bazzite ./scripts/deploy.sh
```

| Variable | Default | Notes |
|---|---|---|
| `DECK_USER` | `bazzite` | `deck` on stock SteamOS |
| `DECK_HOST` | `192.168.1.100` | IP or hostname |
| `DECK_PORT` | `22` | |
| `PLUGIN_DIR` | `WarpDeck` | folder under `~/homebrew/plugins` |
| `DECK_KEY` | `~/.ssh/id_ed25519` | skipped if the file is absent |

The script runs `yarn install --immutable` + `yarn build`, wipes the old install (Decky owns it as root), rsyncs `dist main.py package.json plugin.json py_modules defaults README.md LICENSE`, chowns back to `root:root`, then restarts `plugin_loader`. It uses `ssh -t`, so sudo can prompt interactively.

Then: **QAM → Decky → WarpDeck**. A frontend-only change still needs a full redeploy — Decky serves `dist/index.js` from the device.

### Verifying and debugging on device

```bash
journalctl -u plugin_loader -f                 # loader + plugin stdout
sudo cat ~/homebrew/logs/WarpDeck/*.log        # decky.logger output
warp-cli --accept-tos status                   # is it the plugin or WARP?
```

If the panel says *"Cannot reach the WARP daemon"*, check `systemctl status warp-svc` before touching plugin code.

### The VSCode task path (template leftover)

[.vscode/tasks.json](.vscode/tasks.json) still carries the upstream template's `build` / `deploy` / `builddeploy` tasks. They were ported to yarn but still use the Decky CLI, Docker and a zip round-trip, and need a `.vscode/settings.json` copied from [.vscode/defsettings.json](.vscode/defsettings.json). Unused and unverified here — `scripts/deploy.sh` is the supported path.

### Release zip (CI)

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs `corepack enable` → `yarn install --immutable` → `yarn build` on every push and PR. On a published GitHub release it also stamps `package.json` with the tag, assembles `pkg/WarpDeck/` (hoisting `defaults/` contents into the plugin root), and uploads `WarpDeck-<tag>.zip` to the release. Tag as `vX.Y.Z` — the leading `v` is stripped for the version field.

*Currently untracked — `git add .github` to enable it.*

### Store distribution (not yet done)

Before submitting to [decky-plugin-database](https://github.com/SteamDeckHomebrew/decky-plugin-database):

- [ ] `plugin.json`: author is still `John Doe`; drop the `debug` flag; replace the placeholder `publish.image`; `tags` still say `template`.
- [ ] `package.json`: `repository`, `homepage`, `bugs` and `author` still point at the upstream template.
- [ ] Package manager: this repo is yarn-only (`yarn@4.18.0` + `yarn.lock`, no `pnpm-lock.yaml`). The database CI is documented as expecting **pnpm v9** — confirm it builds a yarn repo, or add a `pnpm-lock.yaml` for CI only.
- [ ] Keep the template's BSD-3-Clause block at the bottom of [LICENSE](LICENSE) under your own license.

## Maintenance

### Self-check

`main.py` has an `assert`-based self-check at the bottom, driven by `warp-cli` output captured verbatim from a real device:

```bash
python3 main.py   # prints "ok"
```

Run it after touching any parser. There is no frontend test suite.

### Things that must stay in sync

`main.py` and `src/index.tsx` both hold a `MODES` list, and `main.py` maps `warp-cli settings` vocabulary onto it via `SETTINGS_MODES`. The three are checked against each other by `assert set(SETTINGS_MODES.values()) == set(MODES)` — but **the frontend copy is not**, so update [src/index.tsx](src/index.tsx#L21) by hand when modes change.

Only tunnel-establishing modes are offered on purpose. `doh` / `dot` proxy DNS without a tunnel and `proxy` needs a SOCKS5 port nothing in Game Mode uses — offering them would let the panel read "connected" while no traffic is tunnelled.

### Version

Bump `version` in [package.json](package.json). The backend reads it back from the `package.json` Decky deploys next to `main.py` and the panel renders it in the footer, so a stale footer means a stale deploy.

### Two workarounds that look removable and are not

- **`_clean_env()`** — Decky's PluginLoader is PyInstaller-packed and repoints `LD_LIBRARY_PATH` at its bundled libs, stashing the real value in `LD_LIBRARY_PATH_ORIG`. Any system binary we exec inherits it and loads Decky's older libcrypto; `systemctl` then dies on `OPENSSL_3.4.0 not found` before writing to stdout. Every subprocess must carry `_ENV`.
- **`curl` in `trace()`** — the same bundled OpenSSL breaks Python's `_ssl` in this process (`unknown url type: https`). Only a child process with the scrubbed env can negotiate TLS, so `urllib` is not an option here.

### Dependencies

```bash
yarn install --immutable     # respect yarn.lock
yarn build                   # rollup -> dist/index.js
yarn watch                   # rebuild on change (still needs a redeploy)
yarn up @decky/ui @decky/api # when the frontend lib goes stale
```

Yarn 4.18.0 via Corepack (`corepack enable` once — the `packageManager` field in [package.json](package.json) pins the version), `nodeLinker: node-modules`. React is never installed: Steam injects it at runtime, and [.yarnrc.yml](.yarnrc.yml) marks the `react-icons` peer optional so installs stay warning-free. [decky.pyi](decky.pyi) is a local type stub for the `decky` module the loader injects — it is not shipped and not importable outside the loader (hence the `try/except ImportError`).

### Liveness checks are deliberately single-source

`warp-cli status` is the authoritative daemon check: it has to reach `warp-svc` over its socket to answer at all. Asking `systemctl` as well gave a second, weaker source of truth that disagreed with a demonstrably live daemon. Don't add it back.

## References

**Decky**
- [Plugin development wiki](https://wiki.deckbrew.xyz/en/user-guide/home#plugin-development) — primary reference
- [decky-loader](https://github.com/SteamDeckHomebrew/decky-loader) · [decky-plugin-database](https://github.com/SteamDeckHomebrew/decky-plugin-database)
- [@decky/ui (decky-frontend-lib)](https://github.com/SteamDeckHomebrew/decky-frontend-lib) — `PanelSection`, `ToggleField`, `DropdownItem`
- [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) — this repo's origin
- [Discord](https://deckbrew.xyz/discord)

**Cloudflare WARP**
- [WARP client docs](https://developers.cloudflare.com/warp-client/)
- [`warp-cli` reference](https://developers.cloudflare.com/cloudflare-one/team-and-resources/devices/warp/configure-warp/warp-cli/)
- [Linux package repo](https://pkg.cloudflareclient.com/)

**Prior art**
- [steve228uk/TunnelDeck](https://github.com/steve228uk/TunnelDeck) — same problem (VPN toggling in Game Mode on an immutable rootfs), nmcli instead of `warp-cli`, and the systemd-sysext trick for getting packages onto a read-only rootfs.

**In this repo**
- [AGENTS.md](AGENTS.md) — design context and the TunnelDeck comparison
- [docs/install-warp-on-bazzite.md](docs/install-warp-on-bazzite.md) — WARP install, `$releasever` gotcha
- [docs/warpdeck_plugin_quickstart_guide.md](docs/warpdeck_plugin_quickstart_guide.md) — **outdated**, see notes

## Notes

- **The quickstart doc is wrong.** [docs/warpdeck_plugin_quickstart_guide.md](docs/warpdeck_plugin_quickstart_guide.md) uses the old frontend API (`definePlugin((serverApi: ServerAPI) => ...)`). This repo is on `@decky/api` v1 (`callable`, `definePlugin(() => ...)`). Follow the code and the wiki, not that doc.

- **Installing WARP from Game Mode is unsolved.** `rpm-ostree install` needs a reboot, which is a dealbreaker. The no-daemon alternative is `wgcf` → generate a WireGuard profile → `nmcli connection import`, giving a plain NetworkManager connection to toggle exactly as TunnelDeck does. Cost: no WARP+ / Zero Trust, no mode switching. Worth settling before `main.py` commits harder to the `warp-cli` surface.

- **`cloudflare-warp` is not in the SteamOS/Arch `extra` mirror**, so TunnelDeck's sysext recipe (download `.pkg.tar.zst` → `mksquashfs` → `/var/lib/extensions/`) has no package source to point at. Resolve that before pursuing sysext.

- **`$releasever` has holes.** Cloudflare publishes no RPM path for Fedora 42; 9, 10, 43 and 44 exist. Hardcode a working `baseurl` if the repo file 404s.

- **Registration state lives on the device**, unlike TunnelDeck's stateless nmcli calls. Nothing migrates it today; a fresh `registration new` is the only path.

- **Polling costs four `warp-cli` spawns every 3s** while connected. Each is a local socket round-trip, so it is cheap — batch it or widen the interval if it ever shows up in handheld battery numbers.

- **Unused template files kept for now**: [backend/](backend/) (C hello-world + Dockerfile, for plugins with compiled backends — ours is pure Python) and [defaults/defaults.txt](defaults/defaults.txt). `defaults/` is still rsynced by the deploy script, so anything dropped there lands in the plugin root on device.

- **`warp-cli` has no `--json`.** Every parser in `main.py` is scraping human output, which is why the fixtures are verbatim device captures. If Cloudflare ever ships structured output, `_kv` / `_parse_status` should go.

## License

BSD-3-Clause — see [LICENSE](LICENSE).
