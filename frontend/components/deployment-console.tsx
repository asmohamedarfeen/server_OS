"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowDownToLine, Check, CheckCircle2, Clock3, Copy, GitBranch, LoaderCircle, TerminalSquare, X } from "lucide-react";
import { api } from "@/lib/api";

export type DeploymentJob = {
  id: string; name: string; source: string; ref: string;
  status: "queued" | "running" | "success" | "failed" | "interrupted";
  stage: string; message: string; created_at: string; started_at?: string; finished_at?: string;
  result?: { id: string; url?: string; name?: string; framework?: string; host_port?: number; domain?: string };
};
type LogLine = { id: number; created_at: string; stage: string; level: string; message: string };
type JobDetails = DeploymentJob & { logs: LogLine[]; next_cursor: number; has_more: boolean };
const stages = [
  { key: "queued", title: "Queued", detail: "Reserve a build worker" },
  { key: "clone", title: "Source", detail: "Fetch repository or unpack ZIP" },
  { key: "detect", title: "Configure", detail: "Detect framework and container port" },
  { key: "build", title: "Build image", detail: "Install dependencies and compile" },
  { key: "deploy", title: "Deploy", detail: "Start the application container" },
  { key: "verify", title: "Verify", detail: "Check container startup" },
];
const active = (job: DeploymentJob) => job.status === "queued" || job.status === "running";

function elapsed(job: DeploymentJob, time: number) {
  const seconds = Math.max(0, Math.floor(((job.finished_at ? Date.parse(job.finished_at) : time) - Date.parse(job.started_at || job.created_at)) / 1000));
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`;
}

export function DeploymentConsole({ jobId, onClose, onFinished }: {
  jobId: string; onClose: () => void; onFinished?: () => void;
}) {
  const [job, setJob] = useState<DeploymentJob | null>(null);
  const [lines, setLines] = useState<LogLine[]>([]);
  const [error, setError] = useState("");
  const [follow, setFollow] = useState(true);
  const [copied, setCopied] = useState(false);
  const [time, setTime] = useState(Date.now());
  const scroll = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  useEffect(() => {
    let stopped = false, cursor = 0, notified = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<JobDetails>(`/deployment-jobs/${jobId}?after=${cursor}`);
        if (stopped) return;
        setJob(data);
        setError("");
        if (data.logs.length) setLines((previous) => [...previous, ...data.logs].slice(-2000));
        cursor = data.next_cursor;
        if (!active(data) && !data.has_more) {
          if (!notified) { notified = true; finished.current?.(); }
          return;
        }
        timer = setTimeout(poll, data.has_more ? 50 : 1500);
      } catch (e) {
        if (stopped) return;
        setError(e instanceof Error ? e.message : "Connection lost");
        timer = setTimeout(poll, 4000);
      }
    }
    poll();
    const ticker = setInterval(() => setTime(Date.now()), 1000);
    return () => { stopped = true; clearTimeout(timer); clearInterval(ticker); };
  }, [jobId]);

  useEffect(() => {
    if (follow && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [lines, follow]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    return () => { document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, []);

  const failed = job?.status === "failed" || job?.status === "interrupted";
  const current = job?.status === "success" ? stages.length : Math.max(0, stages.findIndex((s) => s.key === job?.stage));
  async function copyLogs() {
    try {
      const response = await fetch(`/api/deployment-jobs/${jobId}/logs`, { credentials: "include" });
      if (!response.ok) throw new Error("Could not download logs");
      await navigator.clipboard.writeText(await response.text());
      setCopied(true);
    } catch { setError("Could not copy logs. Use Download logs instead."); }
  }

  return <div className="deployment-backdrop">
    <section className="deployment-console" ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="deployment-console-title"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        if (event.key !== "Tab") return;
        const nodes = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, [tabindex="0"]');
        if (!nodes?.length) return;
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}>
      <header className="deployment-console-heading">
        <div className="deployment-console-icon"><TerminalSquare size={21} /></div>
        <div className="deployment-console-title"><p>DEPLOYMENT WORKSPACE</p><h2 id="deployment-console-title">{job?.name || "Connecting to deployment…"}</h2></div>
        <span className={`deployment-status ${job?.status || "queued"}`} aria-live="polite">
          {job?.status === "success" ? <CheckCircle2 size={14} /> : failed ? <AlertCircle size={14} /> : <LoaderCircle className="spin" size={14} />}
          {job?.status === "success" ? "Deployed" : job?.status === "running" ? "In progress" : job?.status || "Connecting"}
        </span>
        <button className="icon-button" aria-label="Close deployment logs" onClick={onClose}><X size={19} /></button>
      </header>
      <div className="deployment-source"><GitBranch size={14} /><span title={job?.source}>{job?.source || "Loading source…"}</span><b>{job?.ref || "default"}</b><span className="deployment-elapsed"><Clock3 size={13} />{job ? elapsed(job, time) : "—"}</span></div>
      <div className="deployment-workspace">
        <aside className="deployment-stages" aria-label="Deployment stages">
          {stages.map((stage, index) => {
            const done = index < current, isCurrent = index === current;
            return <div key={stage.key} className={`deployment-stage ${done ? "done" : ""} ${isCurrent ? failed ? "failed" : "current" : ""}`} aria-current={isCurrent ? "step" : undefined}>
              <span className="deployment-stage-marker">{done ? <Check size={13} /> : isCurrent && !failed ? <LoaderCircle size={13} className={job && active(job) ? "spin" : ""} /> : failed && isCurrent ? <X size={13} /> : index + 1}</span>
              <div><strong>{stage.title}</strong><small>{stage.detail}</small></div>
            </div>;
          })}
          <p className="deployment-stage-note">You can close this view. The build continues on your server.</p>
        </aside>
        <main className="deployment-output">
          <div className="deployment-output-toolbar"><span><i className={job && active(job) ? "live" : ""} />BUILD OUTPUT</span><label><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow logs</label></div>
          {error && <div className="deployment-connection-warning" role="alert">{error}. Reconnecting automatically; the server job continues.</div>}
          <div className="deployment-log" ref={scroll} role="log" aria-label="Deployment build output" aria-live="off" tabIndex={0}>
            {!lines.length && <p className="deployment-log-empty">{job?.status === "queued" ? "Waiting for the current build to finish. Your deployment is safely queued." : "Connecting to the build worker…"}</p>}
            {lines.map((line) => <div className={`deployment-log-line ${line.level}`} key={line.id}><time dateTime={line.created_at}>{new Date(line.created_at).toLocaleTimeString("en-GB", { hour12: false })}</time><pre>{line.message}</pre></div>)}
          </div>
          <div className={`deployment-result ${failed ? "failed" : job?.status === "success" ? "success" : ""}`} role="status">
            {failed ? <AlertCircle size={16} /> : job?.status === "success" ? <CheckCircle2 size={16} /> : <TerminalSquare size={16} />}
            <span>{job?.message || "Loading deployment details…"}{lines.length >= 2000 && " · Showing latest 2,000 entries; download for complete output."}</span>
          </div>
        </main>
      </div>
      <footer className="deployment-console-footer"><span>#{jobId.slice(0, 8)} · Saved on your server</span><div>
        {job?.status === "success" && (job.result?.domain || job.result?.host_port) && <a className="button button-light" target="_blank" rel="noreferrer" href={job.result.domain ? `http://${job.result.domain}` : `http://${window.location.hostname}:${job.result.host_port}`}>Open application ↗</a>}
        <button className="button button-light" onClick={copyLogs}><Copy size={14} />{copied ? "Copied" : "Copy logs"}</button>
        <a className="button button-light" href={`/api/deployment-jobs/${jobId}/logs`} download><ArrowDownToLine size={14} />Download logs</a>
        <button className="button button-primary" onClick={onClose}>{job && active(job) ? "Continue in background" : "Done"}</button>
      </div></footer>
    </section>
  </div>;
}

