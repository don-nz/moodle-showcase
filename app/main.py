"""FastAPI app: the LTI endpoints, the quiz page and the score API."""
import html
import json
import ssl
import time

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import Settings, load_settings
from .db import Database
from .keys import ToolKeys
from .catalog import load_catalog
from .lti import SCOPE_SCORE, DeepLinkRequest, LtiError, LtiTool

SCORE_TOKEN_HOURS = 6
PICKER_TOKEN_MINUTES = 30
STATE_COOKIE = "lti_state"

# Added to every served quiz page, just before </body>. The quiz engine's own
# globals (QUESTIONS, Q, isAnswerCorrect, showSummary, resetQuiz) are wrapped,
# not changed: the score is counted when the summary appears, once per attempt.
SCORE_SCRIPT = """
<script>
(function () {
  var TOKEN = __TOKEN__;
  var sent = false, box = null;
  function banner(text, state, retry) {
    if (!box) {
      box = document.createElement('div');
      box.setAttribute('role', 'status');
      box.style.cssText = 'position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:9999;' +
        'max-width:min(92vw,560px);padding:10px 16px;border-radius:8px;font:600 15px/1.4 system-ui,sans-serif;' +
        'box-shadow:0 4px 16px rgba(0,0,0,.25);color:#fff';
      document.body.appendChild(box);
    }
    box.style.background = state === 'ok' ? '#1d7a46' : state === 'error' ? '#b3261e' : '#3a4a5c';
    box.textContent = text + ' ';
    if (retry) {
      var b = document.createElement('button');
      b.textContent = 'Try again';
      b.style.cssText = 'margin-left:8px;font:inherit;padding:2px 10px;border-radius:6px;border:0;cursor:pointer';
      b.onclick = report;
      box.appendChild(b);
    }
  }
  function report() {
    if (sent) return;
    sent = true;
    var total = QUESTIONS.length, right = 0;
    for (var i = 0; i < total; i++) if (isAnswerCorrect(QUESTIONS[i], Q[i])) right++;
    banner('Sending your score (' + right + ' / ' + total + ')…', 'busy');
    fetch('/api/score', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: TOKEN, score: right, max: total })
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, j: j }; });
    }).then(function (res) {
      var failed = !res.ok || res.j.status === 'error';
      if (failed) sent = false;
      banner(res.j.message || 'Your score could not be sent.', failed ? 'error' : 'ok', failed);
    }).catch(function () {
      sent = false;
      banner('Your score could not be sent. Check your connection.', 'error', true);
    });
  }
  if (typeof showSummary !== 'function') return;
  var origSummary = showSummary, origReset = resetQuiz;
  window.showSummary = function () {
    var r = origSummary.apply(this, arguments);
    try { report(); } catch (e) { console.error(e); }
    return r;
  };
  window.resetQuiz = function () {
    sent = false;
    if (box) { box.remove(); box = null; }
    return origReset.apply(this, arguments);
  };
})();
</script>
"""


