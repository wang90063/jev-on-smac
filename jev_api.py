"""TypeSafe / Jev System One client. Uses TYPESAFE_API_KEY only. Never logs the key."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"


def load_typesafe_key() -> str:
    key = (os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_KEY") or "").strip()
    if key:
        return key
    for path in (
        Path(__file__).resolve().parent / ".typesafe_key",
        Path.home() / ".typesafe" / "api_key",
        Path.home() / ".config" / "typesafe" / "api_key",
    ):
        if path.is_file():
            val = path.read_text().strip()
            if val:
                return val
    raise RuntimeError(
        "No TypeSafe key. Export TYPESAFE_API_KEY from https://console.typesafe.ai/keys "
        "(this is not the LLM gateway key)."
    )


class JevClient:
    def __init__(self, model: str = MODEL, timeout: float = 15.0):
        self.model = model
        self.timeout = timeout
        self._key = load_typesafe_key()
        self.n_calls = 0
        self.n_fail = 0
        self.infer_s = 0.0
        self.last_usage: Dict[str, int] = {}

    def system_one(self, state: Any, questions: Dict[str, Any]) -> Optional[dict]:
        body = {"state": state, "model": self.model, "questions": questions}
        payload = json.dumps(body).encode("utf-8")
        t0 = time.perf_counter()
        last_err = None
        for attempt in range(5):
            req = urllib.request.Request(
                ENDPOINT,
                data=payload,
                method="POST",
                headers={
                    "Authorization": "Bearer " + self._key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                self.infer_s += time.perf_counter() - t0
                data = json.loads(raw)
            except urllib.error.HTTPError as exc:
                last_err = exc
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")[:240]
                except Exception:
                    err_body = ""
                if exc.code in (429, 529) and attempt < 4:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    wait = float(retry_after) if retry_after else min(8.0, 0.4 * (2 ** attempt))
                    time.sleep(wait)
                    continue
                self.n_fail += 1
                self.infer_s += time.perf_counter() - t0
                print(f"    jev_http {exc.code} {err_body}", flush=True)
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError, BrokenPipeError, OSError) as exc:
                last_err = exc
                if attempt < 4:
                    time.sleep(min(8.0, 0.5 * (2 ** attempt)))
                    continue
                self.n_fail += 1
                self.infer_s += time.perf_counter() - t0
                print(f"    jev_http fail {type(exc).__name__}", flush=True)
                return None
            if not isinstance(data, dict) or data.get("error"):
                self.n_fail += 1
                print("    jev_http err", str(data.get("error") if isinstance(data, dict) else last_err)[:160], flush=True)
                return None
            self.n_calls += 1
            usage = data.get("usage") or {}
            if isinstance(usage, dict):
                self.last_usage = {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                }
            return data
        self.n_fail += 1
        self.infer_s += time.perf_counter() - t0
        return None
