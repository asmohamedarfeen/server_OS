"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AppWindow,
  Bell,
  Box,
  ChevronRight,
  Cloud,
  Database,
  FileText,
  Folder,
  HardDrive,
  Home,
  Layers3,
  LogOut,
  Menu,
  Network,
  Search,
  Server,
  Settings2,
  TerminalSquare,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { AppRecord } from "@/lib/types";
import AuthScreen from "./auth-screen";
import {
  ContainersPage,
  DatabasesPage,
  DockerResourcesPage,
  FilesPage,
  LogsPage,
  SettingsPage,
} from "./resource-pages";
import TerminalPanel from "./terminal-panel";
import {
  ActivityList,
  ErrorNotice,
  href,
  itemsOf,
  Notify,
  parseRoute,
  PortalRoute,
  useResource,
} from "./portal-shared";
import { PortalHome, ResourceInventory, ResourceRow } from "./portal-pages";
import { PortalApplications, PortalApplication } from "./portal-app";
import { PortalPipelines } from "./portal-pipelines";
import { PortalServer } from "./portal-server";
import { InfrastructureResource } from "./portal-infrastructure";

const destinations = [
  { id: "home", label: "Home", icon: Home },
  { id: "resources", label: "All resources", icon: Layers3 },
  { id: "apps", label: "App Services", icon: AppWindow },
  { id: "pipelines", label: "Pipelines", icon: Layers3 },
  { id: "server", label: "Server", icon: Server },
  { id: "containers", label: "Containers", icon: Box },
  { id: "databases", label: "Databases", icon: Database },
  { id: "volumes", label: "Storage", icon: HardDrive },
  { id: "images", label: "Images", icon: Layers3 },
  { id: "networks", label: "Networks", icon: Network },
  { id: "files", label: "Files", icon: Folder },
  { id: "monitor", label: "Monitor", icon: Activity },
  { id: "logs", label: "Logs", icon: FileText },
  { id: "activity", label: "Activity log", icon: Activity },
  { id: "terminal", label: "Terminal", icon: TerminalSquare },
  { id: "settings", label: "Settings", icon: Settings2 },
];

