"""LTI 1.3 tool side: OIDC login, launch validation, AGS scores, dynamic registration.

Specs: LTI Core 1.3, IMS Security Framework 1.0, LTI AGS 2.0, LTI Dynamic
Registration 1.0. PyJWT does the signing and verifying; this module does the
protocol checks around it.
"""
import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
import jwt

from .config import Settings
from .db import Database
from .keys import ToolKeys

CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
AGS_CLAIM = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"
SCOPE_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
SCOPE_LINEITEM_RO = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
TOOL_CONFIG = "https://purl.imsglobal.org/spec/lti-tool-configuration"
DL_CLAIM = "https://purl.imsglobal.org/spec/lti-dl/claim/"
MSG_RESOURCE = "LtiResourceLinkRequest"
MSG_DEEP_LINK = "LtiDeepLinkingRequest"

JWKS_CACHE_SECONDS = 3600
CLOCK_LEEWAY = 60


class LtiError(Exception):
    """A launch or registration was refused. The message is safe to show."""


@dataclass
class Launch:
    id: str
    quiz_id: str
    user_name: str | None
    can_send_grade: bool


@dataclass
class DeepLinkRequest:
    """A teacher choosing content while adding an activity in Moodle."""
    platform_id: int
    deployment_id: str
    return_url: str
    data: str | None


