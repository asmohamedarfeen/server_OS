"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  AppWindow,
  ArrowDownToLine,
  Copy,
  ExternalLink,
  GitBranch,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Square,
  TerminalSquare,
  Trash2,
  Upload,
} from "lucide-react";
import { api, bytes } from "@/lib/api";
import { applicationUrl } from "@/lib/application-url";
import { AppRecord } from "@/lib/types";
import { ApplicationEndpoint } from "./application-runtime";
import { DeployModal } from "./resource-pages";
import { DeploymentConsole, DeploymentJobsPanel } from "./deployment-console";
import TerminalPanel from "./terminal-panel";
import {
  ActivityList,
  CommandBar,
  dateTime,
  EmptyState,
  ErrorNotice,
  href,
  itemsOf,
  Loading,
  MetricHistory,
  Notify,
  PageHeading,
  PortalRoute,
  Properties,
  Refresh,
  ResourceWorkspace,
  Status,
  useResource,
} from "./portal-shared";

export function PortalApplications({
  apps,
  loading,
  error,
  refresh,
  notify,
}: {
  apps: AppRecord[];
  loading: boolean;
  error: string;
  refresh: () => void;
  notify: Notify;
}) {
  const [query, setQuery] = useState(""),
    [create, setCreate] = useState(false),
    [job, setJob] = useState<string | null>(null);
  const filtered = apps.filter((a) =>
    `${a.name} ${a.framework} ${a.source}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <div className="az-page">
        <PageHeading title="App Services" subtitle="Applications running on your server" />
      </div>
      <CommandBar>
        <button onClick={() => setCreate(true)}>
          <Plus size={16} />
          Create
        </button>
        <Refresh onClick={refresh} />
        <a href={href("pipelines")}>
          <GitBranch size={15} />
          Pipelines
        </a>
      </CommandBar>
      <div className="az-page">
        <ErrorNotice error={error} retry={refresh} />
        <div className="az-filter-bar">
          <Search size={15} />
          <input
            aria-label="Filter applications"
            placeholder="Filter by name or runtime"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span>{filtered.length} applications</span>
        </div>
        {loading && !apps.length ? (
          <Loading />
        ) : (
          <div className="az-table-wrap">
            <table className="az-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Runtime</th>
                  <th>Source</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((app) => (
                  <tr key={app.id}>
                    <td>
                      <a className="az-resource-link" href={href("apps", app.id)}>
                        <AppWindow size={17} />
                        {app.name}
                      </a>
                    </td>
                    <td>
                      <Status value={app.status} />
                    </td>
                    <td>{app.framework}</td>
                    <td className="az-truncate" title={app.source}>
                      {app.source_type === "zip" ? "ZIP upload" : app.source}
                    </td>
                    <td>{dateTime(app.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!filtered.length && (
              <EmptyState
                title={apps.length ? "No matching applications" : "Create your first App Service"}
                detail="Connect a GitHub repository or upload a ZIP to build and run an application."
              />
            )}
          </div>
        )}
        <div className="az-section-gap">
          <DeploymentJobsPanel onOpen={setJob} onFinished={refresh} />
        </div>
      </div>
      {create && (
        <DeployModal
          notify={notify}
          onClose={() => setCreate(false)}
          onQueued={(id) => {
            setCreate(false);
            setJob(id);
          }}
        />
      )}
      {job && <DeploymentConsole jobId={job} onClose={() => setJob(null)} onFinished={refresh} />}
    </>
  );
}

export function PortalApplication({
  app,
  route,
  loading,
  error,
  notify,
  refresh,
}: {
  app?: AppRecord;
  route: PortalRoute;
  loading: boolean;
  error: string;
  notify: Notify;
  refresh: () => void;
}) {
  const jobs = useResource<any[]>("/deployment-jobs"),
    history = useResource<any[]>(app ? `/apps/${app.id}/deployments` : null);
  const readiness = useResource<any>(app ? `/apps/${app.id}/readiness` : null);
  const [busy, setBusy] = useState(""),
    [job, setJob] = useState<string | null>(null),
    [url, setUrl] = useState<string | null>(null);
  const zip = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (app) setUrl(applicationUrl(app, window.location.hostname));
  }, [app?.domain, app?.host_port]);
  if (!app)
    return (
      <div className="az-page">
        <ErrorNotice error={error} retry={refresh} />
        {loading ? (
          <Loading />
        ) : (
          <EmptyState
            title="Application not found"
            detail="It may have been deleted. Return to App Services to select an application."
          />
        )}
      </div>
    );
  const active = itemsOf(jobs.data).some(
    (j) => ["queued", "running"].includes(j.status) && (j.app_id === app.id || j.name === app.name),
  );
  async function act(action: string) {
    if (!app) return;
    if (
      ["stop", "delete", "rollback"].includes(action) &&
      !window.confirm(
        `${action === "delete" ? "Delete" : action === "rollback" ? "Roll back" : "Stop"} ${app.name}? ${action === "delete" ? "Its application container will be removed." : "This affects the running application."}`,
      )
    )
      return;
    setBusy(action);
    try {
      await api(`/apps/${app.id}/${action}`, { method: "POST" });
      notify(`${app.name}: ${action} completed`);
      if (action === "delete") window.location.hash = href("apps");
      else refresh();
      history.refresh();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Operation failed", "error");
    } finally {
      setBusy("");
    }
  }
  async function deploy(file?: File) {
    if (!app) return;
    if (app.source_type === "zip" && !file) {
      zip.current?.click();
      return;
    }
    setBusy("deploy");
    try {
      const form = new FormData();
      if (file) form.set("file", file);
      const result = await api(`/deployment-jobs/apps/${app.id}/${file ? "zip" : "github"}`, {
        method: "POST",
        ...(file ? { body: form } : {}),
      });
      setJob(result.id);
      jobs.refresh();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Deployment failed", "error");
    } finally {
      setBusy("");
    }
  }
  const disabled = !!busy || active || !!jobs.error || jobs.loading;
  const health = (app as AppRecord & { health?: string }).health;
  const tabs = [
    "Overview",
    "Deployment Center",
    "Log stream",
    "Configuration",
    "Metrics",
    "Activity log",
    "Console",
  ];
  return (
    <>
      <ResourceWorkspace
        title={app.name}
        type="App Service"
        icon={<AppWindow size={30} />}
        route={route}
        tabs={tabs}
        status={app.status}
        commands={
          <>
            {url && (
              <a href={url} target="_blank" rel="noreferrer" aria-label="Browse application">
                <ExternalLink size={15} />
                Browse
              </a>
            )}
            <button disabled={disabled || app.status === "running"} onClick={() => act("start")}>
              <Play size={15} />
              Start
            </button>
            <button disabled={disabled || app.status !== "running"} onClick={() => act("stop")}>
              <Square size={14} />
              Stop
            </button>
            <button disabled={disabled} onClick={() => act("restart")}>
              <RotateCcw size={15} />
              Restart
            </button>
            <button disabled={disabled} onClick={() => deploy()}>
              <Upload size={15} />
              Deploy
            </button>
            <button
              disabled={disabled || itemsOf(history.data).filter((h) => h.status === "success").length < 2}
              onClick={() => act("rollback")}
            >
              <RotateCcw size={15} />
              Roll back
            </button>
            <a href={href("apps", app.id, "log-stream")}>
              <TerminalSquare size={15} />
              Live logs
            </a>
            <Refresh
              onClick={() => {
                refresh();
                history.refresh();
                jobs.refresh();
              }}
            />
            <button className="az-danger" disabled={disabled} onClick={() => act("delete")}>
              <Trash2 size={15} />
              Delete
            </button>
          </>
        }
      >
        <ErrorNotice
          error={error || jobs.error}
          retry={() => {
            refresh();
            jobs.refresh();
          }}
        />
        {active && (
          <div className="az-notice">
            A deployment is active. Lifecycle controls will be available when it finishes.
          </div>
        )}
        {route.tab === "overview" && (
          <>
            <div className="az-section-heading">
              <h2>Overview</h2>
              <span>Essentials</span>
            </div>
            <div className="az-notice">
              <span className={`az-connection-dot ${app.status === "running" ? "online" : ""}`} />
              {app.status === "running"
                ? health === "healthy"
                  ? "Running · Docker health check healthy"
                  : health === "unhealthy"
                    ? "Running · Docker health check unhealthy"
                    : health === "starting"
                      ? "Running · Docker health check starting"
                      : readiness.error
                        ? "Running · readiness status unavailable"
                        : readiness.data?.path
                          ? "Running · HTTP readiness configured"
                          : "Running · readiness not configured"
                : `Application ${app.status}`}
            </div>
            <div className="az-app-essentials">
              <ApplicationEndpoint app={app} notify={notify} />
              <Properties
                rows={[
                  ["Runtime", app.framework],
                  ["Source", app.source],
                  [
                    "Branch",
                    app.source_ref || (app.source_type === "zip" ? "Not applicable" : "Default branch"),
                  ],
                  ["Image", app.image],
                  ["Container", app.container_id],
                  ["Published port", app.host_port || "Domain routing"],
                  ["Container port", app.port],
                  ["Created", dateTime(app.created_at)],
                ]}
              />
            </div>
            <div className="az-section-heading">
              <h2>Recent deployments</h2>
              <a href={href("apps", app.id, "deployment-center")}>Deployment Center</a>
            </div>
            <DeploymentHistory history={itemsOf(history.data)} error={history.error} />
          </>
        )}
        {route.tab === "deployment-center" && (
          <>
            <h2>Deployment Center</h2>
            <p className="az-muted">
              Configure the source and inspect deployment results for this application.
            </p>
            <SourceConfiguration app={app} notify={notify} refresh={refresh} locked={disabled} />
            <div className="az-section-heading">
              <h2>Deployment history</h2>
              <a href={href("pipelines")}>Configure a pipeline</a>
            </div>
            <DeploymentHistory history={itemsOf(history.data)} error={history.error} />
            <div className="az-section-gap">
              <DeploymentJobsPanel
                onOpen={setJob}
                onFinished={() => {
                  refresh();
                  history.refresh();
                }}
              />
            </div>
          </>
        )}
        {route.tab === "log-stream" && (
          <>
            <h2>Log stream</h2>
            <p className="az-muted">
              Current container stdout and stderr. Build output is available in Deployment Center.
            </p>
            <RuntimeStream app={app} notify={notify} />
          </>
        )}
        {route.tab === "configuration" && (
          <>
            <h2>Configuration</h2>
            <EnvironmentConfiguration app={app} notify={notify} refresh={refresh} locked={disabled} />
            <ReadinessConfiguration app={app} notify={notify} locked={disabled} />
          </>
        )}
        {route.tab === "metrics" && (
          <>
            <CurrentAppMetrics app={app} />
            <MetricHistory resourceId={app.id} />
          </>
        )}
        {route.tab === "activity-log" && <ActivityList resourceId={app.id} />}
        {route.tab === "console" && (
          <TerminalPanel key={app.container_id} target={{ id: app.container_id, name: app.name }} />
        )}
        {!tabs.some((t) => t.toLowerCase().replaceAll(" ", "-") === route.tab) && (
          <EmptyState title="View not found" detail="Choose a view from the application menu." />
        )}
      </ResourceWorkspace>
      <input
        hidden
        ref={zip}
        type="file"
        accept=".zip"
        onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          if (file) deploy(file);
          e.currentTarget.value = "";
        }}
      />
      {job && (
        <DeploymentConsole
          jobId={job}
          onClose={() => setJob(null)}
          onFinished={() => {
            refresh();
            history.refresh();
            jobs.refresh();
          }}
        />
      )}
    </>
  );
}

function DeploymentHistory({ history, error }: { history: any[]; error: string }) {
  return (
    <>
      <ErrorNotice error={error} />
      <div className="az-table-wrap">
        <table className="az-table">
          <thead>
            <tr>
              <th>Deployment</th>
              <th>Status</th>
              <th>Image</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {history.slice(0, 20).map((h) => (
              <tr key={h.id}>
                <td>{h.message}</td>
                <td>
                  <Status value={h.status} />
                </td>
                <td className="az-truncate">{h.image || "—"}</td>
                <td>{dateTime(h.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!history.length && <EmptyState title="No deployments recorded" />}
      </div>
    </>
  );
}

function EnvironmentConfiguration({
  app,
  notify,
  refresh,
  locked,
}: {
  app: AppRecord;
  notify: Notify;
  refresh: () => void;
  locked: boolean;
}) {
  const [revealed, setRevealed] = useState(false),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function reveal() {
    setBusy(true);
    try {
      const value = await api(`/apps/${app.id}/environment`);
      setText(
        Object.entries(value.environment || {})
          .map(([k, v]) => `${k}=${v}`)
          .join("\n"),
      );
      setRevealed(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (locked) return;
    setBusy(true);
    setError("");
    try {
      const environment: Record<string, string> = {};
      for (const line of text.split("\n")) {
        if (!line.trim() || line.trim().startsWith("#")) continue;
        const split = line.indexOf("=");
        if (split < 1) throw new Error("Use one KEY=value entry per line");
        const key = line.slice(0, split).trim();
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) throw new Error(`Invalid variable name: ${key}`);
        environment[key] = line.slice(split + 1);
      }
      await api(`/apps/${app.id}/environment`, { method: "PUT", body: JSON.stringify({ environment }) });
      setRevealed(false);
      setText("");
      refresh();
      notify("Configuration saved and application restarted");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="az-settings-section">
      <h3>Environment variables</h3>
      <p className="az-muted">
        Values are hidden. Saving replaces the application container and restarts it.
      </p>
      <ErrorNotice error={error} />
      {!revealed ? (
        <button className="az-button" disabled={busy} onClick={reveal}>
          {busy ? "Loading…" : "Reveal and edit values"}
        </button>
      ) : (
        <form className="az-form" onSubmit={save}>
          <label>
            Environment variables
            <textarea
              aria-label="Environment variables"
              rows={8}
              spellCheck={false}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <div>
            <button className="az-primary" disabled={busy || locked}>
              {busy ? "Saving…" : "Save and restart"}
            </button>
            <button
              type="button"
              onClick={() => {
                setRevealed(false);
                setText("");
              }}
            >
              Hide values
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
function ReadinessConfiguration({
  app,
  notify,
  locked,
}: {
  app: AppRecord;
  notify: Notify;
  locked: boolean;
}) {
  const state = useResource<any>(`/apps/${app.id}/readiness`, 0),
    [path, setPath] = useState(""),
    [expected, setExpected] = useState(200),
    [timeout, setTimeoutValue] = useState(90),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (state.data) {
      setPath(state.data.path || "");
      setExpected(state.data.expected_status);
      setTimeoutValue(state.data.timeout);
    }
  }, [state.data]);
  return (
    <section className="az-settings-section">
      <h3>HTTP readiness check</h3>
      <p className="az-muted">
        Verify a path inside the managed application after deployment. Leave it empty to use Docker
        health/startup checks.
      </p>
      <ErrorNotice error={state.error} retry={state.refresh} />
      <form
        className="az-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (locked || state.error || !state.data) return;
          setBusy(true);
          try {
            await api(`/apps/${app.id}/readiness`, {
              method: "PATCH",
              body: JSON.stringify({ path, expected_status: expected, timeout }),
            });
            notify("Readiness check saved for future deployments");
          } catch (e) {
            notify(e instanceof Error ? e.message : "Could not save readiness", "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Readiness path
          <input placeholder="/health" value={path} onChange={(e) => setPath(e.target.value)} />
        </label>
        <div className="az-form-row">
          <label>
            Expected HTTP status
            <input
              type="number"
              min={100}
              max={599}
              value={expected}
              onChange={(e) => setExpected(Number(e.target.value))}
            />
          </label>
          <label>
            Timeout (seconds)
            <input
              type="number"
              min={1}
              max={300}
              value={timeout}
              onChange={(e) => setTimeoutValue(Number(e.target.value))}
            />
          </label>
        </div>
        <button className="az-primary" disabled={busy || locked || state.loading || !!state.error || !state.data}>
          Save readiness check
        </button>
      </form>
    </section>
  );
}
function SourceConfiguration({
  app,
  notify,
  refresh,
  locked,
}: {
  app: AppRecord;
  notify: Notify;
  refresh: () => void;
  locked: boolean;
}) {
  const [source, setSource] = useState(app.source),
    [ref, setRef] = useState(app.source_ref || ""),
    [busy, setBusy] = useState(false);
  return (
    <section className="az-settings-section">
      <Properties
        rows={[
          ["Source type", app.source_type || "github"],
          ["Deployment target", app.name],
        ]}
      />
      {app.source_type !== "zip" && (
        <form
          className="az-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (locked) return;
            setBusy(true);
            try {
              await api(`/apps/${app.id}/source`, {
                method: "PATCH",
                body: JSON.stringify({ source, source_ref: ref, source_type: app.source_type || "github" }),
              });
              notify("Deployment source saved");
              refresh();
            } catch (e) {
              notify(e instanceof Error ? e.message : "Could not save source", "error");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Repository URL
            <input type="url" required value={source} onChange={(e) => setSource(e.target.value)} />
          </label>
          <label>
            Branch
            <input placeholder="Default branch" value={ref} onChange={(e) => setRef(e.target.value)} />
          </label>
          <button className="az-button" disabled={busy || locked}>
            Save source
          </button>
        </form>
      )}
    </section>
  );
}
function CurrentAppMetrics({ app }: { app: AppRecord }) {
  const { data, error, loading } = useResource<any>(`/apps/${app.id}/metrics`);
  return (
    <>
      <h2>Current container metrics</h2>
      <ErrorNotice error={error} />
      {loading ? (
        <Loading />
      ) : data?.available === false ? (
        <EmptyState
          title="Metrics unavailable"
          detail={data.reason || "Start the application to collect container metrics."}
        />
      ) : (
        data && (
          <Properties
            rows={[
              ["CPU", `${Number(data.cpu_percent || 0).toFixed(1)}%`],
              ["Memory", bytes(data.memory_bytes)],
              ["Memory limit", bytes(data.memory_limit_bytes)],
              ["Network received", bytes(data.network_rx_bytes)],
              ["Network sent", bytes(data.network_tx_bytes)],
              ["Sampled", dateTime(data.timestamp)],
            ]}
          />
        )
      )}
    </>
  );
}

function RuntimeStream({ app, notify }: { app: AppRecord; notify: Notify }) {
  const [paused, setPaused] = useState(false),
    [follow, setFollow] = useState(true),
    [snapshot, setSnapshot] = useState<any>(null),
    ref = useRef<HTMLDivElement>(null);
  const state = useResource<any>(paused ? null : `/apps/${app.id}/logs?tail=2000`, 2000);
  useEffect(() => {
    if (state.data) setSnapshot(state.data);
  }, [state.data]);
  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [snapshot, follow]);
  function download() {
    const blob = URL.createObjectURL(new Blob([snapshot?.logs || ""], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = blob;
    link.download = `${app.name}-runtime.log`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(blob), 1000);
  }
  return (
    <div className="az-runtime-stream">
      <div className="az-runtime-toolbar">
        <span>
          <span className={`az-connection-dot ${!paused && !state.error && snapshot ? "online" : ""}`} />
          {paused ? "Updates paused" : state.error ? "Reconnecting" : "Live · every 2 seconds"}
        </span>
        <div>
          <button onClick={() => setPaused(!paused)}>
            {paused ? <Play size={13} /> : <Pause size={13} />}
            {paused ? "Resume updates" : "Pause updates"}
          </button>
          <label>
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            Follow logs
          </label>
          <button
            disabled={!snapshot}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(snapshot?.logs || "");
                notify("Logs copied");
              } catch {
                notify("Could not copy logs. Use Download logs instead.", "error");
              }
            }}
          >
            <Copy size={13} />
            Copy logs
          </button>
          <button disabled={!snapshot} onClick={download}>
            <ArrowDownToLine size={13} />
            Download logs
          </button>
        </div>
      </div>
      <ErrorNotice
        error={state.error ? `${state.error}. Retrying automatically; previous output is retained.` : ""}
      />
      <div
        ref={ref}
        role="log"
        aria-label="Application runtime output"
        aria-live="off"
        tabIndex={0}
        className="az-log-panel"
        onWheel={(e) => {
          if (e.deltaY < 0) setFollow(false);
        }}
        onKeyDown={(e) => {
          if (["ArrowUp", "PageUp", "Home"].includes(e.key)) setFollow(false);
        }}
      >
        <pre>
          {snapshot
            ? snapshot.logs ||
              "No application output yet. Logs appear when the app writes to stdout or stderr."
            : "Connecting to application logs…"}
        </pre>
      </div>
      <footer>Latest 2,000 lines · stdout + stderr · {snapshot?.status || "Connecting"}</footer>
    </div>
  );
}
