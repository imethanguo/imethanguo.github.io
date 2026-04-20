#!/usr/bin/env python3
"""
Auto-update lecture note links in _pages/cv.md from assets/pdf and assets/txt,
then optionally run git add/commit/push.

Usage:
  python bin/update_cv_resources.py
  python bin/update_cv_resources.py --no-push
  python bin/update_cv_resources.py --message "chore: update lecture notes"

Default behavior:
- Updates `_pages/cv.md` lecture link sections in current style.
- Runs `git add`, `git commit` (if needed), and `git push`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CV_PATH = ROOT / "_pages" / "cv.md"
PDF_DIR = ROOT / "assets" / "pdf"
TXT_DIR = ROOT / "assets" / "txt"

SECTION_ORDER = ["COMP 3711", "COMP 4211", "COMP 2012"]
DEFAULT_PDF_COURSE = "COMP 4211"
IGNORE_PDFS = {"example_pdf.pdf"}

COURSE_KEYWORDS = {
    "COMP 3711": [
        "asymptotic",
        "divide and conquer",
        "binary search",
        "merge sort",
        "inversion",
        "max subarray",
        "master theorem",
        "multiplication",
        "randomized",
    ],
    "COMP 4211": [
        "linear regression",
        "logistic regression",
        "bias-variance",
        "classification",
        "neural network",
        "feed-forward",
    ],
}


def run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def normalize_text(text: str) -> str:
    return text.strip().lower().replace("_", " ")


def encode_web_path(path: str) -> str:
    return quote(path, safe="/-_.~")


def filename_to_title(stem: str) -> str:
    title = stem.replace("_", " ").replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()
    return title.title()


def infer_pdf_course(filename: str, existing_course_map: dict[str, str]) -> str:
    rel = f"/assets/pdf/{filename}"
    if rel in existing_course_map:
        return existing_course_map[rel]

    check = normalize_text(filename.removesuffix(".pdf"))
    for course, words in COURSE_KEYWORDS.items():
        for keyword in words:
            if keyword in check:
                return course

    return DEFAULT_PDF_COURSE


def parse_existing_entries(body: str) -> tuple[dict[str, str], dict[str, str]]:
    course_by_link: dict[str, str] = {}
    title_by_link: dict[str, str] = {}

    pattern = re.compile(r"^- \[(COMP\s+\d{4})\s+(.+?)\]\((/assets/(?:pdf|txt)/[^)]+)\)$")
    for raw_line in body.splitlines():
        line = raw_line.strip()
        match = pattern.match(line)
        if not match:
            continue
        course = " ".join(match.group(1).split())
        title = match.group(2).strip()
        link = match.group(3).strip()
        course_by_link[link] = course
        title_by_link[link] = title

    return course_by_link, title_by_link


def sort_comp2012(name: str) -> tuple[int, float, str]:
    stem = name.removesuffix(".txt")
    low = stem.lower()
    if low.startswith("week"):
        week_num = re.search(r"\d+", low)
        week = int(week_num.group()) if week_num else 0
        return (0, float(week), low)
    try:
        return (1, float(stem), low)
    except ValueError:
        return (2, float("inf"), low)


def build_body(existing_body: str) -> str:
    existing_course_map, existing_title_map = parse_existing_entries(existing_body)

    sections: dict[str, list[str]] = {key: [] for key in SECTION_ORDER}

    pdf_files = sorted([p.name for p in PDF_DIR.glob("*.pdf") if p.name not in IGNORE_PDFS])
    for filename in pdf_files:
        link = f"/assets/pdf/{encode_web_path(filename)}"
        source_link = f"/assets/pdf/{filename}"

        course = infer_pdf_course(filename, existing_course_map)
        if course not in sections:
            sections[course] = []

        title = existing_title_map.get(source_link) or existing_title_map.get(link)
        if not title:
            title = filename_to_title(Path(filename).stem)

        sections[course].append(f"- [{course} {title}]({link})")

    txt_files = sorted([p.name for p in TXT_DIR.glob("*.txt")], key=sort_comp2012)
    for filename in txt_files:
        link = f"/assets/txt/{encode_web_path(filename)}"
        source_link = f"/assets/txt/{filename}"

        course = "COMP 2012"
        title = existing_title_map.get(source_link) or existing_title_map.get(link)
        if not title:
            stem = Path(filename).stem
            if stem.lower().startswith("week"):
                title = stem
            else:
                title = stem

        sections[course].append(f"- [{course} {title}]({link})")

    lines: list[str] = ["## Lecture Notes", ""]

    for course in SECTION_ORDER:
        lines.append(f"### {course}")
        lines.append("")
        entries = sections.get(course, [])
        if entries:
            lines.extend(entries)
        else:
            lines.append(f"- [{course} TBA](#)")
        lines.append("")

    extra_courses = sorted([k for k in sections.keys() if k not in SECTION_ORDER])
    for course in extra_courses:
        lines.append(f"### {course}")
        lines.append("")
        lines.extend(sections[course])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def update_cv() -> bool:
    content = CV_PATH.read_text(encoding="utf-8")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise RuntimeError("Invalid cv.md: missing YAML front matter")

    prefix, frontmatter, body = parts[0], parts[1], parts[2]
    new_body = "\n" + build_body(body.lstrip("\n"))
    new_content = "---" + frontmatter + "---" + new_body

    if new_content == content:
        return False

    CV_PATH.write_text(new_content, encoding="utf-8")
    return True


def git_commit_and_push(message: str, do_push: bool) -> None:
    run(["git", "add", str(CV_PATH.relative_to(ROOT)), "assets/pdf", "assets/txt"])

    commit_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=ROOT, text=True, capture_output=True
    )

    if commit_check.returncode == 0:
        print("No staged changes to commit.")
        return

    run(["git", "commit", "-m", message])
    print("Committed changes.")

    if do_push:
        run(["git", "push"])
        print("Pushed to remote.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-update cv.md lecture resource links")
    parser.add_argument("--no-push", action="store_true", help="Do not run git push")
    parser.add_argument(
        "--message",
        default="chore: auto-update lecture note links",
        help="Commit message used for git commit",
    )
    args = parser.parse_args()

    changed = update_cv()
    if changed:
        print("Updated _pages/cv.md")
    else:
        print("_pages/cv.md already up to date")

    git_commit_and_push(message=args.message, do_push=not args.no_push)


if __name__ == "__main__":
    main()
