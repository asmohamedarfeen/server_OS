"use client";
import { useState } from "react";
import { Box, Database, HardDrive, Layers3, Network, Play, RotateCcw, Square, Trash2 } from "lucide-react";
import { api, bytes } from "@/lib/api";
import TerminalPanel from "./terminal-panel";
import {
  ActivityList,
  ErrorNotice,
  href,
  Loading,
  Notify,
  PortalRoute,
  Properties,
  Refresh,
  ResourceWorkspace,
  useResource,
} from "./portal-shared";

export function InfrastructureResource({
  route,
  resource,
  loading,
  error,
  refresh,
  notify,
}: {
  route: PortalRoute;
  resource: any;
  loading: boolean;
  error: string;
  refresh: () => void;
  notify: Notify;
}) {
  const [busy, setBusy] = useState(false);
  const container = route.view === "containers",
    database = route.view === "databases";
  const live = container || database;
  const logs = useResource<any>(
    live && route.tab === "log-stream"
      ? `/${container ? "containers" : "databases"}/${encodeURIComponent(route.id!)}/logs`
      : null,
    2000,
  );
  if (!resource)
    return (
      <div className="az-page">
        <ErrorNotice error={error} retry={refresh} />
        {loading ? (
          <Loading />
        ) : (
          <>
            <h1>Resource not found</h1>
            <p>This resource may have been removed.</p>
            <a href={href(route.view)}>Return to resources</a>
          </>
        )}
      </div>
    );
  const name = resource.name || resource.tags?.[0] || resource.id;
  const type = container
    ? "Container"
    : database
      ? "Database"
      : route.view === "images"
        ? "Image"
        : route.view === "networks"
          ? "Network"
          : "Volume";
  const Icon = container
    ? Box
    : database
      ? Database
      : route.view === "images"
        ? Layers3
        : route.view === "networks"
          ? Network
          : HardDrive;
  async function action(verb: string) {
    if (
      ["stop", "delete"].includes(verb) &&
      !window.confirm(
        `${verb === "delete" ? "Delete" : "Stop"} ${name}? ${verb === "delete" ? "This removes the selected resource." : "This interrupts its workload."}`,
      )
    )
      return;
    setBusy(true);
    try {
      if (container && verb === "delete") await api(`/containers/${resource.id}`, { method: "DELETE" });
      else if (live)
        await api(`/${container ? "containers" : "databases"}/${resource.id}/${verb}`, { method: "POST" });
      else
        await api(
          `/docker/${route.view}/${encodeURIComponent(resource.full_id || resource.name || resource.id)}`,
          { method: "DELETE" },
        );
      notify(`${name}: ${verb} completed`);
      refresh();
      if (verb === "delete") window.location.hash = href(route.view);
    } catch (e) {
      notify(e instanceof Error ? e.message : "Resource operation failed", "error");
    } finally {
      setBusy(false);
    }
  }
  const rows: [string, React.ReactNode][] = [
    ["Resource ID", resource.full_id || resource.id || resource.name],
    ["Type", type],
  ];
  for (const [key, title] of [
    ["image", "Image"],
    ["engine", "Engine"],
    ["username", "Username"],
    ["connection_host", "Connection host"],
    ["port", "Port"],
    ["driver", "Driver"],
    ["scope", "Scope"],
    ["mountpoint", "Mount point"],
    ["created", "Created"],
    ["created_at", "Created"],
  ])
    if (resource[key] != null) rows.push([title, String(resource[key])]);
  if (resource.size != null) rows.push(["Image size", bytes(resource.size)]);
  if (resource.tags?.length) rows.push(["Tags", resource.tags.join(", ")]);
  if (resource.ports?.length)
    rows.push(["Published ports", resource.ports.map((p: any) => `${p.host} → ${p.container}`).join(", ")]);
  if (resource.containers != null) rows.push(["Attached containers", resource.containers]);
  return (
    <ResourceWorkspace
      title={name}
      type={type}
      icon={<Icon size={30} />}
      route={route}
      tabs={[
        "Overview",
        ...(live ? ["Log stream", ...(resource.container_id || container ? ["Console"] : [])] : []),
        "Activity log",
      ]}
      status={resource.status || "available"}
      commands={
        <>
          {live && (
            <>
              <button
                disabled={busy || resource.system || resource.status === "running"}
                onClick={() => action("start")}
              >
                <Play size={14} />
                Start
              </button>
              <button
                disabled={busy || resource.system || resource.status !== "running"}
                onClick={() => action("stop")}
              >
                <Square size={14} />
                Stop
              </button>
              <button disabled={busy || resource.system} onClick={() => action("restart")}>
                <RotateCcw size={14} />
                Restart
              </button>
            </>
          )}
          <Refresh onClick={refresh} />
          <a href={href(route.view)}>View all {route.view}</a>
          {route.view !== "networks" && (
            <button disabled={busy || resource.system} className="az-danger" onClick={() => action("delete")}>
              <Trash2 size={14} />
              Delete
            </button>
          )}
        </>
      }
    >
      <ErrorNotice error={error} retry={refresh} />
      {resource.system && (
        <div className="az-notice">
          This resource belongs to the management platform. Lifecycle and deletion controls are protected.
        </div>
      )}
      {route.tab === "overview" && (
        <>
          <h2>Overview</h2>
          <Properties rows={rows} />
        </>
      )}
      {route.tab === "activity-log" && <ActivityList resourceId={route.id} />}
      {route.tab === "log-stream" && (
        <>
          <h2>Log stream</h2>
          <ErrorNotice error={logs.error} retry={logs.refresh} />
          <div className="az-log-panel" role="log" aria-label={`${type} runtime output`} tabIndex={0}>
            <pre>{logs.data?.logs || (logs.loading ? "Connecting…" : "No output recorded.")}</pre>
          </div>
        </>
      )}
      {route.tab === "console" && (
        <TerminalPanel target={{ id: resource.container_id || resource.id, name }} />
      )}
    </ResourceWorkspace>
  );
}
