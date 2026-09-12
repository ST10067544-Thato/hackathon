"""Thin HTTP client for the Zernio API (https://docs.zernio.com).

Only the endpoints the Creator Companion tools use are exposed. Every request goes
through ``_request`` so auth, error mapping, and the "not configured" case behave the
same way for each tool; agents receive a JSON string they can reason about instead of
a stack trace.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

import httpx

from creator_companion.config import ZERNIO_DEFAULT_BASE_URL

MAX_RESULT_CHARS = 12_000


class ZernioError(Exception):
    """A non-2xx response, a transport failure, or a missing API key."""

    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(f"{code} ({status}): {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def as_tool_result(self) -> str:
        payload: dict[str, Any] = {
            "error": True,
            "status": self.status,
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        payload["hint"] = _hint_for(self.status, self.code)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _hint_for(status: int, code: str) -> str:
    if code == "not_configured":
        return "Set ZERNIO_API_KEY in the root .env and restart the service."
    if status == 401:
        return "The API key was rejected, or the connected account's token expired and needs reconnecting."
    if status == 403:
        return "The key lacks the add-on or permission this endpoint needs (inbox/analytics add-on, or platform permission)."
    if status == 404:
        return "The post, account, or comment was not found; confirm the id and the account it belongs to."
    if status == 409:
        return "Duplicate write within the idempotency window; the original result should already exist."
    if status == 429:
        return "Rate limited; wait before retrying and reduce the number of calls in this run."
    if status == 424:
        return "Zernio could not sync this post's metrics from any platform; report it as unavailable."
    return "Report the failure to the creator instead of retrying blindly."


class ZernioClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = ZERNIO_DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.configured = bool(api_key)
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=_drop_none(params))

    def post(self, path: str, body: Mapping[str, Any] | None = None, *, idempotent: bool = False) -> Any:
        headers = {"Idempotency-Key": str(uuid.uuid4())} if idempotent else None
        return self._request("POST", path, json_body=_drop_none(body), headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        if not self.configured:
            raise ZernioError(0, "not_configured", "ZERNIO_API_KEY is not set; live social data is unavailable.")
        try:
            response = self._client.request(method, path, params=params, json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            raise ZernioError(0, "network_error", f"{type(exc).__name__}: {exc}") from exc

        body = _parse_body(response)
        if response.status_code == 202:
            return {"status": "sync_pending", "http_status": 202, "body": body}
        if response.is_success:
            return body

        code, message, details = _error_fields(body, response)
        raise ZernioError(response.status_code, code, message, details)


def _parse_body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:2000]}


def _error_fields(body: Any, response: httpx.Response) -> tuple[str, str, Any]:
    if isinstance(body, dict):
        code = str(body.get("code") or body.get("type") or f"http_{response.status_code}")
        message = str(body.get("message") or body.get("error") or response.reason_phrase or "request failed")
        details = body.get("details")
        return code, message, details
    return f"http_{response.status_code}", response.reason_phrase or "request failed", body


def _drop_none(values: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not values:
        return None
    cleaned = {k: v for k, v in values.items() if v is not None and v != ""}
    return cleaned or None


def tool_result(data: Any) -> str:
    """Serialize a tool result for the model, capping very large payloads."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return json.dumps(
        {
            "truncated": True,
            "note": f"Result exceeded {MAX_RESULT_CHARS} characters; narrow the query (smaller limit, one account, a date range).",
            "preview": text[:MAX_RESULT_CHARS],
        },
        ensure_ascii=False,
    )
