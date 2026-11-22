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
| `deploy/` | nginx site, systemd unit, env example, `deploy.sh` |
| `tests/` | End-to-end tests against a fake Moodle |

## On the laptop

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                  # tests
python3 scripts/build_content.py     # after changing quizzes or the manifest
deploy/deploy.sh                     # copy to tools.test and restart
```

## First-time setup of the tools VM

Run once on **tools.test**:

```sh
sudo useradd --system --home /opt/quiz-tool --shell /usr/sbin/nologin quiztool
sudo mkdir -p /opt/quiz-tool && sudo python3 -m venv /opt/quiz-tool/.venv
```

Then, from the laptop, copy the config files across:

```sh
scp deploy/quiz-tool.env.example deploy/quiz-tool.service deploy/nginx-tools.conf tools.test:
```

And on **tools.test**:

```sh
sudo install -m 640 -g quiztool quiz-tool.env.example /etc/quiz-tool.env
sudo install -m 644 quiz-tool.service /etc/systemd/system/
sudo install -m 644 nginx-tools.conf /etc/nginx/sites-available/quiz-tool
sudo ln -s /etc/nginx/sites-available/quiz-tool /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl daemon-reload && sudo systemctl enable quiz-tool
sudo nginx -t && sudo systemctl reload nginx
rm quiz-tool.env.example quiz-tool.service nginx-tools.conf
```

Finally run `deploy/deploy.sh` from the laptop. It should end with `active`.
Check from the laptop: `curl https://tools.test/.well-known/jwks.json`.

## Adding the tool to Moodle

1. Log in to https://moodle.test as admin.
2. **Site administration → Plugins → Activity modules → External tool → Manage tools.**
3. In **Tool URL**, enter `https://tools.test/lti/register` and click **Add LTI Advantage**.
4. When the dialog closes, the tool shows as **pending**. Click **Activate**.
5. In the tool's settings (the pencil), check that grade sync (**IMS LTI Assignment and
   Grade Services**) is on.
6. Under **Tool configuration usage**, choose **Show in activity chooser and as a preconfigured tool**.
7. Tick **Supports Deep Linking (Content-Item Message)** and set **Content Selection URL** to
   `https://tools.test/lti/launch`. A tool registered after this feature was added already has these set.
8. In a course: turn on **Edit mode**, then **Add content → Activity or resource → Quiz Showcase**.
   Click **Select content**, pick a quiz, and save. Graded quizzes get their own gradebook column,
   out of 100. Simulators don't get one.

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
