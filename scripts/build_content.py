#!/usr/bin/env python3
"""Pull built quiz pages in from the content repo.

    python3 scripts/build_content.py [--content-repo PATH] [--ref REF | --working-tree]

For every quiz in content/manifest.json this runs the content repo's own
tools/build_college.py (which makes a self-contained single-file copy), then
copies the result to content/built/<id>.html. Quizzes are never edited here:
change them in the content repo and run this again.

By default it builds from the content repo's last commit (HEAD), exported to a
temporary folder, so uncommitted work in progress never reaches the showcase.
--ref builds from another commit, tag or branch; --working-tree builds from the
files as they are on disk.

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
    which = ap.add_mutually_exclusive_group()
    which.add_argument("--ref", default="HEAD", help="commit, tag or branch to build from (default HEAD)")
    which.add_argument("--working-tree", action="store_true", help="build from uncommitted files on disk")
    args = ap.parse_args()

    repo = Path(args.content_repo).resolve()
    if not (repo / "tools" / "build_college.py").exists():
        print(f"Can't find {repo / 'tools' / 'build_college.py'}. Pass --content-repo.", file=sys.stderr)
        return 1

    def git(*cmd):
        return subprocess.run(["git", "-C", str(repo), *cmd], capture_output=True, text=True)

    quizzes = json.loads(MANIFEST.read_text())["quizzes"]
    with tempfile.TemporaryDirectory() as tmp:
        if args.working_tree:
            src_root = repo
            label = f"the working tree at commit {git('rev-parse', '--short', 'HEAD').stdout.strip()}"
            if git("status", "--porcelain").stdout.strip():
                label += ", with uncommitted changes"
        else:
            commit = git("rev-parse", "--short", args.ref + "^{commit}").stdout.strip()
            if not commit:
                print(f"'{args.ref}' isn't a commit in {repo}.", file=sys.stderr)
                return 1
            src_root = Path(tmp) / "src"
            src_root.mkdir()
            archive = subprocess.run(["git", "-C", str(repo), "archive", commit], capture_output=True, check=True)
            subprocess.run(["tar", "-x", "-C", str(src_root)], input=archive.stdout, check=True)
            label = f"commit {commit}"
            if git("status", "--porcelain").stdout.strip():
                label += " (uncommitted changes in the content repo were left out)"
        build(quizzes, src_root, Path(tmp) / "out")

    print(f"Built from {label}")
    return 0


def build(quizzes, src_root: Path, out: Path) -> None:
    builder = src_root / "tools" / "build_college.py"
    out.mkdir()

    BUILT.mkdir(parents=True, exist_ok=True)
    wanted = {q["id"] for q in quizzes}
    for old in BUILT.glob("*.html"):
        if old.stem not in wanted:
            old.unlink()
            print(f"removed {old.name} (no longer in the manifest)")

    for q in quizzes:
        src = src_root / q["source"]
        subprocess.run([sys.executable, str(builder), str(src), "--out", str(out)], check=True, cwd=src_root,
                       stdout=subprocess.DEVNULL)
        built = out / (src.stem + "_college.html")
        dest = BUILT / f"{q['id']}.html"
        shutil.copyfile(built, dest)
        print(f"{q['id']}: {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
