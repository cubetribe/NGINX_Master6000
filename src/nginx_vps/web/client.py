"""Local CLI helper for approving browser logins with an SSH key."""

from pathlib import Path
import json
from urllib import error, parse, request

from nginx_vps.web.auth import sign_login_challenge


def complete_web_login(
    *,
    base_url: str,
    username: str,
    challenge_id: str,
    key_path: Path,
) -> dict[str, object]:
    """Fetch, sign, and approve a browser login challenge."""
    normalized_base_url = base_url.rstrip("/")
    challenge_response = _json_request(
        f"{normalized_base_url}/auth/challenge-info?{parse.urlencode({'challenge_id': challenge_id, 'username': username})}"
    )
    message = challenge_response.get("message")
    if not isinstance(message, str) or not message:
        raise RuntimeError("Server did not return a signable challenge payload.")

    signature = sign_login_challenge(key_path, message)
    approval_response = _json_request(
        f"{normalized_base_url}/auth/complete",
        method="POST",
        payload={
            "challenge_id": challenge_id,
            "username": username,
            "signature": signature,
        },
    )
    return approval_response


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data: bytes | None = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "nginx-vps-web-login/0.1.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=15) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(response_body)
        except json.JSONDecodeError as decode_error:
            raise RuntimeError(f"Web login request failed with HTTP {exc.code}.") from decode_error
        detail = error_payload.get("error")
        if isinstance(detail, str) and detail:
            raise RuntimeError(detail) from exc
        raise RuntimeError(f"Web login request failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach the web UI at {url}.") from exc

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Server response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Server response was not a JSON object.")
    return payload
