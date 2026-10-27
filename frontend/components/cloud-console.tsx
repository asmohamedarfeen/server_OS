"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AppWindow,
  Box,
  ChevronDown,
  Cloud,
  Command,
  Database,
  FileText,
  Folder,
  HardDrive,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  Plug,
  Search,
  Server,
  Settings2,
  Shield,
  TerminalSquare,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { AppRecord, Container, DatabaseRecord, ServerMetrics } from "@/lib/types";
import AuthScreen from "./auth-screen";
import Overview from "./overview";
import TerminalPanel from "./terminal-panel";
import {
  ApplicationsPage,
  ContainersPage,
  DatabasesPage,
  DeploymentsPage,
  DockerResourcesPage,
  FilesPage,
  LogsPage,
  SettingsPage,
  SimplePage,
} from "./resource-pages";

const navGroups = [
  {
    label: "WORKSPACE",
    items: [
      { id: "Overview", icon: LayoutDashboard },
      { id: "Applications", icon: AppWindow },
      { id: "Deployments", icon: Layers3 },
    ],
  },
  {
    label: "INFRASTRUCTURE",
    items: [
      { id: "Containers", icon: Box },
      { id: "Images", icon: Layers3 },
      { id: "Volumes", icon: HardDrive },
      { id: "Networks", icon: Network },
      { id: "Databases", icon: Database },
    ],
  },
  {
    label: "OBSERVABILITY",
    items: [
      { id: "Storage", icon: Folder },
      { id: "Files", icon: Folder },
      { id: "Logs", icon: FileText },
      { id: "Monitoring", icon: Activity },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { id: "Terminal", icon: TerminalSquare },
      { id: "Settings", icon: Settings2 },
      { id: "Plugins", icon: Plug },
    ],
  },
];

