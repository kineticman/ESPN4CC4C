#!/usr/bin/env python3
# Common ingest helpers for ESPN Clean v2
import hashlib
import time
from typing import Any, Dict, List

import requests


class RetryHTTP:
    def __init__(self, timeout=15, max_tries=5, backoff=0.5):
        self.timeout = timeout
        self.max_tries = max_tries
        self.backoff = backoff

    def get_json(
        self, url: str, headers: Dict[str, str] = None, params: Dict[str, str] = None
    ) -> Any:
        last = None
        for i in range(1, self.max_tries + 1):
            try:
                r = requests.get(
                    url,
                    headers=headers or {},
                    params=params or {},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                if "json" not in (r.headers.get("content-type", "")):
                    raise RuntimeError(
                        f"unexpected content-type {r.headers.get('content-type')}"
                    )
                return r.json()
            except Exception as e:
                last = e
                time.sleep(self.backoff * (2 ** (i - 1)))
        raise last


def stable_event_id(source: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source}:{external_id}".encode("utf-8")).hexdigest()[:32]
    return f"{source}:{external_id}:{digest}"


def ensure_list(x) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]
