# Installing the Cloudflare WARP client on Bazzite

Target: a Bazzite handheld (e.g. Legion Go 2). Bazzite is Fedora atomic, so the
client gets **layered** with `rpm-ostree` and needs one reboot.

## Steps

```bash
# 1. add the repo (/etc is writable on atomic)
sudo curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo \
  -o /etc/yum.repos.d/cloudflare-warp.repo

# 2. layer it, then reboot into the new deployment
sudo rpm-ostree install cloudflare-warp
systemctl reboot

# 3. after reboot
sudo systemctl enable --now warp-svc
warp-cli --accept-tos registration new
warp-cli --accept-tos connect
warp-cli --accept-tos status
```

## `$releasever` gotcha

The repo file is:

```ini
[cloudflare-warp-stable]
name=cloudflare-warp-stable
baseurl=https://pkg.cloudflareclient.com/rpm/$releasever
enabled=1
type=rpm
gpgcheck=1
gpgkey=https://pkg.cloudflareclient.com/pubkey.gpg
```

Probed 2026-09-21 — which `$releasever` paths actually exist:

| releasever | `repodata/repomd.xml` |
|-----------|-----------------------|
| 8         | 404 |
| 9         | 200 |
| 10        | 200 |
| 41, 42    | 404 |
| 43        | 200 |
| 44        | 200 |
| 45        | 404 |

So **Fedora 42 is missing**. If step 2 404s, check `. /etc/os-release; echo $VERSION_ID`
and hardcode a working one in the repo file:

```ini
baseurl=https://pkg.cloudflareclient.com/rpm/43
```

Current package in `/rpm/44`: `cloudflare-warp-2026.7.1377.0`.

## Update behaviour

Layers are re-applied on each Bazzite rebase, so the install survives updates —
but a broken layer **blocks** updates. Back it out with:

```bash
sudo rpm-ostree uninstall cloudflare-warp
```

## Why this matters for WarpDeck

That reboot is a dealbreaker for installing WARP from Game Mode. The no-daemon
alternative is `wgcf` → generate a WireGuard profile → `nmcli connection import`,
giving a plain NetworkManager connection to toggle exactly like
[TunnelDeck](https://github.com/steve228uk/TunnelDeck) does — no layering, no
systemd-sysext, no `warp-svc`, no `VERSION_ID` rebuild dance.

Cost: no WARP+ / Zero Trust, no `warp-cli` mode switching.

Worth settling before [main.py](../main.py) commits harder to the `warp-cli` surface.