export default function Portal() {
  const [user, setUser] = useState<string | null | undefined>(undefined),
    [route, setRoute] = useState<PortalRoute>({ view: "home", tab: "overview" });
  const [mobile, setMobile] = useState(false),
    [searchOpen, setSearchOpen] = useState(false),
    [notifications, setNotifications] = useState(false);
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const update = () => setNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const navigationClosed = narrow ? !mobile : navigationCollapsed;
  const [toast, setToast] = useState<{ text: string; kind: string } | null>(null),
    [recent, setRecent] = useState<ResourceRow[]>([]);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const notify: Notify = useCallback((text, kind = "success") => {
    setToast({ text, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  }, []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);
  useEffect(() => {
    api("/auth/me")
      .then((x) => setUser(x.username || "Administrator"))
      .catch(() => setUser(null));
  }, []);
  useEffect(() => {
    const changed = () => {
      setRoute(parseRoute(window.location.hash));
      setMobile(false);
      setNotifications(false);
      window.scrollTo(0, 0);
    };
    changed();
    window.addEventListener("hashchange", changed);
    try {
      const value = JSON.parse(localStorage.getItem("arfeen-recent-resources") || "[]");
      if (Array.isArray(value)) setRecent(value.slice(0, 6));
    } catch {}
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("hashchange", changed);
      window.removeEventListener("keydown", key);
    };
  }, []);
  const appsState = useResource<AppRecord[]>(user ? "/apps" : null),
    containers = useResource<any[]>(user ? "/containers" : null),
    databases = useResource<any[]>(user ? "/databases" : null);
  const server = useResource<any>(user ? "/control/overview" : null),
    images = useResource<any[]>(user ? "/docker/images" : null, 20000),
    volumes = useResource<any[]>(user ? "/docker/volumes" : null, 20000),
    networks = useResource<any[]>(user ? "/docker/networks" : null, 20000);
  const apps = itemsOf(appsState.data) as AppRecord[];
  const resources: ResourceRow[] = [
    ...(server.data
      ? [
          {
            id: "server",
            name: server.data.hostname || "Managed server",
            type: "Server",
            status:
              server.data.host_available === false
                ? "unavailable"
                : server.data.docker?.available
                  ? "running"
                  : "Docker unavailable",
            href: href("server", "server"),
            detail: server.data.platform || "",
          },
        ]
      : []),
    ...apps.map((a) => ({
      id: a.id,
      name: a.name,
      type: "App Service",
      status: a.status,
      href: href("apps", a.id),
      detail: a.framework,
    })),
    ...itemsOf(containers.data).map((c) => ({
      id: c.id,
      name: c.name,
      type: "Container",
      status: c.status,
      href: href("containers", c.id),
      detail: c.image,
    })),
    ...itemsOf(databases.data).map((d) => ({
      id: d.id,
      name: d.name,
      type: "Database",
      status: d.status,
      href: href("databases", d.id),
      detail: d.engine,
    })),
    ...itemsOf(images.data).map((i) => ({
      id: i.id,
      name: i.tags?.[0] || i.id,
      type: "Image",
      status: "available",
      href: href("images", i.id),
      detail: i.tags?.join(", "),
    })),
    ...itemsOf(volumes.data).map((v) => ({
      id: v.name,
      name: v.name,
      type: "Volume",
      status: "available",
      href: href("volumes", v.name),
      detail: v.driver,
    })),
    ...itemsOf(networks.data).map((n) => ({
      id: n.id,
      name: n.name,
      type: "Network",
      status: "available",
      href: href("networks", n.id),
      detail: n.driver,
    })),
  ];
  const found = resources.find(
    (r) => r.id === route.id && (route.view === "apps" ? r.type === "App Service" : true),
  );
  const resourceIdentity = found ? JSON.stringify(found) : "";
  useEffect(() => {
    if (!resourceIdentity) return;
    const value = JSON.parse(resourceIdentity) as ResourceRow;
    setRecent((prior) => {
      const next = [value, ...prior.filter((x) => x.href !== value.href)].slice(0, 6);
      try {
        localStorage.setItem("arfeen-recent-resources", JSON.stringify(next));
      } catch {}
      return next;
    });
  }, [resourceIdentity]);
  const refresh = () => {
    appsState.refresh();
    containers.refresh();
    databases.refresh();
    server.refresh();
    images.refresh();
    volumes.refresh();
    networks.refresh();
  };
  if (user === undefined)
    return (
      <div className="boot-screen">
        <Cloud size={24} />
        Connecting to Arfeen Cloud…
      </div>
    );
  if (user === null)
    return (
      <AuthScreen
        onAuthenticated={() => {
          api("/auth/me").then((x) => setUser(x.username || "Administrator"));
        }}
      />
    );
  const label = destinations.find((d) => d.id === route.view)?.label || "Resource";
  const app = apps.find((a) => a.id === route.id);
  const legacy = (child: React.ReactNode) => <div className="az-legacy">{child}</div>;
  const content = () => {
    const collections: Record<string, ReturnType<typeof useResource<any>>> = {
      containers,
      databases,
      images,
      volumes,
      networks,
    };
    if (route.id && collections[route.view]) {
      const collection = collections[route.view];
      return (
        <InfrastructureResource
          route={route}
          resource={itemsOf(collection.data).find(
            (r) => r.id === route.id || r.full_id === route.id || r.name === route.id,
          )}
          loading={collection.loading}
          error={collection.error}
          refresh={collection.refresh}
          notify={notify}
        />
      );
    }
    switch (route.view) {
      case "home":
        return (
          <PortalHome
            resources={resources}
            recent={recent}
            server={server.data}
            apps={apps}
            loading={server.loading}
            onRefresh={refresh}
          />
        );
      case "resources":
        return (
          <ResourceInventory
            resources={resources}
            onRefresh={refresh}
            errors={[
              appsState.error,
              containers.error,
              databases.error,
              images.error,
              volumes.error,
              networks.error,
              server.error,
            ].filter(Boolean)}
          />
        );
      case "apps":
        return route.id ? (
          <PortalApplication
            key={route.id}
            app={app}
            loading={appsState.loading}
            error={appsState.error}
            route={route}
            notify={notify}
            refresh={appsState.refresh}
          />
        ) : (
          <PortalApplications
            apps={apps}
            error={appsState.error}
            loading={appsState.loading}
            refresh={appsState.refresh}
            notify={notify}
          />
        );
      case "pipelines":
        return (
          <PortalPipelines
            key={`${route.id || "list"}:${route.tab}`}
            route={route}
            apps={apps}
            notify={notify}
          />
        );
      case "server":
      case "monitor":
        return (
          <PortalServer
            route={{
              ...route,
              view: "server",
              id: "server",
              tab: route.view === "monitor" ? "metrics" : route.tab,
            }}
            notify={notify}
          />
        );
      case "containers":
        return legacy(
          <ContainersPage
            notify={notify}
            onTerminal={(c) => {
              window.location.hash = href("terminal", c.id).slice(1);
            }}
          />,
        );
      case "databases":
        return legacy(<DatabasesPage notify={notify} />);
      case "images":
      case "volumes":
      case "networks":
        return legacy(
          <DockerResourcesPage
            key={route.view}
            kind={route.view === "images" ? "Images" : route.view === "volumes" ? "Volumes" : "Networks"}
            notify={notify}
          />,
        );
      case "files":
        return legacy(<FilesPage notify={notify} />);
      case "logs":
        return legacy(<LogsPage notify={notify} />);
      case "activity":
        return (
          <div className="az-page">
            <ActivityList />
          </div>
        );
      case "terminal":
        return legacy(
          <TerminalPanel
            target={
              route.id
                ? { id: route.id, name: resources.find((r) => r.id === route.id)?.name || route.id }
                : null
            }
          />,
        );
      case "settings":
        return legacy(<SettingsPage notify={notify} />);
      default:
        return (
          <div className="az-page">
            <h1>Page not found</h1>
            <a href={href("home")}>Return home</a>
          </div>
        );
    }
  };
  return (
    <div className={`az-portal ${navigationCollapsed ? "nav-collapsed" : ""}`}>
      <header className="az-topbar">
        <button
          className="az-menu-button"
          aria-label="Open navigation"
          aria-expanded={!navigationClosed}
          aria-controls="portal-navigation"
          onClick={() => {
            if (window.matchMedia("(max-width: 900px)").matches) setMobile(!mobile);
            else setNavigationCollapsed(!navigationCollapsed);
          }}
        >
          <Menu size={20} />
        </button>
        <a className="az-brand" href={href("home")}>
          <Cloud size={23} />
          <strong>Arfeen Cloud</strong>
        </a>
        <button
          className="az-global-search"
          aria-label="Search resources and services"
          onClick={() => setSearchOpen(true)}
        >
          <Search size={16} />
          <span>Search resources and services</span>
          <kbd>⌘ K</kbd>
        </button>
        <div className="az-global-actions">
          <a href={href("terminal")} aria-label="Open terminal" title="Terminal">
            <TerminalSquare size={18} />
          </a>
          <button
            aria-label="Notifications"
            title="Notifications"
            aria-expanded={notifications}
            onClick={() => setNotifications(!notifications)}
          >
            <Bell size={18} />
          </button>
          <a href={href("settings")} aria-label="Portal settings" title="Settings">
            <Settings2 size={18} />
          </a>
          <span className="az-account">
            {user}
            <small>Private server</small>
          </span>
          <button
            aria-label="Sign out"
            title="Sign out"
            onClick={async () => {
              try {
                await api("/auth/logout", { method: "POST" });
                setUser(null);
              } catch (e) {
                notify(String(e), "error");
              }
            }}
          >
            <LogOut size={17} />
          </button>
        </div>
      </header>
      {mobile && (
        <button className="az-nav-scrim" aria-label="Close navigation" onClick={() => setMobile(false)} />
      )}
      <nav
        className={`az-navigation ${mobile ? "open" : ""}`}
        aria-label="Portal navigation"
        id="portal-navigation"
        inert={navigationClosed}
      >
        <div className="az-navigation-label">YOUR WORKSPACE</div>
        {destinations.map(({ id, label: text, icon: Icon }) => (
          <a
            key={id}
            aria-label={text}
            aria-current={route.view === id ? "page" : undefined}
            className={route.view === id ? "active" : ""}
            href={href(id, id === "server" ? "server" : undefined)}
          >
            <Icon size={17} />
            <span>{text}</span>
            {id === "apps" && <small>{apps.length}</small>}
          </a>
        ))}
        <div className="az-nav-host">
          <span
            className={`az-connection-dot ${server.data && !server.error && server.data.host_available !== false ? "online" : ""}`}
          />
          <span>
            {server.error ? "Server disconnected" : server.data?.hostname || "Connecting to server"}
          </span>
        </div>
      </nav>
      <main className="az-main">
        <div className="az-breadcrumb">
          <a href={href("home")}>Home</a>
          {route.view !== "home" && (
            <>
              <ChevronRight size={12} />
              <a href={href(route.view)}>{label}</a>
            </>
          )}
          {route.id && (
            <>
              <ChevronRight size={12} />
              <span>{found?.name || (route.view === "server" ? server.data?.hostname : route.id)}</span>
            </>
          )}
          <span className="az-scope">Single server · {server.data?.hostname || "Connecting"}</span>
        </div>
        {content()}
      </main>
      {searchOpen && <PortalSearch resources={resources} onClose={() => setSearchOpen(false)} />}
      {notifications && (
        <aside className="az-notifications">
          <div className="az-section-heading">
            <h2>Notifications</h2>
            <button aria-label="Close notifications" onClick={() => setNotifications(false)}>
              <X size={17} />
            </button>
          </div>
          <p>Recent operations on your server</p>
          <ActivityList />
        </aside>
      )}
      {toast && (
        <div className={`az-toast ${toast.kind}`} role="status">
          {toast.text}
          <button aria-label="Dismiss" onClick={() => setToast(null)}>
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}

function PortalSearch({ resources, onClose }: { resources: ResourceRow[]; onClose: () => void }) {
  const [query, setQuery] = useState(""),
    [selected, setSelected] = useState(0),
    ref = useRef<HTMLDialogElement>(null);
  const results = [
    ...resources,
    ...destinations.map((d) => ({
      id: d.id,
      name: d.label,
      type: "Service",
      status: "",
      href: href(d.id, d.id === "server" ? "server" : undefined),
      detail: "",
    })),
  ]
    .filter((r) => `${r.name} ${r.type}`.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 12);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => prior?.focus();
  }, []);
  const open = (index: number) => {
    if (results[index]) {
      window.location.hash = results[index].href;
      onClose();
    }
  };
  return (
    <dialog ref={ref} className="az-search-dialog" aria-label="Resource search" onCancel={onClose}>
      <div className="az-search-input">
        <Search size={19} />
        <input
          autoFocus
          role="combobox"
          aria-label="Search resources and services"
          aria-expanded="true"
          aria-controls="portal-search-results"
          aria-activedescendant={results[selected] ? `search-result-${selected}` : undefined}
          placeholder="Search resources and services"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setSelected((s) => Math.min(s + 1, results.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setSelected((s) => Math.max(s - 1, 0));
            }
            if (e.key === "Enter") {
              e.preventDefault();
              open(selected);
            }
          }}
        />
        <button aria-label="Close search" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <p>Resources and services</p>
      <div role="listbox" id="portal-search-results">
        {results.map((r, i) => (
          <button
            role="option"
            id={`search-result-${i}`}
            aria-selected={i === selected}
            key={`${r.type}:${r.id}`}
            onClick={() => open(i)}
          >
            <span>{r.name}</span>
            <small>{r.type}</small>
          </button>
        ))}
        {!results.length && <div className="az-empty">No matching resources or services</div>}
      </div>
    </dialog>
  );
}
