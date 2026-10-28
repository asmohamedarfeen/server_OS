"use client";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

export type Notify = (message: string, kind?: "success" | "error") => void;
export type PortalRoute = { view: string; id?: string; tab: string };
export function href(view: string, id?: string, tab = "overview") {
  return `#${[view, ...(id ? [id, tab] : [])].map(encodeURIComponent).join("/")}`;
}
export function parseRoute(hash: string): PortalRoute {
  try {
    const [view = "home", id, tab = "overview"] = hash
      .replace(/^#/, "")
      .split("/")
      .filter(Boolean)
      .map(decodeURIComponent);
    return { view, id, tab };
  } catch {
    return { view: "home", tab: "overview" };
  }
}
export function useResource<T = any>(path: string | null, interval = 6000) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((r) => r + 1), []);
  useEffect(() => {
    setData(null);
    setError("");
    setLoading(true);
    if (!path) {
      setLoading(false);
      return;
    }
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      controller: AbortController;
    async function load() {
      controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), 15000);
      try {
        const value = await api<T>(path!, { signal: controller.signal });
        if (!stopped) {
          setData(value);
          setError("");
        }
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : "Request failed");
      } finally {
        clearTimeout(deadline);
        if (!stopped) {
          setLoading(false);
          if (interval) timer = setTimeout(load, interval);
        }
      }
    }
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [path, interval, revision]);
  return { data, error, loading, refresh };
}
export function itemsOf(data: any): any[] {
  return Array.isArray(data) ? data : data?.items || [];
}
export function Status({ value }: { value?: string | null }) {
  const status = value || "unknown",
    good = ["running", "active", "healthy", "success", "succeeded", "complete"].includes(status),
    busy = ["queued", "requested", "dispatched", "reconnecting", "starting", "pending"].includes(status);
  return (
    <span
      className={`az-status ${good ? "good" : busy ? "pending" : ["failed", "unhealthy", "exited", "error"].includes(status) ? "bad" : "neutral"}`}
    >
      {good ? <CheckCircle2 size={13} /> : busy ? <Clock3 size={13} /> : <span className="az-status-dot" />}
      {status.replaceAll("_", " ")}
    </span>
  );
}
export function ErrorNotice({ error, retry }: { error?: string; retry?: () => void }) {
  return error ? (
    <div className="az-notice error" role="alert">
      <AlertCircle size={16} />
      <span>{error}</span>
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  ) : null;
}
export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="az-empty">
      <strong>{title}</strong>
      {detail && <p>{detail}</p>}
    </div>
  );
}
export function Loading() {
  return (
    <div className="az-loading" role="status">
      <LoaderCircle size={16} className="spin" /> Loading resource…
    </div>
  );
}
export function PageHeading({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <header className="az-page-heading">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children}
    </header>
  );
}
export function CommandBar({ children }: { children: ReactNode }) {
  return <div className="az-command-bar">{children}</div>;
}
export function Refresh({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick}>
      <RefreshCw size={15} />
      Refresh
    </button>
  );
}
export function Properties({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="az-properties">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
export function ResourceWorkspace({
  title,
  type,
  tabs,
  route,
  children,
  commands,
  status,
  icon,
}: {
  title: string;
  type: string;
  tabs: string[];
  route: PortalRoute;
  children: ReactNode;
  commands?: ReactNode;
  status?: string;
  icon: ReactNode;
}) {
  return (
    <>
      <header className="az-resource-heading">
        <div className="az-resource-icon">{icon}</div>
        <div>
          <h1>{title}</h1>
          <span>{type}</span>
        </div>
        {status && <Status value={status} />}
      </header>
      {commands && <CommandBar>{commands}</CommandBar>}
      <div className="az-resource-workspace">
        <nav aria-label={`${type} menu`} className="az-service-menu">
          {tabs.map((tab) => (
            <a
              key={tab}
              href={href(route.view, route.id, tabKey(tab))}
              className={route.tab === tabKey(tab) ? "selected" : ""}
            >
              {tab}
            </a>
          ))}
        </nav>
        <div className="az-resource-content">{children}</div>
      </div>
    </>
  );
}
export function tabKey(label: string) {
  return label.toLowerCase().replaceAll(" ", "-");
}
export function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}
export function ActivityList({ resourceId }: { resourceId?: string }) {
  const { data, error, loading, refresh } = useResource(
    `/control/activity${resourceId ? `?resource_id=${encodeURIComponent(resourceId)}` : ""}`,
  );
  return (
    <>
      <div className="az-section-heading">
        <h2>Activity log</h2>
        <button className="az-text-button" onClick={refresh}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      <ErrorNotice error={error} retry={refresh} />
      {loading ? (
        <Loading />
      ) : (
        <div className="az-table-wrap">
          <table className="az-table">
            <thead>
              <tr>
                <th>Operation</th>
                <th>Status</th>
                <th>Resource</th>
                <th>Initiated by</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {itemsOf(data).map((event) => (
                <tr key={event.id}>
                  <td>
                    <strong>{event.action.replaceAll("_", " ")}</strong>
                    {event.message && <small>{event.message}</small>}
                  </td>
                  <td>
                    <Status value={event.status} />
                  </td>
                  <td>{event.resource_name}</td>
                  <td>{event.actor}</td>
                  <td>{dateTime(event.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!itemsOf(data).length && (
            <EmptyState
              title="No operations recorded yet"
              detail="Resource changes and deployment results will appear here."
            />
          )}
        </div>
      )}
    </>
  );
}
export function MetricHistory({ resourceId = "server" }: { resourceId?: string }) {
  const { data, error, loading, refresh } = useResource(
    `/control/metrics?resource_id=${encodeURIComponent(resourceId)}`,
    10000,
  );
  const samples = itemsOf(data);
  const percentage = (sample: any, key: string): number | null => {
    const memory = sample.memory || sample.metrics?.memory;
    const value =
      key === "cpu"
        ? (sample.cpu_percent ?? sample.metrics?.cpu_percent)
        : (memory?.percent ??
          sample.memory_percent ??
          (memory?.total > 0 ? (memory.used / memory.total) * 100 : null));
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  };
  return (
    <>
      <div className="az-section-heading">
        <h2>Metrics</h2>
        <span>Collected samples · retained for 24 hours</span>
      </div>
      <ErrorNotice error={error} retry={refresh} />
      {loading ? (
        <Loading />
      ) : !samples.length ? (
        <EmptyState
          title="Waiting for metric samples"
          detail="History is collected on the server and survives page navigation. No sample history is available yet."
        />
      ) : (
        <div className="az-metric-history">
          {["cpu", "memory"].map((key) => {
            const values = samples
              .map((s) => ({ timestamp: s.timestamp, value: percentage(s, key) }))
              .filter((s) => s.value !== null);
            return (
              <section className="az-chart" key={key}>
                <h3>
                  {key === "cpu" ? "CPU" : "Memory"} usage{" "}
                  <strong>{values.at(-1)?.value?.toFixed(1) ?? "—"}%</strong>
                </h3>
                {values.length ? (
                  <>
                    <svg
                      viewBox="0 0 600 150"
                      role="img"
                      aria-label={`${key} usage over ${values.length} collected samples`}
                    >
                      <line x1="0" y1="140" x2="600" y2="140" stroke="#d5d9dd" />
                      <line x1="0" y1="70" x2="600" y2="70" stroke="#eceff1" />
                      <polyline
                        fill="none"
                        stroke={key === "cpu" ? "#0078d4" : "#8764b8"}
                        strokeWidth="2"
                        points={values
                          .map(
                            (s, i) =>
                              `${values.length === 1 ? 300 : (i * 600) / (values.length - 1)},${140 - Math.min(s.value!, 100) * 1.3}`,
                          )
                          .join(" ")}
                      />
                      {values.length === 1 && (
                        <circle
                          cx="300"
                          cy={140 - Math.min(values[0].value!, 100) * 1.3}
                          r="3"
                          fill="#0078d4"
                        />
                      )}
                    </svg>
                    <div className="az-chart-axis">
                      <span>{dateTime(values[0].timestamp)}</span>
                      <span>{dateTime(values.at(-1)?.timestamp)}</span>
                    </div>
                  </>
                ) : (
                  <EmptyState
                    title="No samples available"
                    detail="Waiting for this measurement to be collected."
                  />
                )}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onClose,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      prior?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="az-dialog"
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <h2>{title}</h2>
      {children}
      <div className="az-dialog-actions">
        <button className="az-primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Working…" : confirmLabel}
        </button>
        <button disabled={busy} onClick={onClose}>
          Cancel
        </button>
      </div>
    </dialog>
  );
}
