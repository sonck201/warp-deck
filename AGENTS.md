# AGENTS.md

## What this is

`warp-deck` is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that installs, manages and toggles Cloudflare's 1.1.1.1 WARP VPN from SteamOS Game Mode. The repo is currently an unmodified fork of the official [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) — [main.py](main.py), [src/index.tsx](src/index.tsx) and [plugin.json](plugin.json) still contain template placeholder code.

Primary reference: **https://wiki.deckbrew.xyz/en/user-guide/home#plugin-development**

## Reference implementation: TunnelDeck

[steve228uk/TunnelDeck](https://github.com/steve228uk/TunnelDeck) solves nearly the same problem (VPN toggling in Game Mode on immutable SteamOS). Read it before designing anything here. Its layout maps 1:1 onto ours:

```
main.py                     Plugin class, async methods callable from the frontend
src/index.tsx               QAM panel (PanelSection / ToggleField / DropdownItem)
defaults/extensions/        bash install / uninstall scripts + a package URL list
plugin.json                 "flags": ["root"]  ← required, everything here needs root
```

### Patterns worth copying

**Backend = thin `subprocess` wrapper.** No dbus, no bindings. `Plugin` methods are plain `async def` shelling out and parsing stdout:

```python
subprocess.run(["nmcli", "connection", "show"], text=True, capture_output=True)
```

For WarpDeck the equivalent surface is `warp-cli status` / `connect` / `disconnect` / `registration new`, plus `systemctl {is-active,start} warp-svc`.

**Installing packages on a read-only rootfs.** SteamOS wipes `pacman` state on every update, so TunnelDeck never installs a package — it builds a **systemd-sysext** image and mounts it. [defaults/extensions/install](https://github.com/steve228uk/TunnelDeck/blob/main/defaults/extensions/install) in short:

1. `pacman -Qi <pkg>` → already installed manually? exit 0.
2. `wget -i ./openvpn.list` → download the `.pkg.tar.zst` from `steamdeck-packages.steamos.cloud`.
3. Extract it into a dir, write `usr/lib/extension-release.d/extension-release.<name>` containing `ID=steamos` + the current `VERSION_ID` from `/etc/os-release`.
4. `mksquashfs` the dir → symlink the `.raw` into `/var/lib/extensions/`.
5. `systemctl enable --now systemd-sysext`, `systemd-sysext refresh`, then `systemctl restart NetworkManager`.

The `VERSION_ID` check is the important part: a SteamOS update invalidates the extension-release file, so the image must be **rebuilt on mismatch**, not just mounted. Uninstall is `rm` the `.raw` + `systemd-sysext refresh`.

Note the deployment path: Decky copies [defaults/](defaults/) into the plugin's runtime dir, and the backend invokes the script by absolute path:

```python
subprocess.run(["bash", path.dirname(__file__) + "/extensions/install"],
               cwd=path.dirname(__file__) + "/extensions")
```

### Where WarpDeck will differ

- `cloudflare-warp` is **not** in the SteamOS/Arch `extra` mirror (it's AUR / Cloudflare's own repo), so step 2 above needs a different source. Resolve this before committing to the sysext approach.
- WARP runs its own daemon (`warp-svc`) and stores registration state — there is per-user state to persist and migrate, unlike TunnelDeck's stateless nmcli calls.

## Repo gotchas

- [docs/warpdeck_plugin_quickstart_guide.md](docs/warpdeck_plugin_quickstart_guide.md) uses the **old** frontend API (`definePlugin((serverApi: ServerAPI) => ...)`). The template in this repo is on `@decky/api` v1 (`callable`, `addEventListener`). Follow the template and the wiki, not that doc.
- Package manager is **yarn 4** (`packageManager: yarn@4.18.0` + `yarn.lock`, via Corepack). Decided; the pnpm config and the template's pnpm bootstrap are gone. The plugin-database CI is documented as expecting **pnpm v9**, so confirm it accepts a yarn-only repo before submitting.
- Custom-backend builds must output binaries to `backend/out/`; see the README.
