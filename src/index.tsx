import {
  ButtonItem,
  DropdownItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  SingleDropdownOption,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin } from "@decky/api";
import { useEffect, useState } from "react";
import { FaCloud } from "react-icons/fa";

const HELP_URL = "https://developers.cloudflare.com/warp-client/";

// Tunnel-establishing modes only, mirroring MODES in main.py. doh/dot proxy DNS
// without a tunnel, so offering them would let the toggle read "connected"
// while nothing is actually tunnelled.
const MODES: SingleDropdownOption[] = [
  { data: "warp", label: "WARP" },
  { data: "warp+doh", label: "WARP + DoH" },
  { data: "warp+dot", label: "WARP + DoT" },
  { data: "tunnel_only", label: "Tunnel only" },
];

type Status = {
  version: string;
  installed: boolean;
  daemon_running: boolean;
  registered: boolean;
  connected: boolean;
  status_text: string;
  mode: string;
  always_on: boolean;
  protocol: string;
  latency: string;
  loss: string;
  colo: string;
  sent: string;
  received: string;
};

type Trace = { ip: string; loc: string; error: string };

// Each action resolves to "" on success, or warp-cli's error text.
const getStatus = callable<[], Status>("status");
const getTrace = callable<[], Trace>("trace");
const connect = callable<[], string>("connect");
const disconnect = callable<[], string>("disconnect");
const register = callable<[], string>("register");
const setMode = callable<[string], string>("set_mode");

function Content() {
  const [status, setStatus] = useState<Status | undefined>();
  const [trace, setTrace] = useState<Trace | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      setStatus(await getStatus());
    } catch (e) {
      console.error(e);
    }
  };

  const refreshTrace = async () => {
    try {
      setTrace(await getTrace());
    } catch (e) {
      console.error(e);
    }
  };

  const run = async (action: () => Promise<string>) => {
    setBusy(true);
    try {
      setError(await action());
    } catch (e) {
      console.error(e);
      setError(String(e));
    }
    await refresh();
    setBusy(false);
  };

  useEffect(() => {
    refresh();
    // warp-cli returns before the daemon settles (Connecting -> Connected), and
    // WARP can also be toggled outside the plugin, so poll while the panel is
    // open. Only local warp-cli calls ride this loop; the trace below does not.
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, []);

  const connected = status?.connected ?? false;
  useEffect(() => {
    // The egress IP is the one value behind a network round-trip, so it is
    // fetched when the connection flips rather than every 3 seconds.
    if (connected) refreshTrace();
    else setTrace(undefined);
  }, [connected]);

  const detail = (label: string, value: string) =>
    value ? (
      <PanelSectionRow>
        <Field label={label} bottomSeparator="none">
          {value}
        </Field>
      </PanelSectionRow>
    ) : null;

  return (
    <>
      <PanelSection title="Connection">
        {status && !status.installed && (
          <PanelSectionRow>Cloudflare WARP is not installed</PanelSectionRow>
        )}

        {status && status.installed && !status.daemon_running && (
          <PanelSectionRow>
            {status.status_text || "Cannot reach the WARP daemon"}
          </PanelSectionRow>
        )}

        {status && status.daemon_running && !status.registered && (
          <PanelSectionRow>Device not registered</PanelSectionRow>
        )}

        {status && status.daemon_running && status.registered && (
          <PanelSectionRow>
            <ToggleField
              bottomSeparator="standard"
              checked={status.connected}
              label="WARP"
              description={status.status_text}
              disabled={busy}
              onChange={(switchValue: boolean) =>
                run(switchValue ? connect : disconnect)
              }
            />
          </PanelSectionRow>
        )}

        {error && <PanelSectionRow>{error}</PanelSectionRow>}
      </PanelSection>

      {status && status.connected && (
        <PanelSection title="Details">
          {detail("Latency", status.latency)}
          {detail("Loss", status.loss)}
          {detail("Colo", status.colo)}
          {detail("Protocol", status.protocol)}
          {detail("Sent", status.sent)}
          {detail("Received", status.received)}

          {/* IPv6 is too long to sit beside a label, so it gets its own row. */}
          <PanelSectionRow>
            <Field
              label={trace?.loc ? `IP (${trace.loc})` : "IP"}
              childrenLayout="below"
              bottomSeparator="none"
            >
              {trace ? trace.error || trace.ip || "unavailable" : "checking..."}
            </Field>
          </PanelSectionRow>

          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={refreshTrace}>
              Refresh IP
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}

      <PanelSection title="Settings">
        {status && status.daemon_running && status.registered && (
          <PanelSectionRow>
            <DropdownItem
              label="Mode"
              rgOptions={MODES}
              selectedOption={status.mode}
              strDefaultLabel={status.mode ? undefined : "Unknown"}
              disabled={busy}
              onChange={(option: SingleDropdownOption) =>
                run(() => setMode(option.data as string))
              }
            />
          </PanelSectionRow>
        )}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || !status || !status.daemon_running || status.registered}
            onClick={() => run(register)}
          >
            Register Device
          </ButtonItem>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              Navigation.NavigateToExternalWeb(HELP_URL);
              Navigation.CloseSideMenus();
            }}
          >
            Setup Guide
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      {status?.version && (
        <div
          style={{
            borderTop: "1px solid rgba(255, 255, 255, 0.15)",
            margin: "8px 16px 0",
            paddingTop: "6px",
            fontSize: "0.7em",
            textAlign: "center",
            opacity: 0.5,
          }}
        >
          v{status.version}
        </div>
      )}
    </>
  );
}

export default definePlugin(() => ({
  name: "WarpDeck",
  titleView: <div className={staticClasses.Title}>WarpDeck</div>,
  content: <Content />,
  icon: <FaCloud />,
}));
