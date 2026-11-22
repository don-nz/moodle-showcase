"""End-to-end tests against a fake Moodle (no network)."""
import json
import re
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ISS = "https://moodle.test"
CLIENT_ID = "client-abc"
DEPLOYMENT = "7"
LINEITEM = f"{ISS}/mod/lti/services.php/2/lineitems/5/lineitem?type_id=1"
CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
QUIZ_HTML = "<html><body><h1>Quiz</h1></body></html>"


class FakeMoodle:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="moodle-kid", alg="RS256", use="sig")
        self.jwks = {"keys": [jwk]}
        self.scores = []
        self.registrations = []
        self.tool_jwks = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{ISS}/mod/lti/certs.php":
            return httpx.Response(200, json=self.jwks)
        if url == f"{ISS}/mod/lti/token.php":
            form = parse_qs(request.content.decode())
            assertion = form["client_assertion"][0]
            # Check the tool signed its request with the key it publishes.
            key = jwt.PyJWKSet.from_dict(self.tool_jwks).keys[0].key
            claims = jwt.decode(assertion, key, algorithms=["RS256"], audience=f"{ISS}/mod/lti/token.php")
            assert claims["iss"] == claims["sub"] == CLIENT_ID
            assert form["scope"] == ["https://purl.imsglobal.org/spec/lti-ags/scope/score"]
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
        if url.startswith(f"{ISS}/mod/lti/services.php/2/lineitems/5/lineitem/scores"):
            assert request.headers["authorization"] == "Bearer tok-123"
            assert request.url.params["type_id"] == "1"
            self.scores.append(json.loads(request.content))
            return httpx.Response(200)
        if url == f"{ISS}/mod/lti/openid-configuration.php":
            return httpx.Response(200, json={
                "issuer": ISS,
                "authorization_endpoint": f"{ISS}/mod/lti/auth.php",
                "token_endpoint": f"{ISS}/mod/lti/token.php",
                "jwks_uri": f"{ISS}/mod/lti/certs.php",
                "registration_endpoint": f"{ISS}/mod/lti/openid-registration.php",
            })
        if url == f"{ISS}/mod/lti/openid-registration.php":
            assert request.headers["authorization"] == "Bearer reg-token"
            self.registrations.append(json.loads(request.content))
            return httpx.Response(200, json={
                "client_id": CLIENT_ID,
                "https://purl.imsglobal.org/spec/lti-tool-configuration": {"deployment_id": DEPLOYMENT},
            })
        return httpx.Response(404)

    def id_token(self, nonce, **overrides):
        now = int(time.time())
        claims = {
            "iss": ISS, "aud": CLIENT_ID, "sub": "user-42", "name": "Student One",
            "iat": now, "exp": now + 300, "nonce": nonce,
            CLAIM + "version": "1.3.0",
            CLAIM + "message_type": "LtiResourceLinkRequest",
            CLAIM + "deployment_id": DEPLOYMENT,
            CLAIM + "resource_link": {"id": "rl-1"},
            CLAIM + "context": {"id": "c-1", "title": "Showcase"},
            "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint": {
                "scope": ["https://purl.imsglobal.org/spec/lti-ags/scope/score"],
                "lineitem": LINEITEM,
            },
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "moodle-kid"})


@pytest.fixture
def env(tmp_path):
    content = tmp_path / "content" / "built"
    content.mkdir(parents=True)
    for name in ("quiz-a", "quiz-b", "sim-c"):
        (content / f"{name}.html").write_text(QUIZ_HTML)
    (content.parent / "manifest.json").write_text(json.dumps({"quizzes": [
        {"id": "quiz-a", "title": "Quiz A", "topic": "Topic 1", "graded": True},
        {"id": "quiz-b", "title": "Quiz B", "topic": "Topic 1", "graded": True},
        {"id": "sim-c", "title": "Sim C", "topic": "Simulators", "graded": False},
        {"id": "not-built", "title": "Missing", "topic": "Topic 1", "graded": True},
    ]}))
    settings = Settings(base_url="https://tools.test", data_dir=tmp_path / "data", content_dir=content,
                        allowed_issuers=(ISS,), tool_name="Test Tool")
    moodle = FakeMoodle()
    app = create_app(settings, httpx.Client(transport=httpx.MockTransport(moodle.handler)))
    client = TestClient(app, base_url="https://tools.test", follow_redirects=False)
    moodle.tool_jwks = client.get("/.well-known/jwks.json").json()
    return client, moodle


def register(client):
    r = client.get("/lti/register", params={
        "openid_configuration": f"{ISS}/mod/lti/openid-configuration.php", "registration_token": "reg-token"})
    assert r.status_code == 200, r.text
    return r