def same_host(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return pa.scheme == "https" and (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


class LtiTool:
    def __init__(self, settings: Settings, db: Database, keys: ToolKeys, http: httpx.Client):
        self.settings = settings
        self.db = db
        self.keys = keys
        self.http = http
        self._jwks: dict[str, tuple[float, jwt.PyJWKSet]] = {}
        self._tokens: dict[tuple[int, str], tuple[float, str]] = {}

    @property
    def launch_url(self) -> str:
        return self.settings.base_url + "/lti/launch"

    @property
    def login_url(self) -> str:
        return self.settings.base_url + "/lti/login"

    # 1. OIDC login initiation -------------------------------------------
    def login(self, params: dict) -> tuple[str, str]:
        """Return (URL to send the browser to, state)."""
        issuer = (params.get("iss") or "").rstrip("/")
        login_hint = params.get("login_hint")
        if not issuer or not login_hint:
            raise LtiError("The login request is missing iss or login_hint.")

        platforms = [p for p in self.db.find_platforms(issuer, params.get("client_id")) if p["active"]]
        if len(platforms) != 1:
            raise LtiError("This learning platform is not registered with the tool, or has been switched off.")
        platform = platforms[0]

        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.db.save_state(state, nonce, platform["id"])

        query = {
            "scope": "openid",
            "response_type": "id_token",
            "response_mode": "form_post",
            "prompt": "none",
            "client_id": platform["client_id"],
            "redirect_uri": self.launch_url,
            "login_hint": login_hint,
            "state": state,
            "nonce": nonce,
        }
        if params.get("lti_message_hint"):
            query["lti_message_hint"] = params["lti_message_hint"]
        sep = "&" if "?" in platform["auth_url"] else "?"
        return platform["auth_url"] + sep + urlencode(query), state

    # 2. Launch ----------------------------------------------------------
    def launch(self, id_token: str, state: str, cookie_state: str | None,
               quiz_ids: list[str]) -> Launch | DeepLinkRequest:
        if not id_token or not state:
            raise LtiError("The launch is missing id_token or state.")
        # The state cookie can be blocked when Moodle shows the tool in an
        # iframe, so it is checked when present; the single-use state and
        # nonce held on the server are the main replay protection.
        if cookie_state is not None and cookie_state != state:
            raise LtiError("This launch doesn't match the login that started it.")
        row = self.db.take_state(state)
        if row is None:
            raise LtiError("This launch has expired or was already used. Open the activity again from Moodle.")
        platform = self.db.get_platform(row["platform_id"])
        if platform is None or not platform["active"]:
            raise LtiError("This learning platform has been switched off.")

        claims = self._verify_id_token(id_token, platform)
        if claims.get("nonce") != row["nonce"]:
            raise LtiError("The launch nonce doesn't match.")
        if claims.get(CLAIM + "version") != "1.3.0":
            raise LtiError("Only LTI 1.3 launches are supported.")
        message_type = claims.get(CLAIM + "message_type")
        if message_type not in (MSG_RESOURCE, MSG_DEEP_LINK):
            raise LtiError("This kind of LTI message isn't supported yet.")
        deployment_id = claims.get(CLAIM + "deployment_id")
        if not deployment_id or not self.db.has_deployment(platform["id"], deployment_id):
            raise LtiError("This deployment of the tool isn't registered.")
        if message_type == MSG_DEEP_LINK:
            return self._deep_link_request(claims, platform, deployment_id)
        if not claims.get("sub"):
            raise LtiError("Anonymous launches aren't supported: the tool needs to know who to give the grade to.")

        quiz_id = self._pick_quiz(claims, quiz_ids)
        ags = claims.get(AGS_CLAIM) or {}
        scopes = ags.get("scope") or []
        context = claims.get(CLAIM + "context") or {}
        resource = claims.get(CLAIM + "resource_link") or {}

        launch = Launch(
            id=uuid.uuid4().hex,
            quiz_id=quiz_id,
            user_name=claims.get("name") or claims.get("given_name"),
            can_send_grade=bool(ags.get("lineitem")) and SCOPE_SCORE in scopes,
        )
        self.db.save_launch(
            id=launch.id, platform_id=platform["id"], deployment_id=deployment_id,
            user_sub=claims["sub"], user_name=launch.user_name,
            context_id=context.get("id"), context_title=context.get("title"),
            resource_link_id=resource.get("id"), quiz_id=quiz_id,
            lineitem_url=ags.get("lineitem"), ags_scopes=" ".join(scopes),
        )
        return launch

    @staticmethod
    def _deep_link_request(claims: dict, platform, deployment_id: str) -> DeepLinkRequest:
        settings = claims.get(DL_CLAIM + "deep_linking_settings") or {}
        return_url = settings.get("deep_link_return_url")
        if not return_url or not same_host(return_url, platform["issuer"]):
            raise LtiError("The content selection request has no valid return address.")
        if "ltiResourceLink" not in (settings.get("accept_types") or []):
            raise LtiError("Moodle isn't asking for an activity link here, so there's nothing to choose.")
        return DeepLinkRequest(platform["id"], deployment_id, return_url, settings.get("data"))

    def deep_link_response(self, request: DeepLinkRequest, item_id: str, title: str, graded: bool) -> str:
        """The signed JWT that tells Moodle which quiz the teacher picked."""
        platform = self.db.get_platform(request.platform_id)
        if platform is None or not platform["active"]:
            raise LtiError("This learning platform has been switched off.")
        content_item = {
            "type": "ltiResourceLink",
            "title": title,
            "url": self.launch_url,
            "custom": {"quiz": item_id},
        }
        if graded:
            # Scores are sent as right / total; Moodle scales them to this maximum.
            content_item["lineItem"] = {"scoreMaximum": 100, "label": title, "resourceId": item_id}
        now = int(time.time())
        claims = {
            "iss": platform["client_id"],
            "aud": platform["issuer"],
            "iat": now,
            "exp": now + 300,
            "nonce": secrets.token_urlsafe(16),
            CLAIM + "message_type": "LtiDeepLinkingResponse",
            CLAIM + "version": "1.3.0",
            CLAIM + "deployment_id": request.deployment_id,
            DL_CLAIM + "content_items": [content_item],
        }
        if request.data:
            claims[DL_CLAIM + "data"] = request.data
        return jwt.encode(claims, self.keys.private_key, algorithm="RS256", headers={"kid": self.keys.kid})

    def _verify_id_token(self, id_token: str, platform) -> dict:
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError:
            raise LtiError("The launch token is not a valid JWT.")
        if header.get("alg") != "RS256":
            raise LtiError("The launch token must be signed with RS256.")
        key = self._platform_key(platform["jwks_url"], header.get("kid"))
        try:
            claims = jwt.decode(
                id_token, key, algorithms=["RS256"],
                audience=platform["client_id"], issuer=platform["issuer"],
                leeway=CLOCK_LEEWAY, options={"require": ["exp", "iat", "iss", "aud", "nonce"]},
            )
        except jwt.PyJWTError as e:
            raise LtiError(f"The launch token failed its checks ({e}).")
        aud = claims["aud"]
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != platform["client_id"]:
            raise LtiError("The launch token's azp doesn't name this tool.")
        return claims

    def _platform_key(self, jwks_url: str, kid: str | None):
        for attempt in range(2):
            cached = self._jwks.get(jwks_url)
            if cached is None or cached[0] < time.time() - JWKS_CACHE_SECONDS or attempt == 1:
                try:
                    resp = self.http.get(jwks_url, timeout=10)
                    resp.raise_for_status()
                    keyset = jwt.PyJWKSet.from_dict(resp.json())
                except (httpx.HTTPError, ValueError, jwt.PyJWTError) as e:
                    raise LtiError(f"Couldn't fetch the platform's public keys ({e}).")
                self._jwks[jwks_url] = cached = (time.time(), keyset)
            for k in cached[1].keys:
                if kid is None or k.key_id == kid:
                    return k.key
        raise LtiError("The launch was signed with a key the platform doesn't publish.")

    @staticmethod
    def _pick_quiz(claims: dict, quiz_ids: list[str]) -> str:
        """Custom parameter quiz=<id>, then ?quiz=<id> on the target link, then the first quiz."""
        custom = claims.get(CLAIM + "custom") or {}
        wanted = custom.get("quiz")
        if not wanted:
            target = claims.get(CLAIM + "target_link_uri") or ""
            wanted = (parse_qs(urlsplit(target).query).get("quiz") or [None])[0]
        if wanted:
            if wanted not in quiz_ids:
                raise LtiError(f"There is no quiz called '{wanted}' on this tool.")
            return wanted
        if not quiz_ids:
            raise LtiError("No quizzes are installed on this tool.")
        return quiz_ids[0]

    # 3. Grades (AGS) ----------------------------------------------------
    def send_score(self, launch_row, score: int, max_score: int) -> None:
        platform = self.db.get_platform(launch_row["platform_id"])
        if platform is None or not platform["active"]:
            raise LtiError("This learning platform has been switched off.")
        token = self._access_token(platform, SCOPE_SCORE)

        parts = urlsplit(launch_row["lineitem_url"])
        scores_url = urlunsplit(parts._replace(path=parts.path.rstrip("/") + "/scores"))
        body = {
            "userId": launch_row["user_sub"],
            "scoreGiven": score,
            "scoreMaximum": max_score,
            "activityProgress": "Completed",
            "gradingProgress": "FullyGraded",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        }
        try:
            resp = self.http.post(scores_url, json=body, timeout=15, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.ims.lis.v1.score+json",
            })
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise LtiError(f"Moodle didn't accept the score ({e}).")

    def _access_token(self, platform, scope: str) -> str:
        cache_key = (platform["id"], scope)
        cached = self._tokens.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": platform["client_id"], "sub": platform["client_id"], "aud": platform["token_url"],
             "iat": now, "exp": now + 300, "jti": uuid.uuid4().hex},
            self.keys.private_key, algorithm="RS256", headers={"kid": self.keys.kid},
        )
        try:
            resp = self.http.post(platform["token_url"], timeout=15, data={
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": assertion,
                "scope": scope,
            })
            resp.raise_for_status()
            data = resp.json()
            token = data["access_token"]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise LtiError(f"Couldn't get an access token from Moodle ({e}).")
        lifetime = int(data.get("expires_in", 3600))
        self._tokens[cache_key] = (time.time() + max(lifetime - 60, 0), token)
        return token

    # 4. Dynamic registration --------------------------------------------
    def register(self, openid_configuration: str, registration_token: str | None) -> str:
        """Register with a platform. Returns the platform's issuer."""
        if not any(openid_configuration.startswith(i + "/") for i in self.settings.allowed_issuers):
            raise LtiError("This platform isn't on the tool's list of allowed platforms.")
        try:
            resp = self.http.get(openid_configuration, timeout=10)
            resp.raise_for_status()
            config = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LtiError(f"Couldn't read the platform's configuration ({e}).")

        issuer = (config.get("issuer") or "").rstrip("/")
        if issuer not in self.settings.allowed_issuers or not openid_configuration.startswith(issuer + "/"):
            raise LtiError("The platform's issuer doesn't match its configuration address.")
        endpoints = {k: config.get(k) for k in
                     ("registration_endpoint", "authorization_endpoint", "token_endpoint", "jwks_uri")}
        for name, url in endpoints.items():
            if not url or not same_host(url, issuer):
                raise LtiError(f"The platform's {name} is missing or on a different host.")

        tool_host = urlsplit(self.settings.base_url).netloc
        registration = {
            "application_type": "web",
            "response_types": ["id_token"],
            "grant_types": ["implicit", "client_credentials"],
            "initiate_login_uri": self.login_url,
            "redirect_uris": [self.launch_url],
            "client_name": self.settings.tool_name,
            "jwks_uri": self.settings.base_url + "/.well-known/jwks.json",
            "token_endpoint_auth_method": "private_key_jwt",
            "scope": f"{SCOPE_SCORE} {SCOPE_LINEITEM_RO}",
            TOOL_CONFIG: {
                "domain": tool_host,
                "target_link_uri": self.launch_url,
                "claims": ["iss", "sub", "name", "given_name", "family_name"],
                "messages": [
                    {"type": MSG_RESOURCE},
                    {"type": MSG_DEEP_LINK, "target_link_uri": self.launch_url, "label": "Choose a quiz"},
                ],
                "description": "Interactive electronics quizzes and simulators.",
            },
        }
        headers = {"Authorization": f"Bearer {registration_token}"} if registration_token else {}
        try:
            resp = self.http.post(endpoints["registration_endpoint"], json=registration, headers=headers, timeout=15)
            resp.raise_for_status()
            result = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LtiError(f"The platform refused the registration ({e}).")

        client_id = result.get("client_id")
        deployment_id = (result.get(TOOL_CONFIG) or {}).get("deployment_id")
        if not client_id or not deployment_id:
            raise LtiError("The platform's reply had no client_id or deployment_id.")
        platform_id = self.db.upsert_platform(
            issuer, client_id, endpoints["authorization_endpoint"],
            endpoints["token_endpoint"], endpoints["jwks_uri"])
        self.db.add_deployment(platform_id, deployment_id)
        return issuer
