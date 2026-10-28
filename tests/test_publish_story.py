from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.publish_story import parse_draft, publish_from_zip


APPROVED_DRAFT = """# Where did VER find the lap-time advantage?

**Review status:** Approved for publishing

**Editorial priority:** 81.0 / heuristic score

2026 Test Event · Race · VER lap 3 vs HAM lap 4

Where did VER find the lap-time advantage?

On these selected laps, VER was quicker overall. The next question is where the difference appears—not what caused it.

WHAT THE DATA SHOWS
• VER, lap 3: 90.100 s.
• HAM, lap 4: 90.300 s.

WHAT IT DOESN'T PROVE
This compares the selected laps only. It does not control for tyre age or traffic.

Independent analysis using public session data. Corner references and sampled values are approximate.

#F1 #Formula1

---

**Evidence caveat:** This compares the selected laps only. It does not control for tyre age or traffic.
"""


def test_parse_draft_extracts_title_evidence_and_caveat():
    post = parse_draft(APPROVED_DRAFT, "2026-10-28")
    assert post["title"] == "Where did VER find the lap-time advantage?"
    assert post["date"] == "2026-10-28"
    assert post["evidence"] == ["VER, lap 3: 90.100 s.", "HAM, lap 4: 90.300 s."]
    assert "does not control" in post["caveat"]
    assert "VER was quicker overall" in post["excerpt"]


def test_unapproved_draft_is_rejected():
    with pytest.raises(ValueError, match="not marked as approved"):
        parse_draft(APPROVED_DRAFT.replace("Approved for publishing", "Needs review"), "2026-10-28")


def test_publish_appends_json_and_prevents_duplicates(tmp_path: Path):
    archive_path = tmp_path / "approved.zip"
    posts_path = tmp_path / "posts.json"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("draft-01-ver-lap.md", APPROVED_DRAFT)
    post = publish_from_zip(archive_path, "draft-01-ver-lap.md", "2026-10-28", posts_path)
    assert post["title"].startswith("Where did VER")
    saved = json.loads(posts_path.read_text(encoding="utf-8"))
    assert len(saved) == 1
    with pytest.raises(ValueError, match="already exists"):
        publish_from_zip(archive_path, "draft-01-ver-lap.md", "2026-10-28", posts_path)
    assert len(json.loads(posts_path.read_text(encoding="utf-8"))) == 1
