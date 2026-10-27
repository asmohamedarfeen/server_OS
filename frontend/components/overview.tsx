"use client";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Box,
  Cpu,
  HardDrive,
  MemoryStick,
  RefreshCw,
  Server,
  Thermometer,
  Wifi,
} from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { bytes, duration } from "@/lib/api";
import { AppRecord, Container, DatabaseRecord, ServerMetrics } from "@/lib/types";

function MetricCard({ label, value, detail, icon: Icon, percent, tone = "blue" }: any) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <div className={`metric-icon ${tone}`}>
          <Icon size={17} />
        </div>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
      {percent !== undefined && (
        <div className="meter">
          <span className={percent > 85 ? "danger" : ""} style={{ width: `${Math.min(percent, 100)}%` }} />
        </div>
      )}
    </div>
  );
}

export default function Overview({
  metrics,
  history,
  containers,
  apps,
  databases,
  loading,
  refresh,
}: {
  metrics: ServerMetrics | null;
  history: any[];
  containers: Container[];
  apps: AppRecord[];
  databases: DatabaseRecord[];
  loading: boolean;
  refresh: () => void;
}) {
  const running = containers.filter((c) => c.status === "running").length;
  const activeApps = apps.filter((a) => a.status === "running").length;
  return (
    <div className="page-body overview-page">
      <div className="welcome-row">
        <div>
          <p className="page-kicker">INFRASTRUCTURE / OVERVIEW</p>
          <h1>Good to see you.</h1>
          <p className="muted">Here’s what’s happening across your server right now.</p>
        </div>
        <button className="button button-light" onClick={refresh}>
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      <div className="server-strip">
        <div className="server-avatar">
          <Server size={19} />
        </div>
        <div className="server-name">
          <strong>{metrics?.hostname || "Connecting to server"}</strong>
          <span>{metrics?.platform || "Waiting for host metrics"}</span>
        </div>
        <div className="server-uptime">
          <span className="status-pip" /> ONLINE <small>UP {duration(metrics?.uptime_seconds)}</small>
        </div>
        <div className="server-updated">
          Updated{" "}
          {metrics?.timestamp
            ? new Date(metrics.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })
            : "—"}
        </div>
      </div>
      {!metrics && !loading && (
        <div className="notice notice-warning">
          The API could not read server metrics. Check the backend connection and Docker Engine status.
        </div>
      )}
      <div className="metric-grid">
        <MetricCard
          label="Processor"
          value={`${Math.round(metrics?.cpu_percent || 0)}%`}
          detail={`${metrics?.cpu_count ?? "—"} logical cores`}
          icon={Cpu}
          percent={metrics?.cpu_percent}
        />
        <MetricCard
          label="Memory"
          value={`${Math.round(metrics?.memory.percent || 0)}%`}
          detail={`${bytes(metrics?.memory.used)} of ${bytes(metrics?.memory.total)}`}
          icon={MemoryStick}
          percent={metrics?.memory.percent}
          tone="green"
        />
        <MetricCard
          label="Storage"
          value={`${Math.round(metrics?.disk.percent || 0)}%`}
          detail={`${bytes(metrics?.disk.used)} of ${bytes(metrics?.disk.total)}`}
          icon={HardDrive}
          percent={metrics?.disk.percent}
          tone="amber"
        />
        <MetricCard
          label="Network"
          value={`${bytes(metrics?.network.rx_bytes_sec)}/s`}
          detail={`↑ ${bytes(metrics?.network.tx_bytes_sec)}/s outbound`}
          icon={Wifi}
          tone="violet"
        />
      </div>
      <div className="overview-main-grid">
        <section className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <h2>Resource activity</h2>
              <p>Live CPU and memory utilization</p>
            </div>
            <span className="live-tag">
              <i /> LIVE
            </span>
          </div>
          <div className="chart-legend">
            <span>
              <i className="legend-blue" /> CPU
            </span>
            <span>
              <i className="legend-green" /> MEMORY
            </span>
            <small>Last 5 minutes</small>
          </div>
          <div className="chart-wrap">
            {history.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history} margin={{ top: 8, right: 10, left: -26, bottom: 0 }}>
                  <defs>
                    <linearGradient id="cpuFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#316bea" stopOpacity={0.16} />
                      <stop offset="100%" stopColor="#316bea" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="memFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#24a67a" stopOpacity={0.14} />
                      <stop offset="100%" stopColor="#24a67a" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#edf0f4" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 10, fill: "#97a1b0" }}
                    minTickGap={28}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 10, fill: "#97a1b0" }}
                    ticks={[0, 25, 50, 75, 100]}
                  />
                  <Tooltip contentStyle={{ border: "1px solid #e8ebf0", borderRadius: 8, fontSize: 12 }} />
                  <Area
                    type="monotone"
                    dataKey="cpu"
                    stroke="#316bea"
                    fill="url(#cpuFill)"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="memory"
                    stroke="#24a67a"
                    fill="url(#memFill)"
                    strokeWidth={2}
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">
                <Activity size={20} />
                <span>Collecting live server samples…</span>
              </div>
            )}
          </div>
          <div className="chart-foot">
            <span>
              <Activity size={13} /> {metrics?.process_count ?? "—"} processes
            </span>
            <span>
              <Thermometer size={13} />{" "}
              {metrics?.temperature_c ? `${metrics.temperature_c}°C` : "Temperature unavailable"}
            </span>
            <span>Load {metrics?.load_average?.map((x) => Number(x).toFixed(2)).join(" / ") || "—"}</span>
          </div>
        </section>
        <section className="panel stack-panel">
          <div className="panel-heading">
            <div>
              <h2>Runtime status</h2>
              <p>Docker and managed services</p>
            </div>
            <Box size={17} className="subtle-icon" />
          </div>
          <div className="runtime-engine">
            <div className="docker-mark">▰</div>
            <div>
              <strong>Docker Engine</strong>
              <span>{metrics?.docker?.available ? `Version ${metrics.docker.version}` : "Unavailable"}</span>
            </div>
            <span className={`badge ${metrics?.docker?.available ? "badge-green" : "badge-red"}`}>
              {metrics?.docker?.available ? "Connected" : "Offline"}
            </span>
          </div>
          <div className="runtime-stat">
            <span>Running containers</span>
            <strong>
              {running}
              <small> / {containers.length}</small>
            </strong>
          </div>
          <div className="runtime-stat">
            <span>Applications online</span>
            <strong>
              {activeApps}
              <small> / {apps.length}</small>
            </strong>
          </div>
          <div className="runtime-stat">
            <span>Database services</span>
            <strong>
              {databases.filter((d) => d.status === "running").length}
              <small> / {databases.length}</small>
            </strong>
          </div>
          <div className="runtime-bottom">
            <span>
              <span className="status-pip" /> All systems operational
            </span>
            <span>{containers.length} total</span>
          </div>
        </section>
      </div>
      <div className="overview-bottom-grid">
        <section className="panel list-panel">
          <div className="panel-heading">
            <div>
              <h2>Containers</h2>
              <p>Recent Docker workloads</p>
            </div>
            <span className="panel-count">{containers.length}</span>
          </div>
          {containers.length ? (
            <div className="compact-list">
              {containers.slice(0, 5).map((c) => (
                <div className="compact-row" key={c.id}>
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
          ) : (
            <div className="empty-inline">
              <Box size={18} />
              <span>No containers yet</span>
            </div>
          )}
        </section>
        <section className="panel list-panel">
          <div className="panel-heading">
            <div>
              <h2>Applications</h2>
              <p>Deployments managed by Arfeen</p>
            </div>
            <span className="panel-count">{apps.length}</span>
          </div>
          {apps.length ? (
            <div className="compact-list">
              {apps.slice(0, 5).map((a) => (
                <div className="compact-row" key={a.id}>
                  <div className="app-monogram">{a.name.slice(0, 1).toUpperCase()}</div>
                  <div className="compact-primary">
                    <strong>{a.name}</strong>
                    <span>
                      {a.framework} · {a.domain || "Port " + a.port}
                    </span>
                  </div>
                  <span className={`badge ${a.status === "running" ? "badge-green" : "badge-red"}`}>
                    <i />
                    {a.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-inline">
              <Activity size={18} />
              <span>Deploy your first application</span>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
