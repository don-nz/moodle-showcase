# Quiz Showcase: LTI 1.3 tool for Moodle

Serves the electronics quizzes to Moodle over LTI 1.3 and returns scores to the
Moodle gradebook (AGS). The quizzes are authored in the content repo; this repo
only holds built copies in `content/built/`.

## Layout

| Path | What it is |
|---|---|
| `app/lti.py` | LTI 1.3: login, launch checks, content selection, grade return, dynamic registration |
| `app/catalog.py` | Reads `content/manifest.json` |
| `app/main.py` | Web routes, and the score script added to each quiz page |
| `app/db.py` | SQLite: platforms, launches, attempts |
| `content/manifest.json` | Which quizzes the tool serves |
| `scripts/build_content.py` | Rebuilds `content/built/` from the content repo |
| `deploy/` | Server setup scripts and `deploy.sh` |
| `docs/` | Server setup guide and showcase course sheet |
| `tests/` | End-to-end tests against a fake Moodle |

## On the laptop

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                  # tests
python3 scripts/build_content.py     # after committing quiz changes in the content repo (builds from its last commit)
deploy/deploy.sh aht-tools          # copy to the tool server and restart
```

## Setting up servers

[docs/server-setup.md](docs/server-setup.md) covers building both servers from scratch, behind
Cloudflare Tunnels, on PC VMs or at a hosting provider:
- `deploy/setup-moodle.sh` sets up the Moodle server.
- `deploy/setup-tools.sh` sets up the tool server.
- After that, `deploy/deploy.sh <host>` installs and updates the tool's code.

[docs/showcase-course.md](docs/showcase-course.md) has the two showcase courses, ready to paste.

## How quizzes are chosen

The quiz list comes from `content/manifest.json`, grouped by its `topic` field. As a fallback,
an activity can name a quiz with the custom parameter `quiz=<id>`. With neither, it opens the
first quiz in the manifest.

Only platforms listed in `TOOL_ALLOWED_ISSUERS` (in `/etc/quiz-tool.env`) can register.
To switch a college off, set `active = 0` on its row in the `platforms` table of
`/var/lib/quiz-tool/tool.db`.

## Limits of this phase

- Answers are still checked in the browser, and the browser reports the score, so a
  student who knows how could send a made-up score. Phase 2 moves marking to the server.
- Every finished attempt is sent, and Moodle keeps the latest.
