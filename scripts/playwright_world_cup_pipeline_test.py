import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


FRONTEND_URL = "http://127.0.0.1:5175"
BACKEND_URL = "http://127.0.0.1:8001"
POLL_SECONDS = 10
MAX_WAIT_SECONDS = 20 * 60


def api_request(path: str, *, token: str | None = None, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(f"{BACKEND_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc


def signup_user() -> tuple[str, str]:
    stamp = int(time.time())
    email = f"playwright-world-cup-{stamp}@example.test"
    response = api_request(
        "/api/v1/auth/signup",
        method="POST",
        payload={
            "email": email,
            "name": f"World Cup Playwright {stamp}",
            "password": f"Passw0rd!-{stamp}",
        },
    )
    return email, response["access_token"]


def save(page, folder: Path, name: str) -> Path:
    path = folder / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def main() -> None:
    folder = Path("screenshots-results") / datetime.now().strftime("%Y%m%d-%H%M%S-world-cup-pipeline")
    folder.mkdir(parents=True, exist_ok=True)

    email, token = signup_user()
    summary = {
        "user": email,
        "screenshots_dir": str(folder),
        "pipeline_job_id": None,
        "final_status": None,
        "created_ticket_ids": [],
        "difficulty_tiers": 0,
        "errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1200})
        context.add_cookies(
            [
                {
                    "name": "access_token",
                    "value": token,
                    "url": FRONTEND_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "secure": False,
                }
            ]
        )
        page = context.new_page()

        page.goto(f"{FRONTEND_URL}/scrape", wait_until="networkidle")
        page.get_by_text("World Cup Pipeline").first.wait_for(timeout=20_000)
        save(page, folder, "01-scrape-before-run")

        with page.expect_response(lambda response: "/api/v1/data/world-cup-pipeline" in response.url and response.request.method == "POST", timeout=30_000) as response_info:
            page.get_by_role("button", name="Run World Cup Pipeline").click()
        job = response_info.value.json()
        job_id = job["id"]
        summary["pipeline_job_id"] = job_id
        save(page, folder, "02-pipeline-started")

        final_job = job
        started = time.monotonic()
        while time.monotonic() - started < MAX_WAIT_SECONDS:
            final_job = api_request(f"/api/v1/data/scrape/{job_id}", token=token)
            status = final_job.get("status")
            if status in {"completed", "failed", "cancelled"}:
                break
            page.reload(wait_until="networkidle")
            save(page, folder, f"03-pipeline-running-{int(time.monotonic() - started):04d}s")
            time.sleep(POLL_SECONDS)

        page.reload(wait_until="networkidle")
        save(page, folder, "04-pipeline-final-or-timeout")

        summary["final_status"] = final_job.get("status")
        if final_job.get("output"):
            output = json.loads(final_job["output"])
            summary["created_ticket_ids"] = output.get("created_ticket_ids", [])
            summary["difficulty_tiers"] = len(output.get("difficulty_tiers", []))
            summary["errors"] = output.get("errors", [])

        page.goto(f"{FRONTEND_URL}/predict", wait_until="networkidle")
        save(page, folder, "05-predict-page")

        page.goto(f"{FRONTEND_URL}/tickets", wait_until="networkidle")
        save(page, folder, "06-tickets-page")

        browser.close()

    summary_path = folder / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
