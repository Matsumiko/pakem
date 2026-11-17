"""English-first docs: the Indonesian README is a mirror, not a fork.

The agent-facing docs are English on purpose; README is the human front page and
keeps a translated twin. These tests make the two failure modes visible:
commands that drift between the twins, and a skill description that a skill
index truncates before the trigger word.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"```.*?```", re.S)

def github_slug(heading: str) -> str:
    """GitHub anchor: lowercase, punctuation dropped, spaces become hyphens (emoji vanish)."""
    return re.sub(r"[^\w\s\-]", "", heading.lower()).replace(" ", "-")


class ReadmePair(unittest.TestCase):
    def test_both_files_exist(self):
        self.assertTrue((ROOT / "README.md").is_file())
        self.assertTrue((ROOT / "README-ID.md").is_file())

    def test_language_links_point_at_each_other(self):
        en = (ROOT / "README.md").read_text(encoding="utf-8")
        idn = (ROOT / "README-ID.md").read_text(encoding="utf-8")
        self.assertIn("[English](README.md)", en)
        self.assertIn("[Bahasa Indonesia](README-ID.md)", en)
        self.assertIn("[English](README.md)", idn)
        self.assertIn("[Bahasa Indonesia](README-ID.md)", idn)

    def test_code_blocks_are_identical(self):
        """A CLI change must land in both READMEs; prose may differ, commands may not."""
        en = (ROOT / "README.md").read_text(encoding="utf-8")
        idn = (ROOT / "README-ID.md").read_text(encoding="utf-8")
        self.assertEqual(sorted(FENCE.findall(en)), sorted(FENCE.findall(idn)),
                         "README.md and README-ID.md code blocks diverged")

    def test_table_of_contents_anchors_resolve(self):
        """The arc ToC is hand-written; a renamed heading must not leave a dead link."""
        for name in ("README.md", "README-ID.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            headings = {github_slug(m.group(1))
                        for m in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", FENCE.sub("", text))}
            anchors = set(re.findall(r"\]\(#([^)]+)\)", text))
            self.assertEqual(sorted(anchors - headings), [], f"{name} ToC points at missing headings")

    def test_heading_levels_match(self):
        """The twins may use different words, but the outline must stay parallel."""
        def levels(name: str) -> list[int]:
            text = FENCE.sub("", (ROOT / name).read_text(encoding="utf-8"))
            return [len(m.group(1)) for m in re.finditer(r"(?m)^(#{1,6})\s", text)]

        self.assertEqual(levels("README.md"), levels("README-ID.md"))

    def test_local_images_exist(self):
        for name in ("README.md", "README-ID.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            sources = re.findall(r'<img[^>]+src="([^"]+)"', text)
            sources += re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
            for src in sources:
                if src.startswith(("http://", "https://", "data:")):
                    continue
                self.assertTrue((ROOT / src).is_file(), f"{name}: missing image {src}")


class SkillIndex(unittest.TestCase):
    def test_description_keeps_trigger_and_fits_index_budget(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r'(?m)^description:\s*"([^"]+)"\s*$', text)
        self.assertIsNotNone(match, "SKILL.md frontmatter description missing")
        description = match.group(1)
        self.assertIn("pakem", description.lower())
        # Skill indexes truncate around 57 characters; the trigger word must stay visible.
        self.assertLessEqual(len(description), 57, description)


if __name__ == "__main__":
    unittest.main()
