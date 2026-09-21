# WarpDeck - Decky Loader Plugin Development Guide

`WarpDeck` is a Decky Loader plugin designed to install, configure, and manage Cloudflare's 1.1.1.1 WARP VPN directly from SteamOS Game Mode.

---

## 🛠 Project Structure

```text
warp-deck/
├── src/                  # React Frontend (Steam Deck QAM UI)
│   ├── index.tsx         # Main UI component entry point
│   └── components/       # UI sub-components (Status, Controls, Logs)
├── main.py               # Python Backend (System commands, warp-cli control)
├── package.json          # Plugin Metadata & Dependencies
├── plugin.json           # Decky Loader Plugin Manifest
├── tsconfig.json         # TypeScript configuration
├── rollup.config.js      # Frontend Bundler configuration
└── README_DEV.md         # Local Setup & Dev Instructions
```

---

## 📋 Prerequisites & Tools

### On Your Development PC:
- **Node.js**: v18+ with Corepack enabled (`corepack enable`) for `yarn` 4
- **IDE**: VS Code (recommended) or any modern editor
- **Git**
- **SSH Client**: To connect to your Steam Deck over local network

### On Your Steam Deck:
- **Developer Mode**: Enabled (`Settings > System > Enable Developer Mode`)
- **Decky Loader**: Installed (`release` or `prerelease`)
- **SSH Enabled**:
  ```bash
  sudo systemctl enable --now sshd
  ```
- **Deck Password**: Set via `passwd` in Desktop Mode terminal.

---

## 🚀 Quickstart: Local Setup

### 1. Initialize Project Structure

Generate your initial template using the official Decky template or clone your repo:

```bash
# Clone the Decky Plugin Template
git clone https://github.com/SteamDeckHomebrew/decky-plugin-template warp-deck
cd warp-deck

# Install frontend dependencies
npm install
```

### 2. Configure `package.json`

Ensure your package fields match the required Decky spec:

```json
{
  "name": "warp-deck",
  "label": "WarpDeck",
  "version": "0.1.0",
  "description": "Install, manage, and toggle Cloudflare 1.1.1.1 WARP VPN in SteamOS.",
  "author": "YourName",
  "scripts": {
    "build": "rollup -c",
    "watch": "rollup -c -w"
  }
}
```

---

## 💻 Code Architecture Setup

### Python Backend (`main.py`)
This file executes `warp-cli` root commands and returns status back to the frontend.

```python
import subprocess
import logging

logging.basicConfig(level=logging.INFO)

class Plugin:
    async def get_warp_status(self):
        """Checks if warp-cli is installed and its connection state."""
        try:
            result = subprocess.run(["warp-cli", "status"], capture_output=True, text=True)
            return {"success": True, "output": result.stdout.strip()}
        except FileNotFoundError:
            return {"success": False, "error": "warp-cli not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def connect_warp(self):
        """Connects to WARP VPN."""
        try:
            result = subprocess.run(["warp-cli", "connect"], capture_output=True, text=True)
            return {"success": True, "output": result.stdout.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def disconnect_warp(self):
        """Disconnects from WARP VPN."""
        try:
            result = subprocess.run(["warp-cli", "disconnect"], capture_output=True, text=True)
            return {"success": True, "output": result.stdout.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _main(self):
        logging.info("WarpDeck plugin initialized backend")

    async def _unload(self):
        logging.info("WarpDeck plugin unloaded")
```

### React Frontend (`src/index.tsx`)
This creates the user interface inside the Steam Deck Quick Access Menu (QAM).

```tsx
import {
  definePlugin,
  ServerAPI,
  staticClasses,
  ToggleField,
  PanelSection,
  PanelSectionRow,
  ButtonItem,
} from "decky-frontend-lib";
import { useState, useEffect, VFC } from "react";
import { FaShieldAlt } from "react-icons/fa";

const Content: VFC<{ serverApi: ServerAPI }> = ({ serverApi }) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusText, setStatusText] = useState<string>("Checking status...");

  const fetchStatus = async () => {
    setLoading(true);
    const res = await serverApi.callPluginMethod("get_warp_status", {});
    if (res.success && res.result?.success) {
      const output = res.result.output;
      setStatusText(output);
      setIsConnected(output.includes("Connected"));
    } else {
      setStatusText(res.result?.error || "Error checking status");
      setIsConnected(false);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const toggleWarp = async (enable: boolean) => {
    setLoading(true);
    const method = enable ? "connect_warp" : "disconnect_warp";
    await serverApi.callPluginMethod(method, {});
    await fetchStatus();
  };

  return (
    <PanelSection title="1.1.1.1 WARP Status">
      <PanelSectionRow>
        <ToggleField
          label="Enable WARP VPN"
          description={statusText}
          checked={isConnected}
          disabled={loading}
          onChange={(checked) => toggleWarp(checked)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={fetchStatus} disabled={loading}>
          Refresh Status
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};

export default definePlugin((serverApi: ServerAPI) => {
  return {
    title: <div className={staticClasses.Title}>WarpDeck</div>,
    icon: <FaShieldAlt />,
    content: <Content serverApi={serverApi} />,
    onDismount() {},
  };
});
```

---

## 🔄 Deployment to Steam Deck

To build and deploy the plugin onto your physical Steam Deck over SSH:

### 1. Build local frontend artifacts
```bash
npm run build
```

### 2. Copy files to your Steam Deck
Replace `deck@steamdeck.local` with your Deck's IP address if needed:

```bash
# Create target directory on Deck
ssh deck@steamdeck.local "mkdir -p ~/homebrew/plugins/warp-deck"

# Copy plugin bundle and backend
scp -r dist main.py package.json plugin.json deck@steamdeck.local:~/homebrew/plugins/warp-deck/
```

### 3. Restart Plugin Loader
On your Steam Deck:
- Press `QAM Button (...)` > `Decky Settings` > `Developer` > `Reload Plugins`

---

## 🧪 Testing Checklist & Tips

1. **WARP Binary Dependency**: Ensure `cloudflare-warp` is installed on SteamOS.
   - Standard path: `/usr/bin/warp-cli`
   - Test terminal connection manually: `warp-cli registration new` then `warp-cli connect`.
2. **Permissions**: If `warp-cli` requires elevated privileges, configure `polkit` rules or manage permissions through systemd services.
3. **Debug Logs**: View backend logs directly on the Deck via SSH:
   ```bash
   journalctl -u plugin_loader -f
   ```