export default function CloudConsole() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null),
    [active, setActive] = useState("Overview"),
    [metrics, setMetrics] = useState<ServerMetrics | null>(null),
    [history, setHistory] = useState<any[]>([]),
    [containers, setContainers] = useState<Container[]>([]),
    [apps, setApps] = useState<AppRecord[]>([]),
    [databases, setDatabases] = useState<DatabaseRecord[]>([]),
    [busy, setBusy] = useState(false),
    [sidebarOpen, setSidebarOpen] = useState(false),
    [toast, setToast] = useState<{ message: string; kind: string } | null>(null),
    [terminalTarget, setTerminalTarget] = useState<{ id: string; name: string } | null>(null);
  const notify = useCallback((message: string, kind: "success" | "error" = "success") => {
    setToast({ message, kind });
    window.setTimeout(() => setToast(null), 4200);
  }, []);
  const refresh = useCallback(async () => {
    setBusy(true);
    const [m, c, a, d] = await Promise.allSettled([
      api<ServerMetrics>("/server"),
      api<Container[]>("/containers"),
      api<AppRecord[]>("/apps"),
      api<DatabaseRecord[]>("/databases"),
    ]);
    if (m.status === "fulfilled") {
      setMetrics(m.value);
      setHistory((prev) =>
        [
          ...prev,
          {
            time: new Date().toLocaleTimeString([], { minute: "2-digit", second: "2-digit" }),
            cpu: m.value.cpu_percent,
            memory: m.value.memory.percent,
          },
        ].slice(-36),
      );
    }
    if (c.status === "fulfilled") setContainers(c.value);
    if (a.status === "fulfilled") setApps(a.value);
    if (d.status === "fulfilled") setDatabases(d.value);
    setBusy(false);
  }, []);
  useEffect(() => {
    api("/auth/me")
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    refresh();
    const timer = window.setInterval(refresh, 6000);
    return () => window.clearInterval(timer);
  }, [authenticated, refresh]);
  const subtitle = useMemo(
    () =>
      (
        ({
          Overview: "Your server at a glance",
          Applications: "Build and ship services",
          Deployments: "Build history and rollbacks",
          Containers: "Docker runtime",
          Images: "Docker runtime",
          Volumes: "Docker runtime",
          Networks: "Docker runtime",
          Databases: "Data services",
          Storage: "Persistent storage",
          Files: "Persistent storage",
          Logs: "Service output",
          Monitoring: "Live system metrics",
          Terminal: "Host administration",
          Settings: "Platform configuration",
          Plugins: "Platform extensions",
        }) as Record<string, string>
      )[active] || "Infrastructure",
    [active],
  );
  if (authenticated === null)
    return (
      <div className="boot-screen">
        <div className="boot-mark">
          <Cloud size={22} /> ARFEEN CLOUD
        </div>
        <span className="boot-loader" />
      </div>
    );
  if (!authenticated)
    return (
      <AuthScreen
        onAuthenticated={() => {
          setAuthenticated(true);
          refresh();
        }}
      />
    );
  function render() {
    switch (active) {
      case "Overview":
        return (
          <Overview
            metrics={metrics}
            history={history}
            containers={containers}
            apps={apps}
            databases={databases}
            loading={busy}
            refresh={refresh}
          />
        );
      case "Applications":
        return <ApplicationsPage notify={notify} />;
      case "Deployments":
        return <DeploymentsPage notify={notify} />;
      case "Containers":
        return (
          <ContainersPage
            notify={notify}
            onTerminal={(container) => {
              setTerminalTarget({ id: container.id, name: container.name });
              setActive("Terminal");
            }}
          />
        );
      case "Images":
        return <DockerResourcesPage kind="Images" notify={notify} />;
      case "Volumes":
      case "Storage":
        return <DockerResourcesPage kind="Volumes" notify={notify} />;
      case "Networks":
        return <DockerResourcesPage kind="Networks" notify={notify} />;
      case "Databases":
        return <DatabasesPage notify={notify} />;
      case "Files":
        return <FilesPage notify={notify} />;
      case "Logs":
        return <LogsPage notify={notify} />;
      case "Monitoring":
        return <MonitoringPage metrics={metrics} containers={containers} notify={notify} />;
      case "Terminal":
        return <TerminalPanel target={terminalTarget} />;
      case "Settings":
        return <SettingsPage notify={notify} />;
      case "Plugins":
        return (
          <SimplePage title="Plugins" description="Extend the platform with optional modules." icon={Plug} />
        );
      default:
        return (
          <Overview
            metrics={metrics}
            history={history}
            containers={containers}
            apps={apps}
            databases={databases}
            loading={busy}
            refresh={refresh}
          />
        );
    }
  }
  function select(id: string) {
    if (id === "Terminal") setTerminalTarget(null);
    setActive(id);
    setSidebarOpen(false);
  }
  return (
    <div className="console-shell">
      {sidebarOpen && (
        <button aria-label="Close menu" className="mobile-scrim" onClick={() => setSidebarOpen(false)} />
      )}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-symbol">
            <Cloud size={19} />
          </div>
          <div className="brand-type">
            <strong>
              ARFEEN <span>CLOUD</span>
            </strong>
            <small>PRIVATE INFRASTRUCTURE</small>
          </div>
          <button
            className="mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-select">
          <div className="workspace-avatar">A</div>
          <div>
            <strong>Personal server</strong>
            <span>Self-hosted workspace</span>
          </div>
          <ChevronDown size={14} />
        </div>
        <nav aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.items.map(({ id, icon: Icon }) => (
                <button
                  key={id}
                  className={`nav-item ${active === id ? "nav-active" : ""}`}
                  onClick={() => select(id)}
                >
                  <Icon size={16} strokeWidth={1.8} />
                  <span>{id}</span>
                  {id === "Applications" && apps.length > 0 && <small>{apps.length}</small>}
                  {id === "Containers" && containers.length > 0 && <small>{containers.length}</small>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="host-health">
            <div className="host-health-icon">
              <Activity size={15} />
            </div>
            <div>
              <strong>Host status</strong>
              <span>
                <i />
                {!metrics
                  ? "Connecting…"
                  : metrics.docker?.available
                    ? "All systems normal"
                    : "Docker offline"}
              </span>
            </div>
          </div>
          <div className="sidebar-user">
            <div className="user-avatar">A</div>
            <div>
              <strong>Administrator</strong>
              <span>Personal account</span>
            </div>
            <button
              onClick={async () => {
                await api("/auth/logout", { method: "POST" }).catch(() => {});
                setAuthenticated(false);
              }}
              aria-label="Sign out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
              <Menu size={19} />
            </button>
            <div className="breadcrumbs">
              <span>Cloud</span>
              <b>/</b>
              <strong>{active}</strong>
            </div>
          </div>
          <div className="topbar-right">
            <div className={`connection-state ${metrics ? "" : "connection-waiting"}`}>
              <i /> {metrics ? "SERVER CONNECTED" : "CONNECTING"}
            </div>
            <button className="topbar-search" onClick={() => select("Monitoring")}>
              <Search size={14} />
              <span>Search</span>
              <kbd>⌘ K</kbd>
            </button>
            <div className="topbar-divider" />
            <button className="topbar-help" title="Platform status">
              <Shield size={17} />
            </button>
            <div className="topbar-avatar">A</div>
          </div>
        </header>
        <div className="page-titlebar">
          <div>
            <h2>{active}</h2>
            <span>{subtitle}</span>
          </div>
          <div className="page-title-right">
            <span className="server-label">
              <Server size={13} />
              {metrics?.hostname || "Server"}
            </span>
            <span className="last-refresh">
              {busy ? (
                <>
                  <span className="refresh-pip" /> Updating
                </>
              ) : (
                "Auto-refresh · 6 sec"
              )}
            </span>
          </div>
        </div>
        {render()}
      </main>
      {toast && (
        <div className={`toast toast-${toast.kind}`} role="status">
          <span>{toast.kind === "success" ? "✓" : "!"}</span>
          {toast.message}
          <button onClick={() => setToast(null)} aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

function MonitoringPage({
  metrics,
  containers,
  notify,
}: {
  metrics: ServerMetrics | null;
  containers: Container[];
  notify: (message: string, kind?: "success" | "error") => void;
}) {
  const [processes, setProcesses] = useState<any[]>([]),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    api<any[]>("/processes")
      .then(setProcesses)
      .catch((e) => notify(e.message, "error"))
      .finally(() => setLoading(false));
  }, []);
  const rows = [
    ["CPU utilization", metrics ? `${metrics.cpu_percent.toFixed(1)}%` : "—"],
    [
      "Memory",
      metrics
        ? `${(metrics.memory.used / 1024 ** 3).toFixed(2)} GB / ${(metrics.memory.total / 1024 ** 3).toFixed(2)} GB`
        : "—",
    ],
    [
      "Disk usage",
      metrics
        ? `${(metrics.disk.used / 1024 ** 3).toFixed(1)} GB / ${(metrics.disk.total / 1024 ** 3).toFixed(1)} GB`
        : "—",
    ],
    ["Network receive", metrics ? `${(metrics.network.rx_bytes_sec / 1024).toFixed(1)} KB/s` : "—"],
    ["Network transmit", metrics ? `${(metrics.network.tx_bytes_sec / 1024).toFixed(1)} KB/s` : "—"],
    ["Server temperature", metrics?.temperature_c ? `${metrics.temperature_c} °C` : "Not reported"],
  ];
  return (
    <div className="page-body">
      <div className="monitor-metric-grid">
        {rows.slice(0, 3).map(([name, value], i) => (
          <div className="monitor-metric panel" key={name}>
            <span>{name}</span>
            <strong>{value}</strong>
            <div className="monitor-track">
              <i
                style={{
                  width: `${i === 0 ? metrics?.cpu_percent || 0 : i === 1 ? metrics?.memory.percent || 0 : metrics?.disk.percent || 0}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <section className="panel monitor-panel">
        <div className="panel-heading">
          <div>
            <h2>Server details</h2>
            <p>Current system readings</p>
          </div>
          <Activity size={16} />
        </div>
        <div className="detail-grid">
          {rows.map(([name, value]) => (
            <div key={name}>
              <span>{name}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="panel monitor-panel">
        <div className="panel-heading">
          <div>
            <h2>Running workloads</h2>
            <p>{containers.filter((c) => c.status === "running").length} active containers</p>
          </div>
        </div>
        <div className="compact-list">
          {containers.map((c) => (
            <div key={c.id} className="compact-row">
              <div className="container-symbol">
                <Box size={15} />
              </div>
              <div className="compact-primary">
                <strong>{c.name}</strong>
                <span>{c.image}</span>
              </div>
              <span className={`badge ${c.status === "running" ? "badge-green" : "badge-gray"}`}>
                <i />
                {c.status}
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel monitor-panel">
        <div className="panel-heading">
          <div>
            <h2>Top processes</h2>
            <p>Sorted by memory use</p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>PROCESS</th>
                <th>PID</th>
                <th>CPU</th>
                <th>MEMORY</th>
                <th>STATE</th>
              </tr>
            </thead>
            <tbody>
              {processes.slice(0, 12).map((p) => (
                <tr key={p.pid}>
                  <td>
                    <strong>{p.name || "—"}</strong>
                  </td>
                  <td>{p.pid}</td>
                  <td>{Number(p.cpu_percent || 0).toFixed(1)}%</td>
                  <td>{Number(p.memory_percent || 0).toFixed(2)}%</td>
                  <td>{p.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
