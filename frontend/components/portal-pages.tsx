"use client";
import { useState } from "react";
import { Activity, AppWindow, ArrowRight, Box, GitBranch, Plus, RefreshCw, Server } from "lucide-react";
import { AppRecord } from "@/lib/types";
import {
  ActivityList,
  CommandBar,
  dateTime,
  EmptyState,
  ErrorNotice,
  href,
  itemsOf,
  PageHeading,
  Status,
  useResource,
} from "./portal-shared";
export type ResourceRow = {
  id: string;
  name: string;
  type: string;
  status: string;
  href: string;
  detail?: string;
};

export function ResourceInventory({
  resources,
  onRefresh,
  errors = [],
}: {
  resources: ResourceRow[];
  onRefresh: () => void;
  errors?: string[];
}) {
  const [query, setQuery] = useState(""),
    [type, setType] = useState("All types");
  const filtered = resources.filter(
    (r) =>
      `${r.name} ${r.detail || ""}`.toLowerCase().includes(query.toLowerCase()) &&
      (type === "All types" || r.type === type),
  );
  return (
    <>
      <div className="az-page">
        <PageHeading title="All resources" subtitle="Every resource on your managed server" />
      </div>
      <CommandBar>
        <a href={href("apps")}>
          <Plus size={15} />
          Create an app
        </a>
        <button onClick={onRefresh}>
          <RefreshCw size={15} />
          Refresh
        </button>
      </CommandBar>
      <div className="az-page">
        <ErrorNotice
          error={
            errors.length ? `Some resources could not be loaded: ${[...new Set(errors)].join(" · ")}` : ""
          }
          retry={onRefresh}
        />
        <div className="az-filter-bar">
          <input
            aria-label="Filter resources"
            placeholder="Filter by name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select aria-label="Resource type" value={type} onChange={(e) => setType(e.target.value)}>
            {["All types", ...new Set(resources.map((r) => r.type))].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <span>{filtered.length} resources</span>
        </div>
        <ResourceTable resources={filtered} />
      </div>
    </>
  );
}
export function ResourceTable({ resources }: { resources: ResourceRow[] }) {
  return (
    <div className="az-table-wrap">
      <table className="az-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Status</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {resources.map((r) => (
            <tr key={`${r.type}:${r.id}`}>
              <td>
                <a href={r.href}>{r.name}</a>
              </td>
              <td>{r.type}</td>
              <td>
                <Status value={r.status} />
              </td>
              <td className="az-truncate" title={r.detail}>
                {r.detail || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!resources.length && (
        <EmptyState title="No resources to display" detail="Create an application or change your filters." />
      )}
    </div>
  );
}
export function PortalHome({
  resources,
  recent,
  server,
  apps,
  loading,
  onRefresh,
}: {
  resources: ResourceRow[];
  recent: ResourceRow[];
  server: any;
  apps: AppRecord[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const jobs = useResource<any[]>("/deployment-jobs"),
    active = itemsOf(jobs.data).filter((j) => ["running", "queued"].includes(j.status));
  return (
    <div className="az-page az-home">
      <PageHeading
        title="Welcome to Arfeen Cloud"
        subtitle="Build, manage, and monitor your private infrastructure."
      >
        <button className="az-text-button" onClick={onRefresh}>
          <RefreshCw size={15} />
          Refresh
        </button>
      </PageHeading>
      <section className="az-home-services">
        <h2>Cloud services</h2>
        <div>
          {[
            {
              label: "App Services",
              detail: "Deploy and manage applications",
              view: "apps",
              icon: AppWindow,
            },
            { label: "Pipelines", detail: "Build, test, and release", view: "pipelines", icon: GitBranch },
            { label: "Server", detail: "Manage your Ubuntu host", view: "server", icon: Server },
            { label: "Containers", detail: "Inspect your Docker workloads", view: "containers", icon: Box },
            { label: "Monitor", detail: "Metrics and diagnostics", view: "monitor", icon: Activity },
          ].map(({ label, detail, view, icon: Icon }) => (
            <a key={view} href={href(view, view === "server" ? "server" : undefined)}>
              <Icon size={29} strokeWidth={1.4} />
              <strong>{label}</strong>
              <span>{detail}</span>
            </a>
          ))}
        </div>
      </section>
      <section className="az-home-health">
        <div>
          <span className={`az-connection-dot ${server ? "online" : ""}`} />
          <strong>{server?.hostname || (loading ? "Connecting to server…" : "Server unavailable")}</strong>
          <span>{server?.platform || "Managed server"}</span>
        </div>
        <a href={href("server", "server")}>
          View server <ArrowRight size={14} />
        </a>
      </section>
      <div className="az-home-summary">
        <div>
          <span>App Services</span>
          <strong>{apps.length}</strong>
          <small>{apps.filter((a) => a.status === "running").length} running</small>
        </div>
        <div>
          <span>Docker resources</span>
          <strong>
            {resources.filter((r) => ["Container", "Volume", "Network"].includes(r.type)).length}
          </strong>
          <small>On this server</small>
        </div>
        <div>
          <span>Active builds</span>
          <strong>{jobs.error ? "—" : active.length}</strong>
          <small>{jobs.error ? "Build status unavailable" : "Local build agent"}</small>
        </div>
        <div>
          <span>Server CPU</span>
          <strong>{server?.cpu_percent != null ? `${Math.round(server.cpu_percent)}%` : "—"}</strong>
          <small>{server?.cpu_count ? `${server.cpu_count} logical cores` : "Waiting for sample"}</small>
        </div>
      </div>
      <section>
        <div className="az-section-heading">
          <h2>Recent resources</h2>
          <a href={href("resources")}>
            View all resources <ArrowRight size={13} />
          </a>
        </div>
        <ResourceTable
          resources={
            recent.length
              ? recent.filter((r) => resources.some((x) => x.href === r.href))
              : resources.filter((r) => ["App Service", "Server", "Database"].includes(r.type)).slice(0, 6)
          }
        />
      </section>
      <section>
        <div className="az-section-heading">
          <h2>Build activity</h2>
          <a href={href("pipelines")}>
            Open Pipelines <ArrowRight size={13} />
          </a>
        </div>
        <ErrorNotice error={jobs.error} retry={jobs.refresh} />
        <div className="az-table-wrap">
          <table className="az-table">
            <thead>
              <tr>
                <th>Application</th>
                <th>Status</th>
                <th>Stage</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {itemsOf(jobs.data)
                .slice(0, 5)
                .map((job) => (
                  <tr key={job.id}>
                    <td>
                      <a href={href("apps", job.app_id || undefined, "deployment-center")}>{job.name}</a>
                    </td>
                    <td>
                      <Status value={job.status} />
                    </td>
                    <td>{job.stage}</td>
                    <td>{dateTime(job.started_at || job.created_at)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!itemsOf(jobs.data).length && (
            <EmptyState
              title="No builds yet"
              detail="Deploy your first application to see build progress and results here."
            />
          )}
        </div>
      </section>
      <section>
        <ActivityList />
      </section>
    </div>
  );
}