def login(client):
    r = client.post("/lti/login", data={"iss": ISS, "login_hint": "hint", "client_id": CLIENT_ID,
                                        "target_link_uri": "https://tools.test/lti/launch"})
    assert r.status_code == 302, r.text
    q = parse_qs(urlsplit(r.headers["location"]).query)
    return q["state"][0], q["nonce"][0], r


def launch(client, moodle, **overrides):
    state, nonce, _ = login(client)
    return client.post("/lti/launch", data={"state": state, "id_token": moodle.id_token(nonce, **overrides)})


def score_token(page_html):
    return json.loads(re.search(r"var TOKEN = (\"[^\"]+\")", page_html).group(1))


def test_registration_stores_platform_and_sends_tool_details(env):
    client, moodle = env
    r = register(client)
    assert "org.imsglobal.lti.close" in r.text
    reg = moodle.registrations[0]
    assert reg["initiate_login_uri"] == "https://tools.test/lti/login"
    assert reg["redirect_uris"] == ["https://tools.test/lti/launch"]
    assert reg["jwks_uri"] == "https://tools.test/.well-known/jwks.json"


def test_registration_refuses_unlisted_platform(env):
    client, moodle = env
    r = client.get("/lti/register", params={"openid_configuration": "https://evil.test/openid"})
    assert r.status_code == 400
    assert not moodle.registrations


def test_login_redirects_to_moodle_with_state_and_nonce(env):
    client, _ = env
    register(client)
    state, nonce, r = login(client)
    target = urlsplit(r.headers["location"])
    q = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{ISS}/mod/lti/auth.php"
    assert q["redirect_uri"] == ["https://tools.test/lti/launch"]
    assert q["client_id"] == [CLIENT_ID] and state and nonce
    assert "samesite=none" in r.headers["set-cookie"].lower()


def test_login_refuses_unregistered_platform(env):
    client, _ = env
    r = client.post("/lti/login", data={"iss": ISS, "login_hint": "x"})
    assert r.status_code == 400


def test_launch_serves_quiz_with_score_script(env):
    client, moodle = env
    register(client)
    r = launch(client, moodle)
    assert r.status_code == 200, r.text
    assert "<h1>Quiz</h1>" in r.text and "/api/score" in r.text
    assert r.text.index("/api/score") < r.text.index("</body>")


def test_launch_picks_quiz_from_custom_parameter(env):
    client, moodle = env
    register(client)
    assert launch(client, moodle, **{CLAIM + "custom": {"quiz": "quiz-b"}}).status_code == 200
    r = launch(client, moodle, **{CLAIM + "custom": {"quiz": "nope"}})
    assert r.status_code == 400 and "nope" in r.text


@pytest.mark.parametrize("overrides", [
    {"aud": "someone-else"},
    {"iss": "https://other.test"},
    {"exp": int(time.time()) - 3600},
    {CLAIM + "deployment_id": "999"},
    {CLAIM + "version": "1.1"},
    {"sub": None},
])
def test_launch_rejects_bad_tokens(env, overrides):
    client, moodle = env
    register(client)
    assert launch(client, moodle, **overrides).status_code == 400


def test_launch_rejects_wrong_signature(env):
    client, moodle = env
    register(client)
    state, nonce, _ = login(client)
    moodle.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # not the published key
    r = client.post("/lti/launch", data={"state": state, "id_token": moodle.id_token(nonce)})
    assert r.status_code == 400


def test_launch_rejects_wrong_nonce_and_replay(env):
    client, moodle = env
    register(client)
    state, nonce, _ = login(client)
    bad = client.post("/lti/launch", data={"state": state, "id_token": moodle.id_token("other-nonce")})
    assert bad.status_code == 400
    # The state was used up by the failed attempt, so a replay fails too.
    again = client.post("/lti/launch", data={"state": state, "id_token": moodle.id_token(nonce)})
    assert again.status_code == 400


def test_launch_rejects_mismatched_state_cookie(env):
    client, moodle = env
    register(client)
    state, nonce, _ = login(client)
    client.cookies.set("lti_state", "something-else", domain="tools.test")
    r = client.post("/lti/launch", data={"state": state, "id_token": moodle.id_token(nonce)})
    assert r.status_code == 400


def test_score_goes_to_moodle_gradebook(env):
    client, moodle = env
    register(client)
    token = score_token(launch(client, moodle).text)
    r = client.post("/api/score", json={"token": token, "score": 7, "max": 10})
    assert r.status_code == 200 and r.json()["status"] == "sent", r.text
    sent = moodle.scores[0]
    assert sent["userId"] == "user-42"
    assert (sent["scoreGiven"], sent["scoreMaximum"]) == (7, 10)
    assert sent["activityProgress"] == "Completed" and sent["gradingProgress"] == "FullyGraded"


