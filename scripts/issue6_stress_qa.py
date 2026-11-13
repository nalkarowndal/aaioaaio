"""Issue #6: repeat real browser uploads and verify SQLite after reload.

Runs two upload paths per iteration with distinct browser sessions:
- staged: file-only submit followed by text submit
- combined: file + text in one submission

Requires an app running with AI_STUDIO_SINGLE_USER_HISTORY=1 and a dedicated
test SQLite database. Does not call Groq or store uploaded fixture bytes in DB.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


OWNER = "local:single-user"


def assert_saved(db_path: Path, question: str, filenames: list[str]) -> None:
    """Verify the user's question AND both filenames are in the SQLite row."""
    with sqlite3.connect(db_path, timeout=10) as con:
        rows = con.execute(
            "SELECT messages_json FROM conversations WHERE owner=? "
            "ORDER BY updated_at DESC LIMIT 50", (OWNER,)
        ).fetchall()
    candidates = [
        item
        for (raw,) in rows
        for item in json.loads(raw)
        if item.get("role") == "user"
        and item.get("content", "").startswith(question + "\n\n첨부: ")
    ]
    assert candidates, "SQLite did not persist the attachment-bearing user message"
    stored = candidates[-1]["content"]
    for filename in filenames:
        assert filename in stored, f"SQLite saved no reference to {filename}"


def run_trial(browser, url: str, db_path: Path, iteration: int, mode: str, output: Path) -> dict:
    label = f"issue6-{iteration:02d}-{mode}"
    question = f"Issue #6 upload regression {label}"
    filenames = [f"{label}-alpha.txt", f"{label}-beta.txt"]
    record = {"iteration": iteration, "mode": mode, "files": filenames}
    started = time.monotonic()
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.locator("h1").first.wait_for(state="visible", timeout=30000)
        input_el = page.locator('[data-testid="stChatInput"]').first
        input_el.wait_for(state="visible", timeout=15000)

        with page.expect_file_chooser() as chooser:
            input_el.locator('[data-testid="stChatInputFileUploadButton"]').click()
        chooser.value.set_files([
            {"name": filenames[0], "mimeType": "text/plain",
             "buffer": f"issue6 sentinel {label} alpha".encode("utf-8")},
            {"name": filenames[1], "mimeType": "text/plain",
             "buffer": f"issue6 sentinel {label} beta".encode("utf-8")},
        ])
        page.keyboard.press("Escape")
        page.locator('[data-testid="stApp"]').click(
            position={"x": 0, "y": 0}, force=True
        )
        for filename in filenames:
            input_el.get_by_text(filename, exact=False).first.wait_for(
                state="visible", timeout=20000
            )

        # Wait for the native composer upload to settle before submission.
        page.wait_for_timeout(500)
        if mode == "staged":
            input_el.locator('[data-testid="stChatInputSubmitButton"]').click()
            page.get_by_text("첨부파일 2/8 · 관리", exact=False).first.wait_for(
                state="visible", timeout=20000
            )

        textarea = page.locator('[data-testid="stChatInput"] textarea').first
        textarea.fill(question)
        if mode == "combined":
            input_el.locator('[data-testid="stChatInputSubmitButton"]').click()
        else:
            textarea.press("Enter")

        user_msg = page.locator('[data-testid="stChatMessage"]').filter(
            has_text=question
        ).last
        user_msg.wait_for(state="visible", timeout=20000)
        for filename in filenames:
            user_msg.locator('[data-testid="stMarkdownContainer"]').filter(
                has_text=filename
            ).first.wait_for(state="visible", timeout=15000)
        record["display"] = "pass"

        assert_saved(db_path, question, filenames)
        record["sqlite"] = "pass"

        page.reload(wait_until="domcontentloaded", timeout=30000)
        restored = page.locator('[data-testid="stChatMessage"]').filter(
            has_text=question
        ).last
        restored.wait_for(state="visible", timeout=30000)
        for filename in filenames:
            restored.locator('[data-testid="stMarkdownContainer"]').filter(
                has_text=filename
            ).first.wait_for(state="visible", timeout=15000)
        record["reload"] = "pass"
        record["status"] = "pass"
    except Exception as exc:
        record["status"] = "fail"
        record["error"] = f"{type(exc).__name__}: {str(exc)[:450]}"
        try:
            page.screenshot(path=str(output / (label + "_failure.png")), full_page=True)
        except Exception:
            pass
    finally:
        record["seconds"] = round(time.monotonic() - started, 2)
        context.close()
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8502")
    parser.add_argument("--db", required=True)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--output", default="docs/screenshots/issue6")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 30:
        raise ValueError("iterations must be 1-30")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    db = Path(args.db)
    if not db.is_file():
        raise AssertionError("Expected P6 QA SQLite database does not exist")

    records = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for iteration in range(1, args.iterations + 1):
                for mode in ("staged", "combined"):
                    records.append(run_trial(
                        browser, args.url, db, iteration, mode, output
                    ))
                    (output / "qa_report.json").write_text(
                        json.dumps(records, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
        finally:
            browser.close()

    success = sum(r["status"] == "pass" for r in records)
    print(f"ISSUE6 STRESS RESULT {success}/{len(records)} passed", flush=True)
    if success != len(records):
        raise AssertionError(f"Issue #6 reproduced in {len(records) - success} trials")


if __name__ == "__main__":
    main()
