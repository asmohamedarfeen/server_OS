"use client";
import { ReactNode, useEffect, useRef, useState } from "react";
import { Power, RotateCw, Server } from "lucide-react";
import { api, bytes, duration } from "@/lib/api";
import TerminalPanel from "./terminal-panel";
import {
  ActivityList,
  ConfirmDialog,
  dateTime,
  EmptyState,
  ErrorNotice,
  itemsOf,
  Loading,
  MetricHistory,
  Notify,
  PortalRoute,
  Properties,
  Refresh,
  ResourceWorkspace,
  Status,
  useResource,
} from "./portal-shared";

type Operation = {
  id: string;
  action: string;
  service?: string;
  status: string;
  message: string;
  created_at: string;
  updated_at: string;
};
type Confirmation = { action: "reboot" | "restart"; service?: string; impact?: string };
const activeStates = new Set(["requested", "queued", "dispatched", "reconnecting"]);
const percent = (n?: number | null) => (n == null ? "Unavailable" : `${n.toFixed(1)}%`);
const rate = (n?: number | null) => (n == null ? "Unavailable" : `${bytes(n)}/s`);
function Table({ headings, rows, empty }: { headings: string[]; rows: ReactNode[][]; empty: string }) {
  return (
    <div className="az-table-wrap">
      <table className="az-table">
        <thead>
          <tr>
            {headings.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <EmptyState title={empty} />}
    </div>
  );
}
export function PortalServer({ route, notify }: { route: PortalRoute; notify: Notify }) {
  const overview = useResource("/control/overview", 10000);
  const operations = useResource<{ items: Operation[] }>("/control/operations", 4000);
  const section = useResource(
    ["processes", "disks", "networking", "services"].includes(route.tab)
      ? `/control/${route.tab === "networking" ? "network" : route.tab}`
      : null,
    10000,
  );
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [hostname, setHostname] = useState("");
  const [impact, setImpact] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [posting, setPosting] = useState(false);
  const priorOperations = useRef("");
  const host = overview.data;
  const operationItems = itemsOf(operations.data) as Operation[];
  const active = operationItems.find((op) => activeStates.has(op.status));
  const unavailableReason = host?.capabilities?.reason || "Host control is unavailable";
  const canReboot = Boolean(host?.capabilities?.reboot && host?.hostname);
  const refreshAll = () => {
    overview.refresh();
    section.refresh();
    operations.refresh();
  };
  useEffect(() => {
    const reconnect = () => {
      overview.refresh();
      operations.refresh();
      section.refresh();
    };
    window.addEventListener("online", reconnect);
    window.addEventListener("focus", reconnect);
    return () => {
      window.removeEventListener("online", reconnect);
      window.removeEventListener("focus", reconnect);
    };
  }, [overview.refresh, operations.refresh, section.refresh]);
  useEffect(() => {
    if (!operations.data) return;
    const signature = operations.data.items.map((op) => `${op.id}:${op.status}`).join("|");
    if (priorOperations.current && priorOperations.current !== signature) {
      overview.refresh();
      section.refresh();
    }
    priorOperations.current = signature;
  }, [operations.data, overview.refresh, section.refresh]);
  function openConfirmation(value: Confirmation) {
    setConfirmation(value);
    setHostname("");
    setImpact(false);
    setSubmitError("");
  }
  async function submit() {
    if (!confirmation || posting) return;
    if (active || operations.loading || operations.error || overview.error) {
      setSubmitError(
        "Wait for the current host operation or reconnect and refresh operation status before submitting.",
      );
      return;
    }
    if (!host?.hostname || hostname !== host.hostname) {
      setSubmitError("Enter the exact managed hostname shown below.");
      return;
    }
    if (!impact) {
      setSubmitError("Confirm the application and dashboard connectivity impact.");
      return;
    }
    setPosting(true);
    setSubmitError("");
    try {
      const result = await api<Operation>(
        confirmation.action === "reboot"
          ? "/control/reboot"
          : `/control/services/${encodeURIComponent(confirmation.service!)}/restart`,
        { method: "POST", body: JSON.stringify({ hostname, confirm_impact: true }) },
      );
      notify(`Host operation recorded: ${result.status.replaceAll("_", " ")}.`);
      setConfirmation(null);
    } catch (e) {
      setSubmitError(
        `${e instanceof Error ? e.message : "Request failed"}. Check the operation list before retrying; a disconnected request may already have been accepted.`,
      );
    } finally {
      setPosting(false);
      operations.refresh();
    }
  }
  const operationHistory = (
    <section>
      <div className="az-section-heading">
        <h2>Host operations</h2>
        <span>Recorded by the host action queue</span>
      </div>
      <ErrorNotice
        error={
          operations.error
            ? `${operations.error}. Reconnecting automatically; the last recorded state remains visible.`
            : ""
        }
        retry={operations.refresh}
      />
      {operations.loading ? (
        <Loading />
      ) : (
        <Table
          headings={["Operation", "Status", "Details", "Requested", "Last updated"]}
          empty="No host operations recorded"
          rows={operationItems.slice(0, 10).map((op) => [
            <strong key="name">
              {op.action === "reboot" ? "Reboot server" : `Restart ${op.service}`}
              <small>{op.id}</small>
            </strong>,
            <Status key="status" value={op.status} />,
            op.message,
            dateTime(op.created_at),
            dateTime(op.updated_at),
          ])}
        />
      )}
      <p className="az-muted">
        A request or HTTP response does not confirm a reboot. Success requires the backend to observe a
        changed host boot ID. An unknown outcome requires inspection.
      </p>
    </section>
  );
  let content: ReactNode;
  if (route.tab === "metrics") content = <MetricHistory />;
  else if (route.tab === "terminal") content = <TerminalPanel target={null} />;
  else if (route.tab === "activity-log") content = <ActivityList resourceId="server" />;
  else if (["processes", "disks", "networking", "services"].includes(route.tab)) {
    const data = section.data;
    content = (
      <>
        <div className="az-section-heading">
          <h2>
            {route.tab === "networking" ? "Networking" : route.tab[0].toUpperCase() + route.tab.slice(1)}
          </h2>
          <span>
            {route.tab === "services" ? "Allowlisted platform services" : "Read-only host inspection"}
          </span>
        </div>
        <ErrorNotice error={section.error} retry={section.refresh} />
        {section.loading ? (
          <Loading />
        ) : (
          <>
            {data?.available === false && (
              <div className="az-notice">
                {data.reason || "Host inspection is unavailable. No host data can be confirmed."}
              </div>
            )}
            {route.tab === "processes" && (
              <Table
                headings={["PID", "Name", "State", "Resident memory"]}
                empty="No process information available"
                rows={itemsOf(data).map((p) => [p.pid, p.name, p.state, bytes(p.memory_bytes)])}
              />
            )}
            {route.tab === "disks" && (
              <Table
                headings={["Device", "Mount point", "File system", "Capacity", "Used", "Free", "Usage"]}
                empty="No disk information available"
                rows={itemsOf(data).map((d) => [
                  d.device,
                  d.mountpoint,
                  d.filesystem,
                  bytes(d.total),
                  bytes(d.used),
                  bytes(d.free),
                  percent(d.percent),
                ])}
              />
            )}
            {route.tab === "networking" && (
              <>
                {data?.address_reason && <p className="az-muted">{data.address_reason}</p>}
                <Table
                  headings={["Interface", "State", "Addresses", "MAC address", "Received", "Sent"]}
                  empty="No network interfaces available"
                  rows={itemsOf(data).map((n) => [
                    n.name,
                    n.state || "Unknown",
                    n.addresses?.length ? n.addresses.join(", ") : "Not reported",
                    n.mac || "—",
                    bytes(n.rx_bytes),
                    bytes(n.tx_bytes),
                  ])}
                />
                <div className="az-section-heading">
                  <h2>Listening ports</h2>
                  <span>Host TCP listeners and UDP sockets</span>
                </div>
                <Table
                  headings={["Protocol", "Address", "Port"]}
                  empty="No listening-port information available"
                  rows={(data?.listening_ports || []).map((p: any) => [p.protocol, p.address, p.port])}
                />
              </>
            )}
            {route.tab === "services" && (
              <>
                <Table
                  headings={["Service", "Status", "Enabled state", "Impact", "Action"]}
                  empty="No service information available"
                  rows={itemsOf(data).map((s) => [
                    s.name,
                    <Status key="state" value={s.status} />,
                    s.enabled || "Unknown",
                    s.impact,
                    <button
                      key="restart"
                      disabled={
                        !s.can_restart ||
                        !host?.hostname ||
                        Boolean(overview.error) ||
                        Boolean(active) ||
                        posting ||
                        Boolean(operations.error) ||
                        operations.loading
                      }
                      title={
                        !s.can_restart
                          ? data?.reason || unavailableReason
                          : active
                            ? "Another host operation is active"
                            : "Confirm connectivity impact before restarting"
                      }
                      onClick={() =>
                        openConfirmation({ action: "restart", service: s.name, impact: s.impact })
                      }
                    >
                      <RotateCw size={14} />
                      Restart
                    </button>,
                  ])}
                />
                {operationHistory}
              </>
            )}
          </>
        )}
      </>
    );
  } else
    content = (
      <>
        <div className="az-section-heading">
          <h2>Essentials</h2>
          <span>Managed Ubuntu host</span>
        </div>
        {overview.loading ? (
          <Loading />
        ) : (
          <>
            {host?.host_available === false && (
              <div className="az-notice">
                The host mount is unavailable. Host identity and metrics cannot be confirmed.
              </div>
            )}
            {host?.sample_error && <div className="az-notice">{host.sample_error}</div>}
            <Properties
              rows={[
                ["Hostname", host?.hostname || "Unavailable"],
                ["Operating system", host?.platform || "Unavailable"],
                ["Kernel", host?.kernel || "Unavailable"],
                ["Identity source", host?.identity_source || "Unavailable"],
                [
                  "Host inspection",
                  <Status key="host" value={host?.host_available ? "available" : "unavailable"} />,
                ],
                [
                  "Docker",
                  <Status key="docker" value={host?.docker?.available ? "available" : "unavailable"} />,
                ],
                ["Docker version", host?.docker?.version || "Unavailable"],
                ["Uptime", host?.uptime_seconds == null ? "Unavailable" : duration(host.uptime_seconds)],
                ["CPU cores", host?.cpu_count ?? "Unavailable"],
                ["CPU usage", percent(host?.cpu_percent)],
                [
                  "Load average (1 / 5 / 15 min)",
                  host?.load_average?.length ? host.load_average.join(" / ") : "Unavailable",
                ],
                [
                  "Memory usage",
                  host?.memory
                    ? `${bytes(host.memory.used)} / ${bytes(host.memory.total)} (${percent(host.memory.percent)})`
                    : "Unavailable",
                ],
                [
                  "Host root disk",
                  host?.disk
                    ? `${bytes(host.disk.used)} / ${bytes(host.disk.total)} (${percent(host.disk.percent)})`
                    : "Unavailable",
                ],
                ["Network received", rate(host?.network?.rx_bytes_sec)],
                ["Network sent", rate(host?.network?.tx_bytes_sec)],
                ["Process count", host?.process_count ?? "Unavailable"],
                ["Sample timestamp", dateTime(host?.timestamp)],
                ["Host control", host?.capabilities?.reboot ? "Available" : unavailableReason],
              ]}
            />
            <div className="az-section-heading">
              <h2>Applications on this server</h2>
              <span>Host interruption affects this server's workloads</span>
            </div>
            <Table
              headings={["Application", "State"]}
              empty="No applications recorded"
              rows={(host?.affected_apps || []).map((app: any) => [
                app.name,
                <Status key="status" value={app.status} />,
              ])}
            />
          </>
        )}
        {operationHistory}
      </>
    );
  return (
    <ResourceWorkspace
      title={host?.hostname || "Managed server"}
      type="Server"
      tabs={[
        "Overview",
        "Metrics",
        "Processes",
        "Disks",
        "Networking",
        "Services",
        "Terminal",
        "Activity log",
      ]}
      route={route}
      icon={<Server size={24} />}
      status={
        overview.error
          ? "unreachable"
          : host
            ? host.host_available
              ? "available"
              : "unavailable"
            : undefined
      }
      commands={
        <>
          <button
            disabled={
              !canReboot ||
              Boolean(active) ||
              posting ||
              Boolean(overview.error) ||
              Boolean(operations.error) ||
              operations.loading
            }
            title={
              !canReboot
                ? unavailableReason
                : active
                  ? "Another host operation is active"
                  : "Reboot interrupts applications and dashboard access"
            }
            onClick={() => openConfirmation({ action: "reboot" })}
          >
            <Power size={15} />
            Reboot server
          </button>
          <Refresh onClick={refreshAll} />
        </>
      }
    >
      <ErrorNotice error={overview.error} retry={overview.refresh} />
      {active && (
        <div className="az-notice" role="status">
          <Status value={active.status} />
          <span>
            {active.action === "reboot" ? "Server reboot" : `${active.service} restart`}: {active.message}{" "}
            Connectivity may be interrupted. Status polling resumes automatically when the dashboard is
            reachable.
          </span>
        </div>
      )}
      {content}
      {confirmation && (
        <ConfirmDialog
          title={confirmation.action === "reboot" ? "Reboot server" : `Restart ${confirmation.service}`}
          confirmLabel={confirmation.action === "reboot" ? "Request reboot" : "Request restart"}
          onConfirm={submit}
          onClose={() => {
            if (!posting) setConfirmation(null);
          }}
          busy={posting}
        >
          <p>
            {confirmation.action === "reboot"
              ? "Rebooting stops applications on this server and disconnects this dashboard until the host and platform services return."
              : confirmation.impact ||
                "Restarting this service may interrupt applications and dashboard connectivity."}
          </p>
          <p>
            Affected applications:{" "}
            {(host?.affected_apps || []).map((app: any) => app.name).join(", ") || "No applications recorded"}
            .
          </p>
          <label>
            Enter the exact hostname <strong>{host?.hostname}</strong>
            <input
              autoComplete="off"
              value={hostname}
              onChange={(e) => setHostname(e.target.value)}
              disabled={posting}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={impact}
              onChange={(e) => setImpact(e.target.checked)}
              disabled={posting}
            />{" "}
            I understand applications and dashboard access may be interrupted.
          </label>
          <ErrorNotice error={submitError} />
        </ConfirmDialog>
      )}
    </ResourceWorkspace>
  );
}
