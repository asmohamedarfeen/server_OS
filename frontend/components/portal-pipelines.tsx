"use client";
import { FormEvent, useRef, useState } from "react";
import {
  ArrowDownToLine,
  Check,
  GitBranch,
  Layers3,
  Play,
  Plus,
  Settings2,
  Square,
  Upload,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { AppRecord } from "@/lib/types";
import {
  CommandBar,
  ConfirmDialog,
  dateTime,
  EmptyState,
  ErrorNotice,
  href,
  itemsOf,
  Loading,
  Notify,
  PageHeading,
  PortalRoute,
  Properties,
  Refresh,
  ResourceWorkspace,
  Status,
  useResource,
} from "./portal-shared";

type Pipeline = {
  id: string;
  name: string;
  app_id: string;
  app_name?: string;
  enabled: boolean;
  test_command: string;
  test_timeout: number;
  poll_enabled: boolean;
  last_commit?: string;
  last_poll_at?: string;
  poll_error?: string;
  source_type?: string;
  source?: string;
  source_ref?: string;
};
export function PortalPipelines({
  route,
  apps,
  notify,
}: {
  route: PortalRoute;
  apps: AppRecord[];
  notify: Notify;
}) {
  const list = useResource<Pipeline[]>("/pipelines"),
    detail = useResource<Pipeline>(route.id ? `/pipelines/${route.id}` : null),
    runs = useResource<any[]>(route.id ? `/pipelines/${route.id}/runs` : null);
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false),
    [query, setQuery] = useState("");
  const zip = useRef<HTMLInputElement>(null),
    pipeline = detail.data;
  const refresh = () => {
    list.refresh();
    detail.refresh();
    runs.refresh();
  };
  async function run(file?: File) {
    if (!pipeline) return;
    const app = apps.find((a) => a.id === pipeline.app_id);
    if ((pipeline.source_type === "zip" || app?.source_type === "zip") && !file) {
      zip.current?.click();
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      if (file) form.set("file", file);
      const queued = await api(`/pipelines/${pipeline.id}/${file ? "run-zip" : "run"}`, {
        method: "POST",
        ...(file ? { body: form } : {}),
      });
      window.location.hash = href("pipelines", pipeline.id, `run:${queued.id}`);
      refresh();
      notify("Pipeline run queued");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Could not run pipeline", "error");
    } finally {
      setBusy(false);
    }
  }
  if (!route.id)
    return (
      <>
        <div className="az-page">
          <PageHeading title="Pipelines" subtitle="Build, test, and deploy using the local agent" />
        </div>
        <CommandBar>
          <button onClick={() => setEditing(true)}>
            <Plus size={16} />
            New pipeline
          </button>
          <Refresh onClick={list.refresh} />
        </CommandBar>
        <div className="az-page">
          <div className="az-notice">
            <GitBranch size={17} />
            One local build agent. Runs queue automatically so builds do not compete for the same server.
          </div>
          <ErrorNotice error={list.error} retry={list.refresh} />
          <div className="az-filter-bar">
            <input
              aria-label="Filter pipelines"
              placeholder="Filter pipelines"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <span>{itemsOf(list.data).length} pipelines</span>
          </div>
          {list.loading ? (
            <Loading />
          ) : (
            <div className="az-table-wrap">
              <table className="az-table">
                <thead>
                  <tr>
                    <th>Pipeline</th>
                    <th>Application</th>
                    <th>Source</th>
                    <th>Trigger</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {itemsOf(list.data)
                    .filter((p) => p.name.toLowerCase().includes(query.toLowerCase()))
                    .map((p) => (
                      <tr key={p.id}>
                        <td>
                          <a className="az-resource-link" href={href("pipelines", p.id)}>
                            <Layers3 size={17} />
                            {p.name}
                          </a>
                        </td>
                        <td>
                          <a href={href("apps", p.app_id)}>
                            {p.app_name || apps.find((a) => a.id === p.app_id)?.name || p.app_id}
                          </a>
                        </td>
                        <td>
                          {p.source_type === "zip"
                            ? "ZIP upload"
                            : `GitHub · ${p.source_ref || "Default branch"}`}
                        </td>
                        <td>{p.poll_enabled ? "GitHub branch polling" : "Manual"}</td>
                        <td>
                          <Status value={p.enabled ? "active" : "disabled"} />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {!itemsOf(list.data).length && (
                <EmptyState
                  title="Create your first pipeline"
                  detail="Link a deployed application, configure an optional container test, and run a repeatable build and release workflow."
                />
              )}
            </div>
          )}
        </div>
        {editing && (
          <PipelineForm
            apps={apps}
            onClose={() => setEditing(false)}
            onSaved={(p) => {
              setEditing(false);
              list.refresh();
              window.location.hash = href("pipelines", p.id);
            }}
            notify={notify}
          />
        )}
      </>
    );
  if (!pipeline)
    return (
      <div className="az-page">
        <ErrorNotice error={detail.error} retry={detail.refresh} />
        {detail.loading ? <Loading /> : <EmptyState title="Pipeline not found" />}
      </div>
    );
  return (
    <>
      <ResourceWorkspace
        title={pipeline.name}
        type="Pipeline"
        route={{ ...route, tab: route.tab.startsWith("run:") ? "runs" : route.tab }}
        icon={<GitBranch size={30} />}
        status={pipeline.enabled ? "active" : "disabled"}
        tabs={["Overview", "Runs", "Settings"]}
        commands={
          <>
            <button disabled={busy || !pipeline.enabled} onClick={() => run()}>
              <Play size={15} />
              Run pipeline
            </button>
            <button onClick={() => setEditing(true)}>
              <Settings2 size={15} />
              Edit pipeline
            </button>
            <Refresh onClick={refresh} />
            <a href={href("apps", pipeline.app_id)}>Open application</a>
          </>
        }
      >
        <ErrorNotice error={detail.error || runs.error} retry={refresh} />
        {route.tab.startsWith("run:") ? (
          <PipelineRun
            runId={route.tab.slice(4)}
            pipeline={pipeline}
            notify={notify}
            onRetry={() => run()}
            busy={busy}
          />
        ) : route.tab === "settings" ? (
          <>
            <h2>Pipeline settings</h2>
            <PipelineConfiguration pipeline={pipeline} />
            <button className="az-button" onClick={() => setEditing(true)}>
              Edit configuration
            </button>
          </>
        ) : (
          <>
            <div className="az-section-heading">
              <h2>{route.tab === "runs" ? "Runs" : "Overview"}</h2>
              <span>Local Docker agent</span>
            </div>
            {route.tab !== "runs" && (
              <>
                <PipelineConfiguration pipeline={pipeline} />
                <div className="az-pipeline-flow" aria-label="Pipeline stages">
                  {["Source", "Configure", "Build", "Test", "Deploy", "Verify"].map((s, i) => (
                    <span key={s}>
                      <i>{i + 1}</i>
                      {s}
                    </span>
                  ))}
                </div>
                <div className="az-section-heading">
                  <h2>Recent runs</h2>
                </div>
              </>
            )}
            <RunTable runs={itemsOf(runs.data)} pipelineId={pipeline.id} />
          </>
        )}
      </ResourceWorkspace>
      <input
        ref={zip}
        hidden
        type="file"
        accept=".zip"
        onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          if (file) run(file);
          e.currentTarget.value = "";
        }}
      />
      {editing && (
        <PipelineForm
          pipeline={pipeline}
          apps={apps}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            refresh();
          }}
          notify={notify}
        />
      )}
    </>
  );
}
function PipelineConfiguration({ pipeline: p }: { pipeline: Pipeline }) {
  return (
    <>
      <Properties
        rows={[
          ["Application", <a href={href("apps", p.app_id)}>{p.app_name || p.app_id}</a>],
          ["Source", p.source || p.source_type],
          ["Branch", p.source_ref || "Default branch"],
          ["Test command", p.test_command || "Not configured · test stage skipped"],
          ["Test timeout", `${p.test_timeout} seconds`],
          ["Trigger", p.poll_enabled ? "GitHub branch polling · every 60 seconds" : "Manual"],
          ["Last poll", dateTime(p.last_poll_at)],
          ["Last observed commit", p.last_commit || "—"],
        ]}
      />
      <ErrorNotice error={p.poll_error} />
    </>
  );
}
function RunTable({ runs, pipelineId }: { runs: any[]; pipelineId: string }) {
  return (
    <div className="az-table-wrap">
      <table className="az-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Trigger</th>
            <th>Commit / image</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <a href={href("pipelines", pipelineId, `run:${r.id}`)}>{r.id.slice(0, 8)}</a>
              </td>
              <td>
                <Status value={r.status} />
              </td>
              <td>{r.trigger || "Manual"}</td>
              <td className="az-truncate">{r.commit?.slice(0, 12) || r.image || "—"}</td>
              <td>{dateTime(r.started_at || r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!runs.length && (
        <EmptyState
          title="No runs yet"
          detail="Run this pipeline to build an image, execute configured tests, and deploy to the linked application."
        />
      )}
    </div>
  );
}
function PipelineForm({
  pipeline,
  apps,
  onClose,
  onSaved,
  notify,
}: {
  pipeline?: Pipeline;
  apps: AppRecord[];
  onClose: () => void;
  onSaved: (pipeline: Pipeline) => void;
  notify: Notify;
}) {
  const [name, setName] = useState(pipeline?.name || ""),
    [appId, setAppId] = useState(pipeline?.app_id || apps[0]?.id || ""),
    [test, setTest] = useState(pipeline?.test_command || ""),
    [timeout, setTimeoutValue] = useState(pipeline?.test_timeout || 300),
    [poll, setPoll] = useState(pipeline?.poll_enabled || false),
    [enabled, setEnabled] = useState(pipeline?.enabled ?? true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const selected = apps.find((a) => a.id === appId);
  async function save() {
    setBusy(true);
    setError("");
    try {
      if (!name.trim() || !appId) throw new Error("Enter a name and select an application");
      const p = await api<Pipeline>(pipeline ? `/pipelines/${pipeline.id}` : "/pipelines", {
        method: pipeline ? "PATCH" : "POST",
        body: JSON.stringify({
          name,
          ...(pipeline ? {} : { app_id: appId }),
          test_command: test,
          test_timeout: timeout,
          poll_enabled: poll,
          enabled,
        }),
      });
      notify("Pipeline saved");
      onSaved(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save pipeline");
    } finally {
      setBusy(false);
    }
  }
  return (
    <ConfirmDialog
      title={pipeline ? "Edit pipeline" : "New pipeline"}
      confirmLabel="Save pipeline"
      busy={busy}
      onConfirm={save}
      onClose={onClose}
    >
      <ErrorNotice error={error} />
      <div className="az-form">
        <label>
          Pipeline name
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
        </label>
        <label>
          Application
          <select
            value={appId}
            disabled={!!pipeline}
            onChange={(e) => {
              setAppId(e.target.value);
              setPoll(false);
            }}
          >
            {!apps.length && <option value="">Deploy an application first</option>}
            {apps.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Test command (optional)
          <input placeholder="npm test or pytest" value={test} onChange={(e) => setTest(e.target.value)} />
        </label>
        <p className="az-muted">
          Runs inside a temporary container from the built image. A failing test prevents deployment.
        </p>
        <label>
          Test timeout (seconds)
          <input
            type="number"
            min={1}
            max={3600}
            value={timeout}
            onChange={(e) => setTimeoutValue(Number(e.target.value))}
          />
        </label>
        <label className="az-checkbox">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Pipeline enabled
        </label>
        <label className="az-checkbox">
          <input
            type="checkbox"
            checked={poll}
            disabled={selected?.source_type === "zip"}
            onChange={(e) => setPoll(e.target.checked)}
          />
          Automatically run when the GitHub branch changes
        </label>
        <p className="az-muted">
          Private branch polling uses your saved GitHub connection and does not require a public webhook. ZIP
          deployments always use manual runs.
        </p>
      </div>
    </ConfirmDialog>
  );
}
function PipelineRun({
  runId,
  pipeline,
  notify,
  onRetry,
  busy,
}: {
  runId: string;
  pipeline: Pipeline;
  notify: Notify;
  onRetry: () => void;
  busy: boolean;
}) {
  const state = useResource<any>(`/pipelines/runs/${runId}`, 2000),
    [selected, setSelected] = useState("all"),
    [cancelling, setCancelling] = useState(false);
  const stageOutput = useResource<any>(
    selected !== "all" ? `/pipelines/runs/${runId}?stage=${encodeURIComponent(selected)}` : null,
    2000,
  );
  const run = state.data,
    fallback = useResource<any>(
      run?.job_id && !Array.isArray(run.logs) ? `/deployment-jobs/${run.job_id}` : null,
      2000,
    );
  const labels: Record<string, string> = {
    clone: "Source",
    source: "Source",
    detect: "Configure",
    configure: "Configure",
    build: "Build",
    test: "Test",
    deploy: "Deploy",
    verify: "Verify",
  };
  if (!run)
    return (
      <>
        <ErrorNotice error={state.error} retry={state.refresh} />
        <Loading />
      </>
    );
  const active = ["running", "queued"].includes(run.status),
    stages = run.stages || [],
    logs = run.logs || fallback.data?.logs || [],
    filtered =
      selected === "all" ? logs : stageOutput.data?.logs || logs.filter((l: any) => l.stage === selected);
  return (
    <>
      <div className="az-section-heading">
        <h2>Pipeline run</h2>
        <Status value={run.status} />
      </div>
      <ErrorNotice error={state.error || fallback.error || stageOutput.error} retry={state.refresh} />
      <div className="az-run-heading">
        <div>
          <strong>#{run.id.slice(0, 8)}</strong>
          <span>{dateTime(run.started_at || run.created_at)}</span>
        </div>
        <div>
          {!active && (
            <button className="az-button" disabled={busy || !pipeline.enabled} onClick={onRetry}>
              <Play size={14} />
              Run again
            </button>
          )}
          {active && (
            <button
              className="az-button"
              disabled={
                cancelling || run.cancel_requested || ["deploy", "verify", "complete"].includes(run.stage)
              }
              onClick={async () => {
                setCancelling(true);
                try {
                  await api(`/pipelines/runs/${runId}/cancel`, { method: "POST" });
                  state.refresh();
                  notify("Cancellation requested at the next safe stage boundary");
                } catch (e) {
                  notify(e instanceof Error ? e.message : "Could not cancel run", "error");
                } finally {
                  setCancelling(false);
                }
              }}
            >
              <Square size={13} />
              {run.cancel_requested ? "Cancellation requested" : "Cancel at safe boundary"}
            </button>
          )}
          {run.job_id && (
            <a className="az-button" href={`/api/deployment-jobs/${run.job_id}/logs`} download>
              <ArrowDownToLine size={14} />
              Download logs
            </a>
          )}
        </div>
      </div>
      <Properties
        rows={[
          ["Application", <a href={href("apps", pipeline.app_id)}>{pipeline.app_name || pipeline.app_id}</a>],
          ["Commit", run.commit || "Not available"],
          ["Image artifact", run.image || "Not produced yet"],
          ["Result", run.message || run.status],
          ["Finished", dateTime(run.finished_at)],
        ]}
      />
      <div className="az-run-workspace">
        <nav className="az-stage-list" aria-label="Run stages">
          <button className={selected === "all" ? "selected" : ""} onClick={() => setSelected("all")}>
            All output
          </button>
          {stages.map((stage: any) => (
            <button
              key={stage.name}
              className={selected === stage.name ? "selected" : ""}
              onClick={() => setSelected(stage.name)}
            >
              <span>{labels[stage.name] || stage.name}</span>
              <Status value={stage.status} />
              <small>
                {stage.duration_seconds != null
                  ? `${Number(stage.duration_seconds).toFixed(1)}s`
                  : stage.finished_at && stage.started_at
                    ? `${Math.max(0, (Date.parse(stage.finished_at) - Date.parse(stage.started_at)) / 1000).toFixed(1)}s`
                    : stage.status === "running"
                      ? "In progress"
                      : stage.status === "skipped"
                        ? "Skipped"
                        : "Not started"}
                {stage.exit_code != null ? ` · exit ${stage.exit_code}` : ""}
              </small>
            </button>
          ))}
        </nav>
        <div className="az-run-output">
          <div className="az-runtime-toolbar">
            <span>{selected === "all" ? "All run output" : labels[selected] || selected}</span>
            <span>{filtered.length} entries</span>
          </div>
          <div
            className="az-log-panel"
            role="log"
            aria-label="Pipeline stage output"
            aria-live="off"
            tabIndex={0}
          >
            {filtered.length ? (
              filtered.map((line: any, i: number) => (
                <div key={line.id || i} className={line.level === "error" ? "az-log-error" : ""}>
                  <time>{line.created_at ? new Date(line.created_at).toLocaleTimeString() : ""}</time>
                  <pre>{line.message}</pre>
                </div>
              ))
            ) : (
              <pre>{active ? "Waiting for stage output…" : "No output recorded for this stage."}</pre>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
