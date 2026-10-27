"""Optional browser integration checks. Start the production frontend on port 3100.

Run with a Python environment containing playwright; uses installed Google Chrome.
All API traffic is intercepted with controlled fixtures, never a production server.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        status = {"value": "running", "polls": 0}
        created = "2026-10-27T16:00:00Z"
        job = {"id": "test-job", "name": "cardiovision", "source": "https://github.com/example/cardiovision.git", "ref": "main", "status": "running", "stage": "build", "message": "Installing dependencies", "created_at": created, "started_at": created}
        app = {"id": "app-id", "name": "cardiovision", "status": "running", "framework": "Dockerfile", "source": job["source"], "source_type": "github", "port": 8000, "host_port": 45001, "created_at": created}

        def api(route):
            path = route.request.url.split("/api", 1)[1]
            data = []
            if path == "/auth/me": data = {"username": "test-admin"}
            elif path == "/server":
                route.fulfill(status=503, content_type="application/json", body='{"detail":"Preview metrics unavailable"}')
                return
            elif path == "/github/connection": data = {"connected": False}
            elif path == "/apps": data = [app] if status["value"] == "success" else []
            elif path.startswith("/apps/"): data = []
            elif path == "/deployment-jobs" and route.request.method == "GET": data = [{**job, "status": status["value"], "stage": "complete" if status["value"] == "success" else "build"}]
            elif path == "/deployment-jobs/github":
                route.fulfill(status=202, content_type="application/json", body=json.dumps(job))
                return
            elif path.startswith("/deployment-jobs/test-job?"):
                status["polls"] += 1
                cursor = int(path.split("after=")[1])
                lines = [
                    {"id": 1, "created_at": created, "stage": "clone", "level": "info", "message": "Receiving objects: 100% (412/412)"},
                    {"id": 2, "created_at": created, "stage": "build", "level": "info", "message": "Step 3/12 : RUN npm ci\nadded 182 packages"},
                ]
                if status["polls"] >= 2:
                    lines.append({"id": 3, "created_at": created, "stage": "build", "level": "info", "message": "Step 4/12 : RUN npm run build"})
                if status["value"] == "failed":
                    lines.append({"id": 4, "created_at": created, "stage": "build", "level": "error", "message": "Build failed: missing application entrypoint"})
                lines = [line for line in lines if line["id"] > cursor]
                data = {**job, "status": status["value"], "message": "Build failed: missing application entrypoint" if status["value"] == "failed" else "Installing dependencies", "logs": lines, "has_more": False, "next_cursor": lines[-1]["id"] if lines else cursor}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

        page.route("**/api/**", api)
        page.goto("http://127.0.0.1:3100")
        page.get_by_role("button", name="Applications", exact=True).click()
        page.get_by_role("button", name="View logs →").click()
        expect(page.get_by_role("dialog", name="cardiovision")).to_be_visible()
        expect(page.get_by_text("Receiving objects: 100%", exact=False)).to_be_visible()
        expect(page.get_by_text("Step 4/12", exact=False)).to_be_visible(timeout=8000)
        page.screenshot(path="/tmp/deployment-console-desktop.png", full_page=True)
        page.get_by_role("button", name="Continue in background").click()
        status["value"] = "success"
        expect(page.locator(".app-card").filter(has_text="cardiovision")).to_be_visible(timeout=10000)
        print("PASS: live incremental logs, close/background completion refresh")

        status["value"] = "failed"
        page.get_by_role("button", name="View logs →").click()
        expect(page.locator(".deployment-result.failed")).to_contain_text("missing application entrypoint")
        expect(page.locator(".deployment-log-line.error")).to_be_visible()
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(path="/tmp/deployment-console-mobile.png", full_page=True)
        expect(page.get_by_role("button", name="Done", exact=True)).to_be_visible()
        assert page.locator(".deployment-console").evaluate("el => el.scrollWidth <= el.clientWidth")
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog", name="cardiovision")).not_to_be_visible()
        assert not errors, errors
        print("PASS: failure output, mobile layout, Escape dismissal, no browser errors")
        browser.close()


if __name__ == "__main__":
    run()
