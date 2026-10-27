"use client";
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, bytes } from "@/lib/api";
import { AppRecord, Container, DatabaseRecord } from "@/lib/types";
import {
  Activity,
  ArrowDownToLine,
  Box,
  Check,
  ChevronRight,
  CirclePlus,
  Clock3,
  Code2,
  Database,
  File,
  FileText,
  Folder,
  FolderPlus,
  HardDrive,
  Image,
  Layers3,
  LoaderCircle,
  Network,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Server,
  Settings2,
  Square,
  TerminalSquare,
  Trash2,
  Upload,
  X,
} from "lucide-react";

type Props = { notify: (message: string, kind?: "success" | "error") => void };
function Header({
  kicker,
  title,
  description,
  action,
}: {
  kicker: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="welcome-row">
      <div>
        <p className="page-kicker">{kicker}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section className="modal-card" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <div>
            <h2>{title}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={17} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function Empty({ icon: Icon = Box, title, detail }: { icon?: any; title: string; detail: string }) {
  return (
    <div className="empty-state">
      <div>
        <Icon size={22} />
      </div>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}
function ErrorBlock({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="notice notice-warning">
      {message}
      <button onClick={retry}>Try again</button>
    </div>
  );
}

export function ContainersPage({
  notify,
  onTerminal,
}: {
  notify: Props["notify"];
  onTerminal?: (container: Container) => void;
}) {
  const [items, setItems] = useState<Container[]>([]),
    [busy, setBusy] = useState(true),
    [error, setError] = useState(""),
    [modal, setModal] = useState(false),
    [logs, setLogs] = useState<string | null>(null),
    [selected, setSelected] = useState<Container | null>(null),
    [query, setQuery] = useState("");
  const load = () => {
    setBusy(true);
    api<Container[]>("/containers")
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  };
  useEffect(load, []);
  async function action(id: string, name: string, action: string) {
    try {
      await api(`/containers/${id}/${action}`, { method: "POST" });
      notify(`${name} ${action} completed`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Action failed", "error");
    }
  }
  async function remove(c: Container) {
    if (!window.confirm(`Delete container ${c.name}?`)) return;
    try {
      await api(`/containers/${c.id}`, { method: "DELETE" });
      notify(`${c.name} deleted`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Delete failed", "error");
    }
  }
  async function showLogs(c: Container) {
    setSelected(c);
    try {
      const x = await api<{ logs: string }>(`/containers/${c.id}/logs`);
      setLogs(x.logs);
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not load logs", "error");
    }
  }
  const filtered = items.filter((c) => `${c.name} ${c.image}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="page-body">
      <Header
        kicker="RUNTIME / CONTAINERS"
        title="Containers"
        description="Control workloads running on your Docker Engine."
        action={
          <>
            <button className="button button-light" onClick={load}>
              <RefreshCw size={15} />
            </button>
            <button className="button button-primary" onClick={() => setModal(true)}>
              <CirclePlus size={15} /> New container
            </button>
          </>
        }
      />
      <div className="toolbar">
        <div className="search-box">
          <Search size={15} />
          <input placeholder="Search containers" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="toolbar-summary">
          <span className="status-pip" />
          {items.filter((c) => c.status === "running").length} running <span>·</span> {items.length} total
        </div>
      </div>
      {error && <ErrorBlock message={error} retry={load} />}
      <section className="panel data-panel">
        {busy ? (
          <div className="loading-line">
            <LoaderCircle size={17} className="spin" /> Loading containers…
          </div>
        ) : filtered.length === 0 ? (
          <Empty
            title="No containers found"
            detail="Create a container or deploy an application to get started."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>CONTAINER</th>
                  <th>IMAGE</th>
                  <th>STATUS</th>
                  <th>PORTS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div className="table-primary">
                        <div className="container-symbol">
                          <Box size={15} />
                        </div>
                        <div>
                          <strong>{c.name}</strong>
                          <small>{c.id}</small>
                        </div>
                      </div>
                    </td>
                    <td className="mono-cell">{c.image}</td>
                    <td>
                      <span className={`badge ${c.status === "running" ? "badge-green" : "badge-gray"}`}>
                        <i />
                        {c.status}
                      </span>
                      {c.system && <span className="badge badge-gray">Platform</span>}
                    </td>
                    <td className="mono-cell">
                      {c.ports?.map((p) => `${p.host} → ${p.container}`).join(", ") || "—"}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          title="Container terminal"
                          disabled={c.status !== "running" || c.system}
                          onClick={() => onTerminal?.(c)}
                        >
                          <TerminalSquare size={15} />
                        </button>
                        <button title="Logs" onClick={() => showLogs(c)}>
                          <FileText size={15} />
                        </button>
                        {c.status === "running" ? (
                          <button
                            title="Restart"
                            disabled={c.system}
                            onClick={() => action(c.id, c.name, "restart")}
                          >
                            <RotateCcw size={15} />
                          </button>
                        ) : (
                          <button
                            title="Start"
                            disabled={c.system}
                            onClick={() => action(c.id, c.name, "start")}
                          >
                            <Play size={15} />
                          </button>
                        )}
                        <button
                          title="Stop"
                          onClick={() => action(c.id, c.name, "stop")}
                          disabled={c.status !== "running" || c.system}
                        >
                          <Square size={14} />
                        </button>
                        <button
                          title="Delete"
                          className="danger-action"
                          disabled={c.system}
                          onClick={() => remove(c)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {modal && (
        <CreateContainer
          onClose={() => setModal(false)}
          onCreated={() => {
            setModal(false);
            load();
            notify("Container created");
          }}
          notify={notify}
        />
      )}
      {logs !== null && (
        <Modal title={`Logs · ${selected?.name}`} onClose={() => setLogs(null)}>
          <pre className="log-output">{logs || "No logs available."}</pre>
        </Modal>
      )}
    </div>
  );
}
function CreateContainer({
  onClose,
  onCreated,
  notify,
}: {
  onClose: () => void;
  onCreated: () => void;
  notify: Props["notify"];
}) {
  const [name, setName] = useState(""),
    [image, setImage] = useState(""),
    [loading, setLoading] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await api("/containers", { method: "POST", body: JSON.stringify({ name, image }) });
      onCreated();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not create container", "error");
    } finally {
      setLoading(false);
    }
  }
  return (
    <Modal title="Create a container" onClose={onClose}>
      <form className="modal-form" onSubmit={submit}>
        <label>
          Container name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-service" required />
        </label>
        <label>
          Image
          <input
            value={image}
            onChange={(e) => setImage(e.target.value)}
            placeholder="nginx:alpine"
            required
          />
        </label>
        <p className="form-hint">
          Image must be available locally or in a public registry. Private registry support can be configured
          in Docker.
        </p>
        <div className="modal-actions">
          <button type="button" className="button button-light" onClick={onClose}>
            Cancel
          </button>
          <button className="button button-primary" disabled={loading}>
            {loading ? "Creating…" : "Create container"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function ApplicationsPage({ notify }: { notify: Props["notify"] }) {
  const [items, setItems] = useState<AppRecord[]>([]),
    [loading, setLoading] = useState(true),
    [modal, setModal] = useState(false),
    [history, setHistory] = useState<any[] | null>(null),
    [envApp, setEnvApp] = useState<AppRecord | null>(null),
    [zipApp, setZipApp] = useState<AppRecord | null>(null);
  const zipInput = useRef<HTMLInputElement>(null);
  const load = () => {
    setLoading(true);
    api<AppRecord[]>("/apps")
      .then(setItems)
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  async function action(app: AppRecord, act: string) {
    if (act === "delete" && !window.confirm(`Delete ${app.name} and its container?`)) return;
    try {
      await api(`/apps/${app.id}/${act}`, { method: "POST" });
      notify(`${app.name} ${act} completed`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Action failed", "error");
    }
  }
  async function showHistory(app: AppRecord) {
    try {
      setHistory(await api(`/apps/${app.id}/deployments`));
    } catch (e) {
      notify(e instanceof Error ? e.message : "History unavailable", "error");
    }
  }
  async function redeploy(app: AppRecord) {
    if (app.source.startsWith("https://github.com/") || app.source.startsWith("https://www.github.com/")) {
      try {
        await api(`/apps/${app.id}/redeploy/github`, { method: "POST" });
        notify(`${app.name} redeployed`);
        load();
      } catch (e) {
        notify(e instanceof Error ? e.message : "Redeploy failed", "error");
      }
    } else {
      setZipApp(app);
      zipInput.current?.click();
    }
  }
  async function redeployZip(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !zipApp) return;
    const form = new FormData();
    form.set("file", file);
    try {
      await api(`/apps/${zipApp.id}/redeploy/zip`, { method: "POST", body: form });
      notify(`${zipApp.name} redeployed`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Redeploy failed", "error");
    } finally {
      setZipApp(null);
      event.target.value = "";
    }
  }
  return (
    <div className="page-body">
      <Header
        kicker="DELIVERY / APPLICATIONS"
        title="Applications"
        description="Deploy and manage services from a repository or ZIP archive."
        action={
          <>
            <button className="button button-light" onClick={load}>
              <RefreshCw size={15} />
            </button>
            <button className="button button-primary" onClick={() => setModal(true)}>
              <CirclePlus size={15} /> Deploy application
            </button>
          </>
        }
      />
      <div className="app-summary-row">
        <div>
          <strong>{items.length}</strong>
          <span>applications</span>
        </div>
        <div>
          <strong>{items.filter((a) => a.status === "running").length}</strong>
          <span>online</span>
        </div>
        <div>
          <strong>{items.filter((a) => a.status !== "running").length}</strong>
          <span>attention needed</span>
        </div>
      </div>
      {loading ? (
        <div className="panel loading-line">
          <LoaderCircle size={17} className="spin" /> Loading applications…
        </div>
      ) : items.length === 0 ? (
        <section className="panel">
          <Empty
            icon={Code2}
            title="Your first app starts here"
            detail="Connect a GitHub repository or upload a ZIP. Arfeen will detect its framework, build an image, and start a container."
          />
          <div className="empty-cta">
            <button className="button button-primary" onClick={() => setModal(true)}>
              <CirclePlus size={15} /> Deploy application
            </button>
          </div>
        </section>
      ) : (
        <>
          <input ref={zipInput} type="file" accept=".zip,application/zip" hidden onChange={redeployZip} />
          <div className="app-card-grid">
            {items.map((app) => (
              <article className="app-card" key={app.id}>
                <div className="app-card-top">
                  <div className="app-monogram">{app.name.slice(0, 1).toUpperCase()}</div>
                  <span className={`badge ${app.status === "running" ? "badge-green" : "badge-red"}`}>
                    <i />
                    {app.status}
                  </span>
                  <button
                    className="icon-button"
                    title="Application actions"
                    onClick={() => showHistory(app)}
                  >
                    <Clock3 size={16} />
                  </button>
                </div>
                <h2>{app.name}</h2>
                <p>
                  {app.framework} · {app.source}
                </p>
                <div className="app-card-url">
                  <span>
                    {app.domain ? `http://${app.domain}` : `Container port :${app.host_port || "—"}`}
                  </span>
                  <span className="mono-cell">{app.domain ? `:${app.port}` : ""}</span>
                </div>
                <div className="app-card-actions">
                  <button onClick={() => redeploy(app)}>
                    <Upload size={14} /> Redeploy
                  </button>
                  <button onClick={() => action(app, "restart")}>
                    <RotateCcw size={14} /> Restart
                  </button>
                  <button onClick={() => action(app, "rollback")}>
                    <RotateCcw size={14} /> Roll back
                  </button>
                  <button onClick={() => showHistory(app)}>
                    <Clock3 size={14} /> History
                  </button>
                  <button title="Environment variables" onClick={() => setEnvApp(app)}>
                    <Settings2 size={14} />
                  </button>
                  <button className="danger-action" onClick={() => action(app, "delete")}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      {modal && (
        <DeployModal
          notify={notify}
          onClose={() => setModal(false)}
          onCreated={() => {
            setModal(false);
            load();
          }}
        />
      )}
      {envApp && (
        <EnvironmentModal
          app={envApp}
          notify={notify}
          onClose={() => setEnvApp(null)}
          onSaved={() => {
            setEnvApp(null);
            load();
          }}
        />
      )}
      {history && (
        <Modal title="Deployment history" onClose={() => setHistory(null)}>
          <div className="history-list">
            {history.length ? (
              history.map((h: any) => (
                <div key={h.id}>
                  <span className={`history-dot ${h.status}`} />
                  <div>
                    <strong>{h.message}</strong>
                    <small>
                      {new Date(h.created_at).toLocaleString()} · {h.image}
                    </small>
                  </div>
                </div>
              ))
            ) : (
              <Empty
                icon={Clock3}
                title="No deployment history"
                detail="A record will appear after the first deployment."
              />
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
export function DeploymentsPage({ notify }: { notify: Props["notify"] }) {
  const [items, setItems] = useState<any[]>([]),
    [busy, setBusy] = useState(true);
  const load = () => {
    setBusy(true);
    api<AppRecord[]>("/apps")
      .then(async (apps) => {
        const histories = await Promise.all(
          apps.map(async (app) => ({
            app,
            items: await api<any[]>(`/apps/${app.id}/deployments`).catch(() => []),
          })),
        );
        setItems(
          histories
            .flatMap((x) => x.items.map((deployment: any) => ({ ...deployment, app: x.app })))
            .sort((a, b) => b.created_at.localeCompare(a.created_at)),
        );
      })
      .catch((e) => notify(e.message, "error"))
      .finally(() => setBusy(false));
  };
  useEffect(load, []);
  async function rollback(app: AppRecord) {
    try {
      await api(`/apps/${app.id}/rollback`, { method: "POST" });
      notify(`${app.name} rolled back`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Rollback failed", "error");
    }
  }
  return (
    <div className="page-body">
      <Header
        kicker="DELIVERY / HISTORY"
        title="Deployments"
        description="Build records across your managed applications."
        action={
          <button className="button button-light" onClick={load}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <section className="panel data-panel">
        {busy ? (
          <div className="loading-line">
            <LoaderCircle size={17} className="spin" /> Loading deployment history…
          </div>
        ) : items.length === 0 ? (
          <Empty
            icon={Layers3}
            title="No deployments yet"
            detail="Successful builds and rollbacks will appear here."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>APPLICATION</th>
                  <th>RESULT</th>
                  <th>DETAIL</th>
                  <th>CREATED</th>
                  <th>IMAGE</th>
                  <th>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.app.name}</strong>
                    </td>
                    <td>
                      <span className={`badge ${item.status === "success" ? "badge-green" : "badge-red"}`}>
                        <i />
                        {item.status}
                      </span>
                    </td>
                    <td>{item.message}</td>
                    <td>{new Date(item.created_at).toLocaleString()}</td>
                    <td className="mono-cell">{item.image}</td>
                    <td>
                      <button className="row-action-button" onClick={() => rollback(item.app)}>
                        <RotateCcw size={13} /> Roll back
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
function parseEnvironment(input: string) {
  const values: Record<string, string> = {};
  for (const line of input.split("\n")) {
    const value = line.trim();
    if (!value || value.startsWith("#")) continue;
    const at = value.indexOf("=");
    if (at < 1) throw new Error(`Invalid environment entry: ${value}`);
    values[value.slice(0, at).trim()] = value.slice(at + 1);
  }
  return values;
}
function environmentText(input: Record<string, string>) {
  return Object.entries(input)
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
}
function DeployModal({
  notify,
  onClose,
  onCreated,
}: {
  notify: Props["notify"];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [tab, setTab] = useState("github"),
    [name, setName] = useState(""),
    [url, setUrl] = useState(""),
    [domain, setDomain] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [envText, setEnvText] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const environment = parseEnvironment(envText);
      if (tab === "github")
        await api("/apps/github", {
          method: "POST",
          body: JSON.stringify({ name, url, domain: domain || null, environment }),
        });
      else {
        if (!file) throw new Error("Choose a ZIP archive first");
        const data = new FormData();
        data.set("file", file);
        data.set("name", name);
        data.set("domain", domain);
        data.set("environment", JSON.stringify(environment));
        await api("/apps/zip", { method: "POST", body: data });
      }
      notify("Application deployed successfully");
      onCreated();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Deployment failed", "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Deploy an application" onClose={onClose}>
      <div className="source-tabs">
        <button className={tab === "github" ? "selected" : ""} onClick={() => setTab("github")}>
          <Code2 size={15} /> GitHub
        </button>
        <button className={tab === "zip" ? "selected" : ""} onClick={() => setTab("zip")}>
          <Upload size={15} /> ZIP upload
        </button>
      </div>
      <form className="modal-form" onSubmit={submit}>
        <label>
          Application name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-application"
            required
          />
        </label>
        {tab === "github" ? (
          <label>
            Repository URL
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              required
              type="url"
            />
          </label>
        ) : (
          <label>
            Source archive
            <input
              type="file"
              accept=".zip,application/zip"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              required
            />
          </label>
        )}
        <label>
          Domain <span className="optional-label">OPTIONAL</span>
          <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="app.example.com" />
        </label>
        <label>
          Environment variables <span className="optional-label">OPTIONAL · KEY=VALUE</span>
          <textarea
            className="env-textarea"
            value={envText}
            onChange={(e) => setEnvText(e.target.value)}
            placeholder={"DATABASE_URL=postgres://…\nAPP_SECRET=…"}
          />
        </label>
        <div className="deploy-detect">
          <Activity size={15} />
          <span>Framework detection and image build run automatically after deploy.</span>
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-light" onClick={onClose}>
            Cancel
          </button>
          <button className="button button-primary" disabled={busy}>
            {busy ? (
              <>
                <LoaderCircle size={15} className="spin" /> Building…
              </>
            ) : (
              "Build and deploy"
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function EnvironmentModal({
  app,
  notify,
  onClose,
  onSaved,
}: {
  app: AppRecord;
  notify: Props["notify"];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState<string | null>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ environment: Record<string, string> }>(`/apps/${app.id}/environment`)
      .then((x) => setText(environmentText(x.environment)))
      .catch((e) => notify(e.message, "error"));
  }, [app.id, notify]);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/apps/${app.id}/environment`, {
        method: "PUT",
        body: JSON.stringify({ environment: parseEnvironment(text || "") }),
      });
      notify("Environment saved and application restarted");
      onSaved();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not update environment", "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={`Environment · ${app.name}`} onClose={onClose}>
      <form className="modal-form" onSubmit={save}>
        <p className="form-hint">
          Saving replaces the container so the new variables take effect. Values are stored in the local
          application database.
        </p>
        <label>
          Environment variables
          <textarea
            className="env-textarea env-editor"
            value={text ?? ""}
            onChange={(e) => setText(e.target.value)}
            placeholder="KEY=value"
            disabled={text === null}
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="button button-light" onClick={onClose}>
            Cancel
          </button>
          <button className="button button-primary" disabled={busy || text === null}>
            {busy ? "Restarting…" : "Save and restart"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function DatabasesPage({ notify }: { notify: Props["notify"] }) {
  const [items, setItems] = useState<DatabaseRecord[]>([]),
    [modal, setModal] = useState(false),
    [loading, setLoading] = useState(true),
    [secret, setSecret] = useState<any>(null),
    [logs, setLogs] = useState("");
  const load = () => {
    setLoading(true);
    api<DatabaseRecord[]>("/databases")
      .then(setItems)
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  async function action(item: DatabaseRecord, act: string) {
    if (
      act === "delete" &&
      !window.confirm(`Delete the database container ${item.name}? Its data volume will be retained.`)
    )
      return;
    try {
      await api(`/databases/${item.id}/${act}`, { method: "POST" });
      notify(`${item.name} ${act} completed`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Action failed", "error");
    }
  }
  return (
    <div className="page-body">
      <Header
        kicker="DATA / DATABASES"
        title="Databases"
        description="Create and operate private database services on your server."
        action={
          <button className="button button-primary" onClick={() => setModal(true)}>
            <CirclePlus size={15} /> Create database
          </button>
        }
      />
      <div className="db-engine-grid">
        {[
          ["PostgreSQL", "Relational database", "5432", "#3265a8"],
          ["MySQL", "Relational database", "3306", "#cb862b"],
          ["Redis", "In-memory store", "6379", "#d64b42"],
        ].map(([a, b, c, d]) => (
          <div key={a} className="db-engine">
            <div style={{ color: d }}>
              <Database size={20} />
            </div>
            <div>
              <strong>{a}</strong>
              <span>{b}</span>
            </div>
            <small>{c}</small>
          </div>
        ))}
      </div>
      <section className="panel data-panel">
        {loading ? (
          <div className="loading-line">
            <LoaderCircle size={17} className="spin" /> Loading databases…
          </div>
        ) : items.length === 0 ? (
          <Empty
            icon={Database}
            title="No database services yet"
            detail="Create a PostgreSQL, MySQL, or Redis instance. Services stay on the private Docker network."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SERVICE</th>
                  <th>ENGINE</th>
                  <th>STATUS</th>
                  <th>INTERNAL HOST</th>
                  <th>CREATED</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {items.map((x) => (
                  <tr key={x.id}>
                    <td>
                      <div className="table-primary">
                        <div className="db-icon">
                          <Database size={15} />
                        </div>
                        <strong>{x.name}</strong>
                      </div>
                    </td>
                    <td>{x.engine}</td>
                    <td>
                      <span className={`badge ${x.status === "running" ? "badge-green" : "badge-gray"}`}>
                        <i />
                        {x.status}
                      </span>
                    </td>
                    <td className="mono-cell">
                      {x.connection_host || "private network"}:{x.port}
                    </td>
                    <td>{x.created_at ? new Date(x.created_at).toLocaleDateString() : "—"}</td>
                    <td>
                      <div className="row-actions">
                        {x.status === "running" ? (
                          <button title="Restart" onClick={() => action(x, "restart")}>
                            <RotateCcw size={15} />
                          </button>
                        ) : (
                          <button title="Start" onClick={() => action(x, "start")}>
                            <Play size={15} />
                          </button>
                        )}
                        <button
                          title="Logs"
                          onClick={() =>
                            api<{ logs: string }>(`/databases/${x.id}/logs`)
                              .then((r) => setLogs(r.logs))
                              .catch((e) => notify(e.message, "error"))
                          }
                        >
                          <FileText size={15} />
                        </button>
                        <button title="Delete" className="danger-action" onClick={() => action(x, "delete")}>
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {modal && (
        <DatabaseModal
          notify={notify}
          onClose={() => setModal(false)}
          onCreated={(x) => {
            setModal(false);
            setSecret(x);
            load();
          }}
        />
      )}
      {secret && (
        <Modal title="Database created" onClose={() => setSecret(null)}>
          <div className="credential-box">
            <div>
              <small>HOST</small>
              <strong>
                {secret.connection_host}:{secret.port}
              </strong>
            </div>
            <div>
              <small>USERNAME</small>
              <strong>{secret.username}</strong>
            </div>
            <div>
              <small>PASSWORD</small>
              <strong>{secret.password}</strong>
            </div>
            <p>Save these credentials now. The password is shown only once.</p>
          </div>
        </Modal>
      )}
      {logs !== "" && (
        <Modal title="Database logs" onClose={() => setLogs("")}>
          <pre className="log-output">{logs}</pre>
        </Modal>
      )}
    </div>
  );
}
function DatabaseModal({
  notify,
  onClose,
  onCreated,
}: {
  notify: Props["notify"];
  onClose: () => void;
  onCreated: (x: any) => void;
}) {
  const [name, setName] = useState(""),
    [engine, setEngine] = useState("postgresql"),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api<any>("/databases", { method: "POST", body: JSON.stringify({ name, engine }) });
      onCreated(result);
    } catch (x) {
      notify(x instanceof Error ? x.message : "Could not create database", "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Create a database" onClose={onClose}>
      <form className="modal-form" onSubmit={submit}>
        <label>
          Service name
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="primary-db" />
        </label>
        <label>
          Database engine
          <select value={engine} onChange={(e) => setEngine(e.target.value)}>
            <option value="postgresql">PostgreSQL 16</option>
            <option value="mysql">MySQL 8</option>
            <option value="redis">Redis 7</option>
          </select>
        </label>
        <div className="notice notice-neutral">
          A private Docker volume will persist database data. The service will not be exposed directly to the
          public network.
        </div>
        <div className="modal-actions">
          <button type="button" className="button button-light" onClick={onClose}>
            Cancel
          </button>
          <button className="button button-primary" disabled={busy}>
            {busy ? "Creating…" : "Create service"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function FilesPage({ notify }: { notify: Props["notify"] }) {
  const [path, setPath] = useState(""),
    [items, setItems] = useState<any[]>([]),
    [loading, setLoading] = useState(true),
    [folder, setFolder] = useState(false);
  const load = (p = path) => {
    setLoading(true);
    api<any[]>(`/files?path=${encodeURIComponent(p)}`)
      .then(setItems)
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load("");
  }, []);
  function enter(item: any) {
    if (item.directory) {
      setPath(item.path);
      load(item.path);
    }
  }
  async function remove(item: any) {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api(`/files?path=${encodeURIComponent(item.path)}`, { method: "DELETE" });
      notify(`${item.name} deleted`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not delete", "error");
    }
  }
  async function renameItem(item: any) {
    const name = window.prompt("New name", item.name);
    if (!name || name === item.name) return;
    try {
      await api("/files/rename", { method: "POST", body: JSON.stringify({ path: item.path, name }) });
      notify("Item renamed");
      load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not rename", "error");
    }
  }
  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    form.set("path", path);
    try {
      await api("/files/upload", { method: "POST", body: form });
      notify("File uploaded");
      load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Upload failed", "error");
    }
    e.target.value = "";
  }
  async function createFolder(e: FormEvent) {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).elements.namedItem("folder") as HTMLInputElement;
    const newPath = path ? `${path}/${input.value}` : input.value;
    try {
      await api("/files/folders", { method: "POST", body: JSON.stringify({ path: newPath }) });
      setFolder(false);
      notify("Folder created");
      load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not create folder", "error");
    }
  }
  return (
    <div className="page-body">
      <Header
        kicker="STORAGE / FILES"
        title="File manager"
        description="Manage files in Arfeen Cloud’s persistent storage area."
        action={
          <>
            <label className="button button-light upload-label">
              <Upload size={15} /> Upload
              <input type="file" onChange={upload} />
            </label>
            <button className="button button-primary" onClick={() => setFolder(true)}>
              <FolderPlus size={15} /> New folder
            </button>
          </>
        }
      />
      <div className="breadcrumb">
        <button
          onClick={() => {
            setPath("");
            load("");
          }}
        >
          Storage
        </button>
        {path
          .split("/")
          .filter(Boolean)
          .map((part, i, parts) => (
            <span key={i}>
              <ChevronRight size={14} />
              <button
                onClick={() => {
                  const p = parts.slice(0, i + 1).join("/");
                  setPath(p);
                  load(p);
                }}
              >
                {part}
              </button>
            </span>
          ))}
      </div>
      <section className="panel data-panel files-panel">
        {loading ? (
          <div className="loading-line">
            <LoaderCircle size={17} className="spin" /> Loading files…
          </div>
        ) : items.length === 0 ? (
          <Empty
            icon={Folder}
            title="This folder is empty"
            detail="Upload a file or create a new folder to begin."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>NAME</th>
                  <th>TYPE</th>
                  <th>SIZE</th>
                  <th>MODIFIED</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {items.map((x) => (
                  <tr key={x.path}>
                    <td>
                      <button className="file-name" onClick={() => enter(x)}>
                        {x.directory ? <Folder size={16} /> : <File size={16} />}
                        <strong>{x.name}</strong>
                      </button>
                    </td>
                    <td>{x.directory ? "Folder" : "File"}</td>
                    <td>{x.directory ? "—" : bytes(x.size)}</td>
                    <td>{new Date(x.modified * 1000).toLocaleString()}</td>
                    <td>
                      <div className="row-actions">
                        <button title="Rename" onClick={() => renameItem(x)}>
                          <Pencil size={14} />
                        </button>
                        {!x.directory && (
                          <a title="Download" href={`/api/files/download?path=${encodeURIComponent(x.path)}`}>
                            <ArrowDownToLine size={15} />
                          </a>
                        )}
                        <button title="Delete" className="danger-action" onClick={() => remove(x)}>
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="storage-note">
        <HardDrive size={14} /> Files are stored in the project’s persistent <code>storage/</code> directory.
      </div>
      {folder && (
        <Modal title="Create folder" onClose={() => setFolder(false)}>
          <form className="modal-form" onSubmit={createFolder}>
            <label>
              Folder name
              <input name="folder" required pattern="[^/\\]+" autoFocus placeholder="new-folder" />
            </label>
            <div className="modal-actions">
              <button type="button" className="button button-light" onClick={() => setFolder(false)}>
                Cancel
              </button>
              <button className="button button-primary">Create folder</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export function DockerResourcesPage({
  kind,
  notify,
}: {
  kind: "Images" | "Volumes" | "Networks";
  notify: Props["notify"];
}) {
  const [items, setItems] = useState<any[]>([]),
    [loading, setLoading] = useState(true);
  const url = kind.toLowerCase();
  const load = () => {
    setLoading(true);
    api<any[]>(`/docker/${url}`)
      .then(setItems)
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  async function remove(item: any) {
    const id = item.full_id || item.name;
    if (!window.confirm(`Remove ${item.tags?.[0] || item.name || item.id}?`)) return;
    try {
      await api(`/docker/${url}/${encodeURIComponent(id)}`, { method: "DELETE" });
      notify(`${kind.slice(0, -1)} removed`);
      load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Removal failed", "error");
    }
  }
  const titleMap: any = {
    Images: ["Images", "Build artifacts available to your Docker Engine."],
    Volumes: ["Volumes", "Persistent storage attached to Docker services."],
    Networks: ["Networks", "Private networks connecting workloads."],
  };
  return (
    <div className="page-body">
      <Header
        kicker={`RUNTIME / ${kind.toUpperCase()}`}
        title={titleMap[kind][0]}
        description={titleMap[kind][1]}
        action={
          <button className="button button-light" onClick={load}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <section className="panel data-panel">
        {loading ? (
          <div className="loading-line">
            <LoaderCircle size={17} className="spin" /> Loading {kind.toLowerCase()}…
          </div>
        ) : items.length === 0 ? (
          <Empty
            icon={kind === "Images" ? Image : kind === "Volumes" ? HardDrive : Network}
            title={`No ${kind.toLowerCase()} found`}
            detail="Docker Engine has no resources to show yet."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {(kind === "Images"
                    ? ["IMAGE", "SIZE", "CREATED", "ACTIONS"]
                    : kind === "Volumes"
                      ? ["VOLUME", "DRIVER", "CREATED", "ACTIONS"]
                      : ["NETWORK", "DRIVER", "SCOPE", "CONTAINERS"]
                  ).map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={item.id || item.name || i}>
                    {kind === "Images" ? (
                      <>
                        <td>
                          <div className="table-primary">
                            <Image size={16} />
                            <div>
                              <strong>{item.tags?.join(", ") || "<none>:<none>"}</strong>
                              <small>{item.id}</small>
                            </div>
                          </div>
                        </td>
                        <td>{bytes(item.size)}</td>
                        <td>{item.created ? new Date(item.created * 1000).toLocaleDateString() : "—"}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="danger-action"
                              title="Remove image"
                              onClick={() => remove(item)}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </td>
                      </>
                    ) : kind === "Volumes" ? (
                      <>
                        <td>
                          <strong>{item.name}</strong>
                        </td>
                        <td>{item.driver}</td>
                        <td>{item.created ? new Date(item.created).toLocaleDateString() : "—"}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="danger-action"
                              title="Remove volume"
                              disabled={item.system}
                              onClick={() => remove(item)}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>
                          <strong>{item.name}</strong>
                        </td>
                        <td>{item.driver}</td>
                        <td>{item.scope}</td>
                        <td>{item.containers}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export function LogsPage({ notify }: { notify: Props["notify"] }) {
  const [containers, setContainers] = useState<Container[]>([]),
    [id, setId] = useState(""),
    [logs, setLogs] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    api<Container[]>("/containers")
      .then((x) => {
        setContainers(x);
        if (x[0]) setId(x[0].id);
      })
      .catch((e) => notify(e.message, "error"));
  }, []);
  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api<{ logs: string }>(`/containers/${id}/logs?tail=400`)
      .then((x) => setLogs(x.logs))
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  }, [id]);
  const selected = containers.find((x) => x.id === id);
  return (
    <div className="page-body">
      <Header
        kicker="OBSERVABILITY / LOGS"
        title="Logs"
        description="Inspect recent output from your containers and services."
        action={
          <button
            className="button button-light"
            onClick={() => {
              if (id)
                api<{ logs: string }>(`/containers/${id}/logs?tail=400`)
                  .then((x) => setLogs(x.logs))
                  .catch((e) => notify(e.message, "error"));
            }}
          >
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <div className="log-toolbar">
        <label>
          Source
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">Choose container</option>
            {containers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <span className={`badge ${selected.status === "running" ? "badge-green" : "badge-gray"}`}>
            <i />
            {selected.status}
          </span>
        )}
      </div>
      <section className="log-viewer">
        <header>
          <span>
            <FileText size={14} />
            {selected?.name || "No container selected"}
          </span>
          <small>Last 400 lines</small>
        </header>
        <pre>{loading ? "Loading logs…" : logs || "No output to display."}</pre>
      </section>
    </div>
  );
}

export function SettingsPage({ notify }: { notify: Props["notify"] }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api("/settings")
      .then(setData)
      .catch((e) => notify(e.message, "error"));
  }, []);
  return (
    <div className="page-body">
      <Header
        kicker="SYSTEM / SETTINGS"
        title="Settings"
        description="Review your server identity and security posture."
      />
      <section className="settings-section">
        <div>
          <h2>Server</h2>
          <p>Host and runtime information for this Arfeen Cloud instance.</p>
        </div>
        <div className="panel settings-panel">
          <div>
            <span>Hostname</span>
            <strong>{data?.hostname || "Loading…"}</strong>
          </div>
          <div>
            <span>Operating system</span>
            <strong>{data?.platform || "—"}</strong>
          </div>
          <div>
            <span>Administrator</span>
            <strong>{data?.administrator || "—"}</strong>
          </div>
          <div>
            <span>File manager root</span>
            <strong>
              <code>{data?.storage_root || "/data/files"}</code>
            </strong>
          </div>
        </div>
      </section>
      <section className="settings-section">
        <div>
          <h2>Access and security</h2>
          <p>Current session and network access guidance.</p>
        </div>
        <div className="panel security-panel">
          <div className="security-mark">
            <Check size={16} />
          </div>
          <div>
            <strong>Single administrator enabled</strong>
            <p>Admin sessions use HTTP-only cookies with strict same-site settings.</p>
          </div>
        </div>
        <div className="notice notice-warning settings-warning">
          {data?.public_access ||
            "Before enabling public access, configure a domain, HTTPS termination, and secure cookies."}
        </div>
      </section>
      <section className="settings-section">
        <div>
          <h2>Future modules</h2>
          <p>Additional capabilities planned for this platform.</p>
        </div>
        <div className="future-tags">
          <span>Backup engine</span>
          <span>Notifications</span>
          <span>AI agents</span>
          <span>Plugin system</span>
          <span>Object storage</span>
          <span>Multi-server</span>
        </div>
      </section>
    </div>
  );
}

export function SimplePage({
  title,
  description,
  icon: Icon = Server,
}: {
  title: string;
  description: string;
  icon?: any;
}) {
  return (
    <div className="page-body">
      <Header kicker={`PLATFORM / ${title.toUpperCase()}`} title={title} description={description} />
      <section className="panel">
        <Empty
          icon={Icon}
          title={`${title} is ready for expansion`}
          detail="The navigation and modular API boundary are in place. This module will be added in a later release."
        />
      </section>
    </div>
  );
}
