from __future__ import annotations

from typing import Optional

import requests


def send_ntfy(
    server: str,
    topic: str,
    title: str,
    message: str,
    click_url: Optional[str] = None,
) -> bool:
    if not topic:
        return False

    url = f"{server.rstrip('/')}/{topic}"
    headers = {"Title": title}
    if click_url:
        headers["Click"] = click_url

    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
    resp.raise_for_status()
    return True
