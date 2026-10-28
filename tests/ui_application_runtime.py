"""Run against the frontend on :3100, with isolated API fixtures."""
import json
from playwright.sync_api import sync_playwright, expect


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        state = {"polls": 0, "failure": False, "empty": False}
        apps = [dict(id="runtime-app", name="sample", framework="Dockerfile", source="ZIP upload", port=8000,
                     host_port=53834, status="running", domain=None, container_id="old-container", created_at="2026-10-28"),
                dict(id="domain-app", name="custom-domain", framework="Node.js", source="ZIP upload", port=3000,
                     host_port=None, status="running", domain="app.example.com", created_at="2026-10-28")]

        def api(route):
            path = route.request.url.split("/api", 1)[1]
            data = []
            if path == "/auth/me": data = {"username": "test-admin"}
            elif path == "/server":
                route.fulfill(status=503, content_type="application/json", body='{"detail":"No metrics in preview"}')
                return
            elif path == "/apps": data = apps
            elif path.startswith("/apps/runtime-app/logs"):
                state["polls"] += 1
                if state["failure"]:
                    route.fulfill(status=503, content_type="application/json", body='{"detail":"Docker temporarily unavailable"}')
                    return
                data = {"logs": "" if state["empty"] else "\n".join(f"2026-10-28T00:00:00Z Runtime line {i}" for i in range(200)) + f"\nRefresh {state['polls']}",
                        "status": "running", "container_id": "current-container"}
            route.fulfill(content_type="application/json", body=json.dumps(data))

        page.route("**/api/**", api)
        page.goto("http://127.0.0.1:3100")
        page.get_by_role("link", name="App Services", exact=True).first.click()
        page.get_by_role("link", name="custom-domain", exact=True).first.click()
        expect(page.get_by_role("link", name="Open application")).to_have_attribute("href", "http://app.example.com")
        page.get_by_role("link", name="App Services", exact=True).first.click()
        page.get_by_role("link", name="sample", exact=True).first.click()
        expect(page.get_by_role("link", name="Open application")).to_have_attribute("href", "http://127.0.0.1:53834")
        page.get_by_role("button", name="Copy application URL").click()
        assert page.evaluate("navigator.clipboard.readText()") == "http://127.0.0.1:53834"
        page.get_by_role("link", name="Log stream", exact=True).click()
        stream = page.locator(".az-runtime-stream")
        expect(stream).to_be_visible()
        log = page.get_by_role("log", name="Application runtime output")
        expect(log).to_contain_text("Refresh 2", timeout=10000)
        assert log.evaluate("el => el.scrollHeight > el.clientHeight")
        log.hover()
        page.mouse.wheel(0, -500)
        expect(page.get_by_role("checkbox", name="Follow logs")).not_to_be_checked()
        before = log.evaluate("el => el.scrollTop")
        expect(log).to_contain_text("Refresh 3", timeout=10000)
        assert abs(log.evaluate("el => el.scrollTop") - before) < 5
        page.get_by_role("button", name="Pause updates").click()
        polls = state["polls"]
        page.wait_for_timeout(2500)
        assert state["polls"] == polls
        with page.expect_download() as download:
            page.get_by_role("button", name="Download logs").click()
        assert download.value.suggested_filename == "sample-runtime.log"
        state["failure"] = True
        page.get_by_role("button", name="Resume updates").click()
        expect(stream.get_by_role("alert")).to_contain_text("Docker temporarily unavailable")
        expect(log).to_contain_text("Runtime line 199")
        state["failure"] = False
        state["empty"] = True
        expect(log).to_contain_text("No application output yet", timeout=12000)
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(path="/tmp/application-runtime-mobile.png", full_page=True)
        assert stream.evaluate("el => el.scrollWidth <= el.clientWidth")
        assert log.evaluate("el => el.scrollHeight >= el.clientHeight")
        page.get_by_role("link", name="Overview", exact=True).click()
        expect(stream).not_to_be_visible()
        polls = state["polls"]
        page.wait_for_timeout(2500)
        assert state["polls"] == polls
        page.set_viewport_size({"width": 1440, "height": 1000})
        state["empty"] = False
        page.get_by_role("link", name="Log stream", exact=True).click()
        expect(log).to_contain_text("Runtime line 199")
        page.screenshot(path="/tmp/application-runtime-desktop.png", full_page=True)
        assert not errors, errors
        print("PASS: application URLs, copy, runtime refresh, follow, pause, download, recovery, empty state, mobile, cleanup")
        browser.close()


if __name__ == "__main__":
    run()
