"""SQLite storage: registered platforms, login states, launches and attempts."""
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS platforms (
    id          INTEGER PRIMARY KEY,
    issuer      TEXT NOT NULL,
    client_id   TEXT NOT NULL,
    auth_url    TEXT NOT NULL,
    token_url   TEXT NOT NULL,
    jwks_url    TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,   -- set to 0 to switch a college off
    created     INTEGER NOT NULL,
    UNIQUE (issuer, client_id)
);
CREATE TABLE IF NOT EXISTS deployments (
    platform_id   INTEGER NOT NULL REFERENCES platforms(id),
    deployment_id TEXT NOT NULL,
    PRIMARY KEY (platform_id, deployment_id)
);
CREATE TABLE IF NOT EXISTS login_states (
    state       TEXT PRIMARY KEY,
    nonce       TEXT NOT NULL,
    platform_id INTEGER NOT NULL REFERENCES platforms(id),
    created     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS launches (
    id               TEXT PRIMARY KEY,
    platform_id      INTEGER NOT NULL REFERENCES platforms(id),
    deployment_id    TEXT NOT NULL,
    user_sub         TEXT NOT NULL,
    user_name        TEXT,
    context_id       TEXT,
    context_title    TEXT,
    resource_link_id TEXT,
    quiz_id          TEXT NOT NULL,
    lineitem_url     TEXT,
    ags_scopes       TEXT,
    created          INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id         INTEGER PRIMARY KEY,
    launch_id  TEXT NOT NULL REFERENCES launches(id),
    score      INTEGER NOT NULL,
    max_score  INTEGER NOT NULL,
    sent       INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    created    INTEGER NOT NULL
);
"""

STATE_LIFETIME = 600  # seconds a login state stays valid


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _one(self, sql, args=()):
        with self.connect() as conn:
            return conn.execute(sql, args).fetchone()

    # platforms -----------------------------------------------------------
    def find_platforms(self, issuer: str, client_id: str | None):
        with self.connect() as conn:
            if client_id:
                return conn.execute("SELECT * FROM platforms WHERE issuer = ? AND client_id = ?",
                                    (issuer, client_id)).fetchall()
            return conn.execute("SELECT * FROM platforms WHERE issuer = ?", (issuer,)).fetchall()

    def get_platform(self, platform_id: int):
        return self._one("SELECT * FROM platforms WHERE id = ?", (platform_id,))

    def upsert_platform(self, issuer, client_id, auth_url, token_url, jwks_url) -> int:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO platforms (issuer, client_id, auth_url, token_url, jwks_url, created)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (issuer, client_id) DO UPDATE SET
                     auth_url = excluded.auth_url, token_url = excluded.token_url,
                     jwks_url = excluded.jwks_url""",
                (issuer, client_id, auth_url, token_url, jwks_url, int(time.time())))
            return conn.execute("SELECT id FROM platforms WHERE issuer = ? AND client_id = ?",
                                (issuer, client_id)).fetchone()["id"]

    def add_deployment(self, platform_id: int, deployment_id: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO deployments VALUES (?, ?)", (platform_id, deployment_id))

    def has_deployment(self, platform_id: int, deployment_id: str) -> bool:
        return self._one("SELECT 1 FROM deployments WHERE platform_id = ? AND deployment_id = ?",
                         (platform_id, deployment_id)) is not None

    # login states (single use) --------------------------------------------
    def save_state(self, state: str, nonce: str, platform_id: int) -> None:
        now = int(time.time())
        with self.connect() as conn:
            conn.execute("DELETE FROM login_states WHERE created < ?", (now - STATE_LIFETIME,))
            conn.execute("INSERT INTO login_states VALUES (?, ?, ?, ?)", (state, nonce, platform_id, now))

    def take_state(self, state: str):
        """Return the state row and delete it, so it can't be used twice."""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM login_states WHERE state = ?", (state,)).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM login_states WHERE state = ?", (state,))
            if row["created"] < time.time() - STATE_LIFETIME:
                return None
            return row

    # launches and attempts ------------------------------------------------
    def save_launch(self, **launch) -> None:
        launch["created"] = int(time.time())
        cols = ", ".join(launch)
        marks = ", ".join("?" for _ in launch)
        with self.connect() as conn:
            conn.execute(f"INSERT INTO launches ({cols}) VALUES ({marks})", tuple(launch.values()))

    def get_launch(self, launch_id: str):
        return self._one("SELECT * FROM launches WHERE id = ?", (launch_id,))

    def save_attempt(self, launch_id: str, score: int, max_score: int, sent: bool, error: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO attempts (launch_id, score, max_score, sent, error, created) VALUES (?, ?, ?, ?, ?, ?)",
                (launch_id, score, max_score, int(sent), error, int(time.time())))
