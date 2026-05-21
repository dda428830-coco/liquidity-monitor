from __future__ import annotations

import json
from urllib import parse, request


def get_text(url: str, params: dict[str, str] | None = None, timeout: int = 30) -> str:
    full_url = _url_with_params(url, params)
    req = request.Request(full_url, headers={"User-Agent": "liquidity-monitor/1.0"})
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def get_json(url: str, params: dict[str, str] | None = None, timeout: int = 30) -> dict:
    return json.loads(get_text(url, params=params, timeout=timeout))


def post_json(url: str, payload: dict, timeout: int = 30) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "liquidity-monitor/1.0",
        },
    )
    with request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def _url_with_params(url: str, params: dict[str, str] | None) -> str:
    if not params:
        return url
    return f"{url}?{parse.urlencode(params)}"