def page(title: str, message: str, status: int = 200, extra: str = "") -> HTMLResponse:
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>:root{{--muted:#5b6675;--line:#d0d7de;--panel:#f6f8fa}}
body{{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;color:#1b2430;background:#fff}}
@media (prefers-color-scheme: dark){{:root{{--muted:#9aa5b1;--line:#30363d;--panel:#161b22}}
body{{color:#e6edf3;background:#11161c}}}}</style></head>
<body><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>{extra}</body></html>"""
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def create_app(settings: Settings | None = None, http: httpx.Client | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.data_dir / "tool.db")
    keys = ToolKeys(settings.data_dir)
    # ssl.create_default_context() uses the system trust store, which holds the
    # mkcert root on the demo VMs (httpx would otherwise use certifi's list).
    http = http or httpx.Client(verify=ssl.create_default_context(), follow_redirects=False)
    tool = LtiTool(settings, db, keys, http)

    app = FastAPI(title=settings.tool_name, docs_url=None, redoc_url=None, openapi_url=None)

    def catalog():
        return load_catalog(settings.content_dir)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return page(settings.tool_name, "This is an LTI 1.3 tool. Add it to a Moodle course to use it.")

    @app.get("/.well-known/jwks.json")
    def jwks():
        return JSONResponse(keys.jwks)

    @app.api_route("/lti/login", methods=["GET", "POST"])
    async def login(request: Request):
        params = dict(request.query_params)
        if request.method == "POST":
            params.update({k: v for k, v in (await request.form()).items() if isinstance(v, str)})
        try:
            url, state = tool.login(params)
        except LtiError as e:
            return page("Can't start the activity", str(e), 400)
        resp = RedirectResponse(url, status_code=302)
        resp.set_cookie(STATE_COOKIE, state, max_age=600, secure=True, httponly=True, samesite="none")
        return resp

    @app.post("/lti/launch")
    async def launch(request: Request):
        form = await request.form()
        items = catalog()
        try:
            launch = tool.launch(str(form.get("id_token") or ""), str(form.get("state") or ""),
                                 request.cookies.get(STATE_COOKIE), list(items))
        except LtiError as e:
            return page("Can't open the activity", str(e), 400)

        if isinstance(launch, DeepLinkRequest):
            resp = picker_page(launch, items)
            resp.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite="none")
            return resp

        token = jwt.encode({"launch": launch.id, "exp": int(time.time()) + SCORE_TOKEN_HOURS * 3600},
                           keys.session_secret, algorithm="HS256")
        quiz_html = (settings.content_dir / f"{launch.quiz_id}.html").read_text(encoding="utf-8")
        script = SCORE_SCRIPT.replace("__TOKEN__", json.dumps(token)) if items[launch.quiz_id].graded else ""
        cut = quiz_html.lower().rfind("</body>")
        quiz_html = quiz_html[:cut] + script + quiz_html[cut:] if cut >= 0 else quiz_html + script
        resp = HTMLResponse(quiz_html, headers={"Cache-Control": "no-store"})
        resp.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite="none")
        return resp

    def picker_page(request: DeepLinkRequest, items) -> HTMLResponse:
        token = jwt.encode({"dl": {"platform_id": request.platform_id, "deployment_id": request.deployment_id,
                                   "return_url": request.return_url, "data": request.data},
                            "exp": int(time.time()) + PICKER_TOKEN_MINUTES * 60},
                           keys.session_secret, algorithm="HS256")
        groups: dict[str, list] = {}
        for item in items.values():
            groups.setdefault(item.topic or "Other", []).append(item)
        sections = []
        for topic, group in groups.items():
            buttons = "".join(
                f'<button name="item" value="{html.escape(i.id)}"><span>{html.escape(i.title)}</span>'
                f'<small>{"Graded" if i.graded else "Not graded"}</small></button>' for i in group)
            sections.append(f"<h2>{html.escape(topic)}</h2>{buttons}")
        style = """<style>
h2{font-size:1rem;margin:24px 0 8px;color:var(--muted)}
form button{display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;
  text-align:left;font:inherit;padding:12px 14px;margin:0 0 8px;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:inherit;cursor:pointer}
form button:hover,form button:focus-visible{border-color:#2f6fd6;outline:none}
form small{color:var(--muted);white-space:nowrap}
</style>"""
        form = (f'<form method="post" action="/lti/deeplink"><input type="hidden" name="token" '
                f'value="{html.escape(token)}">{"".join(sections)}</form>')
        return page("Choose a quiz", "Pick what this activity should open. Graded quizzes get a "
                    "gradebook column.", extra=style + form)

    @app.post("/lti/deeplink")
    async def deeplink(request: Request):
        form = await request.form()
        items = catalog()
        try:
            dl = jwt.decode(str(form.get("token") or ""), keys.session_secret, algorithms=["HS256"])["dl"]
        except (jwt.PyJWTError, KeyError):
            return page("Choose a quiz", "This page has expired. Click Select content in Moodle again.", 400)
        item = items.get(str(form.get("item") or ""))
        if item is None:
            return page("Choose a quiz", "That quiz isn't available.", 400)
        request_ = DeepLinkRequest(dl["platform_id"], dl["deployment_id"], dl["return_url"], dl.get("data"))
        try:
            response_jwt = tool.deep_link_response(request_, item.id, item.title, item.graded)
        except LtiError as e:
            return page("Choose a quiz", str(e), 400)
        # Post the signed choice back to Moodle straight away.
        auto_post = (f'<form id="f" method="post" action="{html.escape(request_.return_url)}">'
                     f'<input type="hidden" name="JWT" value="{html.escape(response_jwt)}">'
                     f'<noscript><button>Continue</button></noscript></form>'
                     f'<script>document.getElementById("f").submit();</script>')
        return page("Choose a quiz", f"Sending your choice ({item.title}) to Moodle\u2026", extra=auto_post)

    @app.post("/api/score")
    async def score(request: Request):
        try:
            data = await request.json()
            claims = jwt.decode(str(data.get("token", "")), keys.session_secret, algorithms=["HS256"])
            score, max_score = data.get("score"), data.get("max")
        except (ValueError, AttributeError, jwt.PyJWTError):
            return JSONResponse({"status": "error", "message": "This quiz session has expired. "
                                 "Open the activity again from Moodle."}, status_code=401)
        if not (isinstance(score, int) and isinstance(max_score, int) and 0 < max_score <= 500
                and 0 <= score <= max_score):
            return JSONResponse({"status": "error", "message": "That score isn't valid."}, status_code=400)

        launch_row = db.get_launch(claims["launch"])
        if launch_row is None:
            return JSONResponse({"status": "error", "message": "Unknown quiz session."}, status_code=401)
        can_send = bool(launch_row["lineitem_url"]) and SCOPE_SCORE in (launch_row["ags_scopes"] or "").split()
        if not can_send:
            db.save_attempt(launch_row["id"], score, max_score, False, "no gradebook item")
            return {"status": "recorded",
                    "message": f"Score {score} / {max_score}. This activity has no gradebook item, "
                               "so nothing was sent to Moodle."}
        try:
            tool.send_score(launch_row, score, max_score)
        except LtiError as e:
            db.save_attempt(launch_row["id"], score, max_score, False, str(e))
            return JSONResponse({"status": "error", "message": "Your score couldn't be sent to Moodle."},
                                status_code=502)
        db.save_attempt(launch_row["id"], score, max_score, True, None)
        return {"status": "sent", "message": f"Score {score} / {max_score} sent to the Moodle gradebook."}

    @app.get("/lti/register", response_class=HTMLResponse)
    def register(openid_configuration: str = "", registration_token: str | None = None):
        if not openid_configuration:
            return page("Registration", "Start registration from Moodle: Site administration → "
                        "Plugins → Activity modules → External tool → Manage tools.", 400)
        try:
            issuer = tool.register(openid_configuration, registration_token)
        except LtiError as e:
            return page("Registration failed", str(e), 400)
        # Tells Moodle's registration dialog that the tool has finished.
        close = "<script>(window.opener||window.parent).postMessage({subject:'org.imsglobal.lti.close'},'*');</script>"
        return page("Registered", f"{settings.tool_name} is registered with {issuer}. "
                    "You can close this window.", extra=close)

    return app