export function DeploymentJobsPanel({ onOpen, refreshKey = 0, onFinished }: { onOpen: (id: string) => void; refreshKey?: number; onFinished?: () => void }) {
  const [jobs, setJobs] = useState<DeploymentJob[]>([]);
  const [error, setError] = useState("");
  const finished = useRef(onFinished);
  finished.current = onFinished;
  useEffect(() => {
    let stopped = false;
    const known = new Map<string, string>();
    async function load() {
      try {
        const data = await api<DeploymentJob[]>("/deployment-jobs");
        if (!stopped) {
          const completed = data.some((job) => !active(job) && known.get(job.id) !== job.status);
          data.forEach((job) => known.set(job.id, job.status));
          setJobs(data); setError("");
          if (completed) finished.current?.();
        }
      }
      catch { if (!stopped) setError("Could not load deployment jobs. Retrying…"); }
    }
    load();
    const timer = setInterval(load, 4000);
    return () => { stopped = true; clearInterval(timer); };
  }, [refreshKey]);
  return <section className="panel deployment-jobs-panel" aria-label="Recent build jobs">
    <header><div><TerminalSquare size={17} /><h2>Build activity</h2></div><span>Live · refreshes automatically</span></header>
    {error && <p className="deployment-jobs-empty" role="status">{error}</p>}
    {!jobs.length && !error ? <p className="deployment-jobs-empty">Your next deployment will appear here with live build output.</p> : <div className="deployment-job-list">{jobs.slice(0, 20).map((job) => <button className="deployment-job-row" key={job.id} onClick={() => onOpen(job.id)}>
      <span className={`deployment-status ${job.status}`}>{active(job) ? <LoaderCircle size={13} className="spin" /> : job.status === "success" ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}{job.status}</span>
      <span className="deployment-job-name"><strong>{job.name}</strong><small>{job.ref || "default branch"} · #{job.id.slice(0, 8)}</small></span>
      <span className="deployment-job-message">{job.message}</span><time>{new Date(job.created_at).toLocaleString()}</time><span className="deployment-open-label">View logs →</span>
    </button>)}</div>}
  </section>;
}
