from __future__ import annotations

import os

from liquidity_monitor.common.http import post_json


class DiscordPusher:
    def __init__(self, webhook_url: str | None = None, timeout: int = 10) -> None:
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.timeout = timeout

    def send(self, content: str) -> None:
        if not self.webhook_url:
            raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")
        chunks = _split_discord_content(content)
        for chunk in chunks:
            post_json(
                self.webhook_url,
                {"content": chunk, "allowed_mentions": {"parse": []}},
                timeout=self.timeout,
            )


def _split_discord_content(content: str, limit: int = 1900) -> list[str]:
    if len(content) <= limit:
        return [content]
    chunks = []
    current = []
    current_len = 0
    for line in content.splitlines():
        extra = len(line) + 1
        if current and current_len + extra > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += extra
    if current:
        chunks.append("\n".join(current))
    return chunks
