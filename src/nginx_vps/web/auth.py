"""SSH-key-only browser authentication and session management."""

from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time

from nginx_vps.config import USERNAME_PATTERN, WebSettings

SSH_SIGNATURE_NAMESPACE = "nginx-master6000-login"
SESSION_COOKIE_NAME = "nginx_master6000_session"
PENDING_COOKIE_NAME = "nginx_master6000_pending"
MAX_SIGNATURE_LENGTH = 32_768


class AuthError(RuntimeError):
    """Typed authentication failure with HTTP status metadata."""

    def __init__(self, message: str, *, status_code: int = 400, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(slots=True)
class LoginChallenge:
    """Pending SSH-signature login challenge."""

    challenge_id: str
    username: str
    client_ip: str
    browser_token: str
    message: str
    created_at: float
    expires_at: float
    approved_at: float | None = None
    consumed_at: float | None = None


@dataclass(slots=True)
class AuthSession:
    """Issued browser session for an authenticated user."""

    session_id: str
    username: str
    client_ip: str
    created_at: float
    expires_at: float


class AuthService:
    """Thread-safe in-memory auth state for the web UI."""

    def __init__(self, settings: WebSettings, *, time_func: Callable[[], float] | None = None) -> None:
        self.settings = settings
        self._time = time_func or time.time
        self._lock = threading.Lock()
        self._challenges: dict[str, LoginChallenge] = {}
        self._sessions: dict[str, AuthSession] = {}
        self._challenge_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._verify_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._failed_verifications: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lockouts: dict[tuple[str, str], float] = {}

    def create_challenge(self, username: str, client_ip: str) -> LoginChallenge:
        """Create a browser login challenge for a configured user."""
        normalized_username = username.strip()
        self._validate_username(normalized_username)
        now = self._time()

        with self._lock:
            self._prune_expired_locked(now)
            key = (client_ip, normalized_username)
            self._ensure_not_locked_locked(key, now)
            self._record_window_event_locked(
                store=self._challenge_events,
                key=key,
                now=now,
                limit=self.settings.challenge_rate_limit,
                window_seconds=self.settings.challenge_rate_window_seconds,
                message="Too many login challenges requested. Wait before trying again.",
            )
            public_keys = self.settings.public_keys_for(normalized_username)
            if not public_keys:
                raise AuthError("Login challenge rejected.", status_code=403)

            challenge_id = secrets.token_urlsafe(16)
            expires_at = now + self.settings.challenge_ttl_seconds
            challenge = LoginChallenge(
                challenge_id=challenge_id,
                username=normalized_username,
                client_ip=client_ip,
                browser_token=secrets.token_urlsafe(16),
                message=build_login_message(
                    base_url=self.settings.base_url,
                    challenge_id=challenge_id,
                    username=normalized_username,
                    client_ip=client_ip,
                    expires_at=expires_at,
                ),
                created_at=now,
                expires_at=expires_at,
            )
            self._challenges[challenge_id] = challenge
            return challenge

    def get_cli_challenge(self, challenge_id: str, username: str, client_ip: str) -> LoginChallenge:
        """Return an active challenge for the local CLI signer."""
        normalized_username = username.strip()
        now = self._time()
        with self._lock:
            self._prune_expired_locked(now)
            return self._require_active_challenge_locked(challenge_id, normalized_username, client_ip)

    def approve_challenge(
        self,
        *,
        challenge_id: str,
        username: str,
        client_ip: str,
        signature: str,
    ) -> LoginChallenge:
        """Verify a signed OpenSSH challenge and mark the browser login as approved."""
        if len(signature) > MAX_SIGNATURE_LENGTH:
            raise AuthError("Signature payload is too large.", status_code=400)

        normalized_username = username.strip()
        now = self._time()

        with self._lock:
            self._prune_expired_locked(now)
            key = (client_ip, normalized_username)
            self._ensure_not_locked_locked(key, now)
            self._record_window_event_locked(
                store=self._verify_events,
                key=key,
                now=now,
                limit=self.settings.verify_rate_limit,
                window_seconds=self.settings.verify_rate_window_seconds,
                message="Too many signature attempts. Wait before trying again.",
            )
            challenge = self._require_active_challenge_locked(challenge_id, normalized_username, client_ip)
            if challenge.approved_at is not None:
                return challenge

            public_keys = self.settings.public_keys_for(normalized_username)
            verified = verify_login_signature(
                username=normalized_username,
                public_keys=public_keys,
                message=challenge.message,
                signature=signature,
            )
            if not verified:
                self._record_failed_verification_locked(key, now)
                raise AuthError("Signature verification failed.", status_code=401)

            challenge.approved_at = now
            self._failed_verifications.pop(key, None)
            return challenge

    def challenge_from_pending_cookie(self, cookie_value: str | None, client_ip: str) -> LoginChallenge | None:
        """Load a pending browser challenge from a signed cookie."""
        if not cookie_value:
            return None
        payload = _unsign_payload(self.settings.session_secret, cookie_value)
        if payload is None:
            return None

        challenge_id = payload.get("cid")
        browser_token = payload.get("bt")
        if not isinstance(challenge_id, str) or not isinstance(browser_token, str):
            return None

        now = self._time()
        with self._lock:
            self._prune_expired_locked(now)
            challenge = self._challenges.get(challenge_id)
            if challenge is None:
                return None
            if challenge.browser_token != browser_token or challenge.client_ip != client_ip:
                return None
            if challenge.consumed_at is not None:
                return None
            return challenge

    def pending_cookie_value(self, challenge: LoginChallenge) -> str:
        """Encode a signed pending-login cookie."""
        return _sign_payload(
            self.settings.session_secret,
            {
                "cid": challenge.challenge_id,
                "bt": challenge.browser_token,
            },
        )

    def issue_session_from_pending_cookie(
        self, cookie_value: str | None, client_ip: str
    ) -> AuthSession | None:
        """Create an authenticated browser session when a pending challenge has been approved."""
        challenge = self.challenge_from_pending_cookie(cookie_value, client_ip)
        if challenge is None or challenge.approved_at is None:
            return None

        now = self._time()
        with self._lock:
            self._prune_expired_locked(now)
            live_challenge = self._challenges.get(challenge.challenge_id)
            if live_challenge is None or live_challenge.consumed_at is not None:
                return None

            session = AuthSession(
                session_id=secrets.token_urlsafe(24),
                username=live_challenge.username,
                client_ip=client_ip,
                created_at=now,
                expires_at=now + self.settings.session_ttl_seconds,
            )
            self._sessions[session.session_id] = session
            live_challenge.consumed_at = now
            return session

    def session_cookie_value(self, session: AuthSession) -> str:
        """Encode a signed browser session cookie."""
        return _sign_payload(
            self.settings.session_secret,
            {
                "sid": session.session_id,
                "iat": int(session.created_at),
            },
        )

    def load_session(self, cookie_value: str | None, client_ip: str) -> AuthSession | None:
        """Return a valid browser session and extend its expiry."""
        if not cookie_value:
            return None
        payload = _unsign_payload(self.settings.session_secret, cookie_value)
        if payload is None:
            return None
        session_id = payload.get("sid")
        if not isinstance(session_id, str):
            return None

        now = self._time()
        with self._lock:
            self._prune_expired_locked(now)
            session = self._sessions.get(session_id)
            if session is None or session.client_ip != client_ip:
                return None
            session.expires_at = now + self.settings.session_ttl_seconds
            return session

    def clear_session(self, cookie_value: str | None) -> None:
        """Invalidate a browser session if the cookie is valid."""
        if not cookie_value:
            return
        payload = _unsign_payload(self.settings.session_secret, cookie_value)
        if payload is None:
            return
        session_id = payload.get("sid")
        if not isinstance(session_id, str):
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def _validate_username(self, username: str) -> None:
        if not USERNAME_PATTERN.fullmatch(username):
            raise AuthError("Usernames may contain only letters, numbers, dot, underscore, dash, and @.")

    def _require_active_challenge_locked(
        self, challenge_id: str, username: str, client_ip: str
    ) -> LoginChallenge:
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            raise AuthError("Login challenge not found.", status_code=404)
        if challenge.username != username or challenge.client_ip != client_ip:
            raise AuthError("Login challenge not found.", status_code=404)
        if challenge.consumed_at is not None:
            raise AuthError("Login challenge has already been used.", status_code=410)
        now = self._time()
        if challenge.expires_at <= now:
            self._challenges.pop(challenge_id, None)
            raise AuthError("Login challenge expired. Start a new browser login.", status_code=410)
        return challenge

    def _record_window_event_locked(
        self,
        *,
        store: dict[tuple[str, str], deque[float]],
        key: tuple[str, str],
        now: float,
        limit: int,
        window_seconds: int,
        message: str,
    ) -> None:
        history = store[key]
        _trim_window(history, now, window_seconds)
        if len(history) >= limit:
            retry_after = max(1, int(window_seconds - (now - history[0])))
            raise AuthError(message, status_code=429, retry_after=retry_after)
        history.append(now)

    def _record_failed_verification_locked(self, key: tuple[str, str], now: float) -> None:
        failures = self._failed_verifications[key]
        _trim_window(failures, now, self.settings.verify_rate_window_seconds)
        failures.append(now)
        if len(failures) >= self.settings.lockout_threshold:
            self._lockouts[key] = now + self.settings.lockout_seconds

    def _ensure_not_locked_locked(self, key: tuple[str, str], now: float) -> None:
        locked_until = self._lockouts.get(key)
        if locked_until is None:
            return
        if locked_until <= now:
            self._lockouts.pop(key, None)
            return
        retry_after = max(1, int(locked_until - now))
        raise AuthError(
            "This browser login is temporarily locked after repeated failed signature attempts.",
            status_code=429,
            retry_after=retry_after,
        )

    def _prune_expired_locked(self, now: float) -> None:
        expired_challenges = [
            challenge_id
            for challenge_id, challenge in self._challenges.items()
            if challenge.expires_at <= now or challenge.consumed_at is not None
        ]
        for challenge_id in expired_challenges:
            self._challenges.pop(challenge_id, None)

        expired_sessions = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired_sessions:
            self._sessions.pop(session_id, None)

        _prune_mapping(self._challenge_events, now, self.settings.challenge_rate_window_seconds)
        _prune_mapping(self._verify_events, now, self.settings.verify_rate_window_seconds)
        _prune_mapping(self._failed_verifications, now, self.settings.verify_rate_window_seconds)

        expired_lockouts = [key for key, locked_until in self._lockouts.items() if locked_until <= now]
        for key in expired_lockouts:
            self._lockouts.pop(key, None)


def build_login_message(
    *,
    base_url: str,
    challenge_id: str,
    username: str,
    client_ip: str,
    expires_at: float,
) -> str:
    """Build the canonical message signed by the local SSH private key."""
    expiry = datetime.fromtimestamp(expires_at, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "\n".join(
        [
            "NGINX Master6000 SSH Login",
            f"origin={base_url.rstrip('/')}",
            f"challenge_id={challenge_id}",
            f"username={username}",
            f"client_ip={client_ip}",
            f"expires_at={expiry}",
        ]
    )


def sign_login_challenge(key_path: Path, message: str) -> str:
    """Sign a login challenge with a local OpenSSH private key."""
    expanded_key_path = key_path.expanduser()
    if not expanded_key_path.is_file():
        raise RuntimeError(f"SSH key path not found: {expanded_key_path}")

    with tempfile.TemporaryDirectory(prefix="nginx-master6000-sign-") as temp_dir:
        message_path = Path(temp_dir) / "challenge.txt"
        message_path.write_text(message, encoding="utf-8")

        process = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-n",
                SSH_SIGNATURE_NAMESPACE,
                "-f",
                str(expanded_key_path),
                str(message_path),
            ],
            check=False,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeError("OpenSSH signing failed. Confirm your local key path and key passphrase.")

        signature_path = Path(f"{message_path}.sig")
        return signature_path.read_text(encoding="utf-8")


def verify_login_signature(
    *,
    username: str,
    public_keys: Sequence[str],
    message: str,
    signature: str,
) -> bool:
    """Verify an OpenSSH signature against any configured public key for a user."""
    if not public_keys:
        return False

    with tempfile.TemporaryDirectory(prefix="nginx-master6000-verify-") as temp_dir:
        temp_root = Path(temp_dir)
        signature_path = temp_root / "challenge.sig"
        signature_path.write_text(signature, encoding="utf-8")

        allowed_signers_path = temp_root / "allowed_signers"
        allowed_signers_path.write_text(
            "".join(
                f'{username} namespaces="{SSH_SIGNATURE_NAMESPACE}" {public_key}\n'
                for public_key in public_keys
            ),
            encoding="utf-8",
        )

        process = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed_signers_path),
                "-I",
                username,
                "-n",
                SSH_SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input=message,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
            text=True,
        )
        return process.returncode == 0


def _prune_mapping(mapping: dict[tuple[str, str], deque[float]], now: float, window_seconds: int) -> None:
    for key in list(mapping):
        history = mapping[key]
        _trim_window(history, now, window_seconds)
        if not history:
            mapping.pop(key, None)


def _trim_window(history: deque[float], now: float, window_seconds: int) -> None:
    threshold = now - window_seconds
    while history and history[0] <= threshold:
        history.popleft()


def _sign_payload(secret: str, payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return f"{_urlsafe_b64encode(raw)}.{_urlsafe_b64encode(digest)}"


def _unsign_payload(secret: str, token: str) -> dict[str, object] | None:
    try:
        raw_payload, raw_digest = token.split(".", 1)
    except ValueError:
        return None

    payload_bytes = _urlsafe_b64decode(raw_payload)
    digest_bytes = _urlsafe_b64decode(raw_digest)
    expected_digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_digest, digest_bytes):
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
