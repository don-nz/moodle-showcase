#!/usr/bin/env python3
"""Pull built quiz pages in from the content repo.

    python3 scripts/build_content.py [--content-repo PATH]

For every quiz in content/manifest.json this runs the content repo's own
tools/build_college.py (which makes a self-contained single-file copy), then
copies the result to content/built/<id>.html. Quizzes are never edited here:
change them in the content repo and run this again.

The content repo defaults to $CONTENT_REPO, else ../tafe/electronics.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "content" / "manifest.json"
BUILT = ROOT / "content" / "built"


def main() -> int:
    import os
    default_repo = os.environ.get("CONTENT_REPO") or str(ROOT.parent / "tafe" / "electronics")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content-repo", default=default_repo)
    args = ap.parse_args()

    repo = Path(args.content_repo).resolve()
    builder = repo / "tools" / "build_college.py"
    if not builder.exists():
        print(f"Can't find {builder}. Pass --content-repo.", file=sys.stderr)
        return 1

    quizzes = json.loads(MANIFEST.read_text())["quizzes"]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown"
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()

    BUILT.mkdir(parents=True, exist_ok=True)
    wanted = {q["id"] for q in quizzes}
    for old in BUILT.glob("*.html"):
        if old.stem not in wanted:
            old.unlink()
            print(f"removed {old.name} (no longer in the manifest)")

    with tempfile.TemporaryDirectory() as out:
        for q in quizzes:
            src = repo / q["source"]
            subprocess.run([sys.executable, str(builder), str(src), "--out", out], check=True, cwd=repo,
                           stdout=subprocess.DEVNULL)
            built = Path(out) / (src.stem + "_college.html")
            dest = BUILT / f"{q['id']}.html"
            shutil.copyfile(built, dest)
            print(f"{q['id']}: {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")

    print(f"Built from content repo commit {commit}" + (" (with uncommitted changes)" if dirty else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
