#!/usr/bin/env python3
"""
Automated demo recorder for Supply Chain Pulse.

Resets the DB to the perfect-storm state, fires the analysis pipeline,
starts API + UI, drives the browser through demo/DEMO_SCRIPT.md via
Playwright, and saves the recording to demo/demo_recording.mp4.

Usage:
    python -m demo.record_demo
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = str(ROOT / ".venv" / "bin" / "python")
VIDEO_DIR = ROOT / "demo" / "_video_tmp"
OUTPUT_MP4 = ROOT / "demo" / "demo_recording.mp4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_dotenv():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())



def wait_ready(url: str, label: str, timeout: int = 40) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code < 500:
                print(f"  {label} ready")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def seed_demo_alert():
    """Reset DB and insert pre-written HIGH-severity alert (no Gemini needed)."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [VENV_PYTHON, "-m", "demo.scenario", "--seed-alert"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR seeding alert:", result.stderr[-500:])
        sys.exit(1)
    print(" ", result.stdout.strip())


# ---------------------------------------------------------------------------
# Browser automation
# ---------------------------------------------------------------------------

async def record_demo():
    from playwright.async_api import async_playwright

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # ------------------------------------------------------------------
        # Load the app
        # ------------------------------------------------------------------
        print("Opening Supply Chain Pulse UI...")
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(5)

        # ------------------------------------------------------------------
        # 00:25–00:50  Pipeline tab
        # Show connections and click "Sync now" to produce tool call log entry
        # ------------------------------------------------------------------
        print("→ Pipeline tab")
        await page.get_by_role("tab", name="Pipeline").click()
        await asyncio.sleep(3)

        sync_btns = page.get_by_role("button", name="Sync now")
        if await sync_btns.count() > 0:
            await sync_btns.first.click()
            print("  Clicked 'Sync now' — sync_connection appears in log")
            await asyncio.sleep(3)

        # ------------------------------------------------------------------
        # 00:50–01:30  Alerts tab
        # Alert was pre-created before recording started — navigate there now
        # ------------------------------------------------------------------
        print("→ Alerts tab")
        await page.get_by_role("tab", name="Alerts").click()
        await asyncio.sleep(3)

        # Verify alert is present
        body_text = await page.locator("body").inner_text()
        if "No open alerts" in body_text:
            print("  WARNING: Alerts tab shows no alerts — retrying after reload")
            await page.reload(wait_until="networkidle")
            await asyncio.sleep(3)
            await page.get_by_role("tab", name="Alerts").click()
            await asyncio.sleep(3)
        else:
            print("  Alert visible: OK")

        # Expand underlying data query
        expander = page.get_by_text("Show underlying data and query")
        if await expander.count() > 0:
            await expander.first.click()
            print("  Expanded underlying data view")
            await asyncio.sleep(5)
        else:
            print("  WARNING: expander not found")

        # ------------------------------------------------------------------
        # 01:30–02:10  Approve action — switch to backup supplier
        # ------------------------------------------------------------------
        print("→ Selecting 'switch_supplier' and approving")
        switch_label = page.locator("label").filter(has_text="Switch to backup supplier")
        if await switch_label.count() > 0:
            await switch_label.first.click()
            print("  Selected 'Switch to backup supplier (Vertex Fabrics)'")
            await asyncio.sleep(2)
        else:
            print("  WARNING: switch_supplier radio label not found")

        approve_btn = page.get_by_role("button", name="Approve")
        approved = False
        if await approve_btn.count() > 0 and not await approve_btn.first.is_disabled():
            await approve_btn.first.click()
            print("  Approved — showing tool call log...")
            await asyncio.sleep(7)
            approved = True
        else:
            print("  WARNING: Approve button not found or still disabled")

        if approved:
            # Scroll to show the tool call JSON log
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

        # ------------------------------------------------------------------
        # 02:10–02:40  Chat tab
        # ------------------------------------------------------------------
        print("→ Chat tab — asking two questions")
        await page.get_by_role("tab", name="Chat").click()
        await asyncio.sleep(2)

        chat_input = page.get_by_placeholder("Ask about your supply chain...")
        await chat_input.click()
        await chat_input.fill("What's my highest-risk SKU?")
        await page.keyboard.press("Enter")
        print("  Q1: 'What's my highest-risk SKU?'")
        await asyncio.sleep(15)

        await chat_input.fill("Compare SUP-001 vs SUP-002 reliability")
        await page.keyboard.press("Enter")
        print("  Q2: 'Compare SUP-001 vs SUP-002 reliability'")
        await asyncio.sleep(15)

        # ------------------------------------------------------------------
        # 02:40–03:00  Hold final state
        # ------------------------------------------------------------------
        await asyncio.sleep(5)

        print("Recording complete — closing browser")
        video_path = await page.video.path()
        await context.close()
        await browser.close()

    return video_path


# ---------------------------------------------------------------------------
# Video conversion
# ---------------------------------------------------------------------------

def convert_to_mp4(webm_path: str):
    print(f"Converting to MP4...")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", webm_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(OUTPUT_MP4),
        ],
        check=True, capture_output=True,
    )
    Path(webm_path).unlink()
    for f in VIDEO_DIR.glob("*.webm"):
        f.unlink()
    try:
        VIDEO_DIR.rmdir()
    except OSError:
        pass
    print(f"  Saved: {OUTPUT_MP4}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    # 1. Reset DB + seed demo alert (no Gemini API needed)
    seed_demo_alert()

    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    # 2. Start API
    print("Starting API server...")
    api_proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "api.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if not wait_ready("http://localhost:8000/docs", "API :8000"):
        print("ERROR: API did not start")
        api_proc.kill()
        sys.exit(1)

    # 3. Start UI
    print("Starting Streamlit UI...")
    ui_proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "streamlit", "run", "ui/app.py",
         "--server.port", "8501"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if not wait_ready("http://localhost:8501", "UI :8501"):
        print("ERROR: UI did not start")
        api_proc.kill()
        ui_proc.kill()
        sys.exit(1)

    time.sleep(3)

    # 5. Record
    try:
        webm_path = asyncio.run(record_demo())
        convert_to_mp4(webm_path)
        print(f"\nDemo video ready: {OUTPUT_MP4}")
    except Exception as exc:
        print("Recording failed:", exc)
        raise
    finally:
        api_proc.kill()
        ui_proc.kill()
        print("Servers stopped.")


if __name__ == "__main__":
    main()
