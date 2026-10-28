#!/usr/bin/env python3
"""Manually add one approved Apex Telemetry draft to the GitHub Pages newsroom.

This script only edits docs/posts.json locally. It does not commit, push, deploy,
contact Instagram, or publish anything without the user's explicit next steps.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POSTS_PATH = ROOT / "docs" / "posts.json"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80] or "f1-analysis"


def parse_draft(markdown: str, publish_date: str) -> dict[str, Any]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].startswith("# "):
        raise ValueError("Draft does not start with a Markdown headline.")
    title = lines[0][2:].strip()
    status_line = next((line for line in lines if line.lower().startswith("**review status:**")), "")
    if "approved" not in status_line.lower():
        raise ValueError("This draft is not marked as approved. Export approved drafts from the newsroom first.")

    priority_index = next((i for i, line in enumerate(lines) if line.startswith("**Editorial priority:**")), None)
    if priority_index is None:
        raise ValueError("Draft is missing its editorial priority section; expected the Apex Telemetry export format.")
    caption_lines: list[str] = []
    for line in lines[priority_index + 1:]:
        if line.strip() == "---":
            break
        caption_lines.append(line.rstrip())
    while caption_lines and not caption_lines[0].strip():
        caption_lines.pop(0)
    while caption_lines and not caption_lines[-1].strip():
        caption_lines.pop()

    # Remove the repeated headline from the caption, retaining session context.
    nonempty = [i for i, line in enumerate(caption_lines) if line.strip()]
    if len(nonempty) > 1 and caption_lines[nonempty[1]].strip() == title:
        caption_lines.pop(nonempty[1])

    evidence: list[str] = []
    body: list[str] = []
    caveat = ""
    mode = "body"
    for line in caption_lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper == "WHAT THE DATA SHOWS":
            mode = "evidence"
            continue
        if upper == "WHAT IT DOESN'T PROVE" or upper == "WHAT IT DOESN’T PROVE":
            mode = "caveat"
            continue
        if mode == "evidence":
            if stripped.startswith("• "):
                evidence.append(stripped[2:].strip())
            elif stripped:
                evidence.append(stripped)
        elif mode == "caveat":
            if stripped and not stripped.startswith("#") and not stripped.startswith("Independent analysis"):
                caveat = f"{caveat} {stripped}".strip()
            elif stripped.startswith("Independent analysis"):
                mode = "body"
                body.append(stripped)
            elif stripped.startswith("#"):
                body.append(stripped)
        elif stripped:
            body.append(stripped)

    excerpt = next((line for line in body if line and " · " not in line and not line.startswith("#") and not line.startswith("Independent analysis")), "Evidence-led analysis from selected Formula 1 session data.")
    category = "Race analysis"
    for candidate in ("Sector comparison", "Corner comparison", "Lap comparison"):
        if candidate == "Sector comparison" and "sector" in title.lower() or candidate == "Corner comparison" and "corner" in title.lower() or candidate == "Lap comparison" and ("lap" in title.lower() or "where did" in title.lower()):
            category = candidate
            break
    post_id = slugify(title)
    return {
        "id": post_id,
        "title": title,
        "date": publish_date,
        "category": category,
        "excerpt": excerpt,
        "body": body,
        "evidence": evidence,
        "caveat": caveat,
        "source_note": "Independent analysis from the selected session data. Review source/platform terms before publication.",
    }


def publish_from_zip(zip_path: Path, draft_name: str, publish_date: str, posts_path: Path = POSTS_PATH) -> dict[str, Any]:
    try:
        date.fromisoformat(publish_date)
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as archive:
        available = archive.namelist()
        if draft_name not in available:
            drafts = [name for name in available if name.lower().endswith(".md")]
            raise ValueError(f"Draft '{draft_name}' is not in the ZIP. Markdown drafts found: {', '.join(drafts) or 'none'}")
        if not draft_name.lower().endswith(".md"):
            raise ValueError("Select a .md draft file from the approved drafts ZIP.")
        markdown = archive.read(draft_name).decode("utf-8-sig")
    post = parse_draft(markdown, publish_date)

    posts_path.parent.mkdir(parents=True, exist_ok=True)
    if posts_path.exists():
        try:
            posts = json.loads(posts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{posts_path} contains invalid JSON; no changes were made.") from exc
    else:
        posts = []
    if not isinstance(posts, list):
        raise ValueError(f"{posts_path} must contain a JSON list; no changes were made.")
    if any(isinstance(existing, dict) and existing.get("id") == post["id"] for existing in posts):
        raise ValueError(f"A story with ID '{post['id']}' already exists in {posts_path}. No changes were made.")
    posts.append(post)
    posts.sort(key=lambda item: str(item.get("date", "")), reverse=True)
    posts_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return post


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually add one approved editorial draft to the Apex Telemetry website data.")
    parser.add_argument("--zip", required=True, type=Path, help="Path to apex-telemetry-approved-drafts.zip")
    parser.add_argument("--draft", required=True, help="Exact .md filename inside the ZIP (list with the PowerShell Expand-Archive command if needed)")
    parser.add_argument("--date", default=date.today().isoformat(), help="Publication date YYYY-MM-DD (default: today's date)")
    args = parser.parse_args()
    try:
        post = publish_from_zip(args.zip, args.draft, args.date)
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Added approved story: {post['title']}")
    print(f"Updated: {POSTS_PATH.relative_to(ROOT)}")
    print("NOT YET LIVE: review docs/posts.json, then commit and push your changes to GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