def test_score_without_gradebook_item_is_only_recorded(env):
    client, moodle = env
    register(client)
    ags = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"
    token = score_token(launch(client, moodle, **{ags: None}).text)
    r = client.post("/api/score", json={"token": token, "score": 3, "max": 4})
    assert r.json()["status"] == "recorded" and not moodle.scores


@pytest.mark.parametrize("body", [
    {"token": "forged", "score": 1, "max": 1},
    {"score": 1, "max": 1},
])
def test_score_rejects_bad_token(env, body):
    client, _ = env
    assert client.post("/api/score", json=body).status_code == 401


@pytest.mark.parametrize("score,max_score", [(11, 10), (-1, 10), (1, 0), ("5", 10), (1.5, 10)])
def test_score_rejects_impossible_values(env, score, max_score):
    client, moodle = env
    register(client)
    token = score_token(launch(client, moodle).text)
    assert client.post("/api/score", json={"token": token, "score": score, "max": max_score}).status_code == 400


DL = "https://purl.imsglobal.org/spec/lti-dl/claim/"
RETURN_URL = f"{ISS}/mod/lti/contentitem_return.php?course=2&id=1&sesskey=abc"


def deep_link_launch(client, moodle, settings=None):
    settings = settings or {"deep_link_return_url": RETURN_URL, "accept_types": ["ltiResourceLink"],
                            "data": "opaque-data"}
    return launch(client, moodle, **{CLAIM + "message_type": "LtiDeepLinkingRequest",
                                     DL + "deep_linking_settings": settings,
                                     "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint": None})


def pick(client, picker_html, item):
    token = re.search(r'name="token" value="([^"]+)"', picker_html).group(1)
    return client.post("/lti/deeplink", data={"token": token, "item": item})


def test_registration_offers_content_selection(env):
    client, moodle = env
    register(client)
    messages = moodle.registrations[0]["https://purl.imsglobal.org/spec/lti-tool-configuration"]["messages"]
    assert {m["type"] for m in messages} == {"LtiResourceLinkRequest", "LtiDeepLinkingRequest"}


def test_content_selection_lists_built_items_by_topic(env):
    client, moodle = env
    register(client)
    r = deep_link_launch(client, moodle)
    assert r.status_code == 200, r.text
    assert "Quiz A" in r.text and "Sim C" in r.text and "Simulators" in r.text
    assert "Missing" not in r.text  # in the manifest but not built


def test_content_selection_returns_signed_choice_to_moodle(env):
    client, moodle = env
    register(client)
    r = pick(client, deep_link_launch(client, moodle).text, "quiz-b")
    assert r.status_code == 200, r.text
    assert f'action="{RETURN_URL.replace("&", "&amp;")}"' in r.text
    response_jwt = re.search(r'name="JWT" value="([^"]+)"', r.text).group(1)
    key = jwt.PyJWKSet.from_dict(moodle.tool_jwks).keys[0].key
    claims = jwt.decode(response_jwt, key, algorithms=["RS256"], audience=ISS)
    assert claims["iss"] == CLIENT_ID
    assert claims[CLAIM + "message_type"] == "LtiDeepLinkingResponse"
    assert claims[CLAIM + "deployment_id"] == DEPLOYMENT
    assert claims[DL + "data"] == "opaque-data"
    item = claims[DL + "content_items"][0]
    assert item["custom"] == {"quiz": "quiz-b"} and item["url"] == "https://tools.test/lti/launch"
    assert item["lineItem"]["scoreMaximum"] == 100


def test_simulator_gets_no_gradebook_column_or_score_script(env):
    client, moodle = env
    register(client)
    r = pick(client, deep_link_launch(client, moodle).text, "sim-c")
    response_jwt = re.search(r'name="JWT" value="([^"]+)"', r.text).group(1)
    item = jwt.decode(response_jwt, options={"verify_signature": False})[DL + "content_items"][0]
    assert "lineItem" not in item
    page = launch(client, moodle, **{CLAIM + "custom": {"quiz": "sim-c"}})
    assert page.status_code == 200 and "/api/score" not in page.text


def test_content_selection_rejects_forged_picker_token_and_unknown_item(env):
    client, moodle = env
    register(client)
    assert client.post("/lti/deeplink", data={"token": "forged", "item": "quiz-a"}).status_code == 400
    assert pick(client, deep_link_launch(client, moodle).text, "not-built").status_code == 400


@pytest.mark.parametrize("settings", [
    {"deep_link_return_url": "https://evil.test/return", "accept_types": ["ltiResourceLink"]},
    {"deep_link_return_url": RETURN_URL, "accept_types": ["file"]},
    {"accept_types": ["ltiResourceLink"]},
])
def test_content_selection_rejects_bad_settings(env, settings):
    client, moodle = env
    register(client)
    assert deep_link_launch(client, moodle, settings).status_code == 400
