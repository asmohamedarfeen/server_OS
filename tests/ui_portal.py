"""Portal integration against local :3100; all backend traffic uses fixtures."""
import json
from playwright.sync_api import sync_playwright, expect


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        state = {"build_active": False, "readiness_error": False}
        page.on("pageerror", lambda e: errors.append(str(e)))
        app = dict(id="app-one", name="customer-api", source="https://github.com/example/api.git", source_type="github", source_ref="main", framework="FastAPI", port=8000, host_port=53834, status="running", container_id="container-one", image="arfeen/api:abc123", domain=None, created_at="2026-10-28T00:00:00Z")
        server = dict(id="server", hostname="ubuntu-server", platform="Ubuntu 24.04", cpu_percent=12, cpu_count=4, uptime_seconds=12345, timestamp="2026-10-28T08:00:00Z", memory={"total": 8000000000, "used": 3000000000, "percent": 37.5}, disk={"total": 100000000000, "used": 40000000000, "free": 60000000000, "percent": 40}, network={"rx_bytes_sec": 256, "tx_bytes_sec": 128}, docker={"available": True, "version": "27.0"}, capabilities={"host_inspection": True, "service_restart": False, "reboot": False, "reason": "Host actions unavailable in preview"}, affected_apps=[app])
        pipeline = dict(id="pipeline-one", name="API production", app_id="app-one", enabled=True, test_command="pytest", test_timeout=120, poll_enabled=False, source=app["source"], ref="main", source_type="github")
        def api(route):
            path = route.request.url.split("/api", 1)[1].split("?", 1)[0]
            requests.append((route.request.method, path))
            data = []
            if path == "/auth/me": data = {"username": "test-admin"}
            elif path in ("/server", "/control/overview"): data = server
            elif path == "/apps": data = [app]
            elif path == "/deployment-jobs": data = [{"id":"busy-build","name":"customer-api","status":"running","stage":"build","app_id":"app-one"}] if state["build_active"] else []
            elif path == "/containers": data = [{"id": "container-one", "name": "customer-api", "status": "running", "image": app["image"], "ports": []}]
            elif path == "/pipelines": data = [pipeline]
            elif path == "/pipelines/pipeline-one": data = pipeline
            elif path == "/pipelines/pipeline-one/runs": data = [{"id": "run-one", "job_id": "job-one", "pipeline_id": "pipeline-one", "status": "success", "created_at": "2026-10-28T08:00:00Z", "commit": "abc123def", "image": app["image"]}]
            elif path == "/pipelines/runs/run-one": data = {"id": "run-one", "job_id": "job-one", "pipeline_id": "pipeline-one", "status": "success", "stages": [{"name": "build", "status": "success", "started_at": "2026-10-28T08:00:00Z", "finished_at": "2026-10-28T08:00:05Z"}], "image": app["image"]}
            elif path.startswith("/deployment-jobs/job-one"): data = {"id": "job-one", "status": "success", "logs": [{"id": 1, "stage": "build", "level": "info", "message": "Successfully built image", "created_at": "2026-10-28T08:00:05Z"}], "next_cursor": 1, "has_more": False}
            elif path.endswith("/logs"): data = {"logs": "2026-10-28 Listening on port 8000", "status": "running", "container_id": "container-one"}
            elif path.endswith("/environment"): data = {"environment": {"TOKEN": "super-secret-value"}}
            elif path.endswith("/readiness"):
                if state["readiness_error"]:
                    route.fulfill(status=503, content_type="application/json", body='{"detail":"Readiness configuration unavailable"}')
                    return
                data = {"path": None, "expected_status": 200, "timeout": 30}
            elif path.endswith("/metrics"): data = {"items": [], "resource_id": "server"}
            elif path == "/control/activity": data = {"items": [{"id": "activity-one", "action": "restart", "resource_id": "app-one", "resource_name": "customer-api", "status": "success", "actor": "test-admin", "created_at": "2026-10-28T08:00:00Z", "message": "Application restarted"}]}
            elif path == "/control/services": data = {"available": True, "items": [{"name": "docker", "status": "active", "active_state": "active"}]}
            elif path.startswith("/control/"): data = {"items": [], "available": True}
            elif path == "/github/connection": data = {"connected": False}
            route.fulfill(content_type="application/json", body=json.dumps(data))
        page.route("**/api/**", api)
        page.goto("http://127.0.0.1:3100")
        expect(page.get_by_role("heading", name="Welcome to Arfeen Cloud")).to_be_visible()
        page.screenshot(path="/tmp/portal-home.png", full_page=True)
        page.get_by_role("link", name="App Services", exact=True).first.click()
        page.get_by_role("link", name="customer-api", exact=True).first.click()
        expect(page.get_by_role("heading", name="customer-api", exact=True)).to_be_visible()
        expect(page.get_by_text("Running · readiness not configured", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="Browse application")).to_have_attribute("href", "http://127.0.0.1:53834")
        page.screenshot(path="/tmp/portal-app.png", full_page=True)
        page.get_by_role("link", name="Configuration", exact=True).click()
        expect(page.get_by_role("textbox", name="Environment variables")).not_to_be_visible()
        page.get_by_role("button", name="Reveal and edit values").click()
        expect(page.get_by_role("textbox", name="Environment variables")).to_contain_text("TOKEN=super-secret-value")
        state["build_active"] = True
        expect(page.get_by_role("button", name="Save and restart")).to_be_disabled(timeout=10000)
        state["build_active"] = False
        expect(page.get_by_role("button", name="Save and restart")).to_be_enabled(timeout=10000)
        state["readiness_error"] = True
        page.reload()
        expect(page.get_by_role("heading", name="Configuration", exact=True)).to_be_visible()
        expect(page.get_by_role("textbox", name="Environment variables")).not_to_be_visible()
        expect(page.locator(".az-notice.error")).to_contain_text("Readiness configuration unavailable")
        expect(page.get_by_role("button", name="Save readiness check")).to_be_disabled()
        state["readiness_error"] = False
        page.get_by_role("button", name="Retry", exact=True).click()
        expect(page.get_by_role("button", name="Save readiness check")).to_be_enabled()
        page.go_back()
        expect(page.get_by_role("heading", name="Overview", exact=True)).to_be_visible()
        page.get_by_role("link", name="Log stream", exact=True).click()
        expect(page.get_by_role("log", name="Application runtime output")).to_contain_text("Listening on port 8000")
        page.get_by_role("link", name="Pipelines", exact=True).first.click()
        page.get_by_role("button", name="New pipeline").click()
        expect(page.get_by_role("dialog", name="New pipeline")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog", name="New pipeline")).not_to_be_visible()
        page.get_by_role("link", name="API production", exact=True).click()
        page.get_by_role("link", name="run-one", exact=False).click()
        expect(page.get_by_role("heading", name="Pipeline run", exact=True)).to_be_visible()
        page.get_by_role("button", name="Build", exact=False).click()
        expect(page.get_by_role("log")).to_contain_text("Successfully built image")
        page.screenshot(path="/tmp/portal-pipeline.png", full_page=True)
        page.evaluate("window.scrollTo(0, 300)")
        page.get_by_role("link", name="Server", exact=True).first.click()
        expect(page.get_by_role("heading", name="ubuntu-server", exact=True)).to_be_visible()
        page.wait_for_function("window.scrollY === 0", timeout=2000)
        expect(page.get_by_role("button", name="Reboot server")).to_be_disabled()
        page.screenshot(path="/tmp/portal-server.png", full_page=True)
        page.get_by_role("link", name="Services", exact=True).click()
        expect(page.get_by_text("docker", exact=True)).to_be_visible()
        page.get_by_role("button", name="Search resources and services").click()
        page.get_by_role("combobox", name="Search resources and services").fill("customer-api")
        page.get_by_role("option", name="customer-api", exact=False).first.click()
        expect(page.get_by_role("heading", name="customer-api", exact=True)).to_be_visible()
        page.get_by_role("link", name="All resources", exact=True).first.click()
        container_row = page.get_by_role("row").filter(has=page.get_by_role("cell", name="Container", exact=True))
        container_row.get_by_role("link", name="customer-api", exact=True).click()
        expect(page.locator(".az-resource-heading")).to_contain_text("Container")
        assert "#containers/container-one/overview" in page.url
        page.get_by_role("link", name="App Services", exact=True).first.click()
        page.get_by_role("link", name="customer-api", exact=True).first.click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("window.scrollTo(0, 0)")
        assert page.locator(".az-topbar").count() == 1
        page.screenshot(path="/tmp/portal-mobile.png", full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "No page-level mobile overflow"
        expect(page.get_by_role("navigation", name="Portal navigation")).not_to_be_visible()
        page.get_by_role("button", name="Open navigation").click()
        expect(page.get_by_role("navigation", name="Portal navigation")).to_be_visible()
        assert not errors, errors
        print("PASS: portal home/app/config/logs/pipeline/server/search/routes/mobile; no browser errors")
        browser.close()


if __name__ == "__main__": run()
