"""System-2 via the same LLM gateway Responses API Codex uses. Never prints the key."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional


def _load_key() -> str:
    auth = json.loads(Path.home().joinpath(".codex/auth.json").read_text())
    key = auth.get("OPENAI_API_KEY") or auth.get("api_key")
    if not key:
        raise RuntimeError("No API key in ~/.codex/auth.json")
    return key


class System2Client:
    """Codex wire_api=responses on LLM gateway. DeepSeek-V4-Flash is ~0.8s when healthy."""

    def __init__(
        self,
        model: str = "DeepSeek-V4-Flash",
        base_url: str = "https://llm-gateway.example/v1",
        timeout: float = 6.0,
    ):
        self.model = model
        self.url = base_url.rstrip("/") + "/responses"
        self.timeout = timeout
        self._key = _load_key()
        self.n_calls = 0
        self.n_fail = 0
        self.infer_s = 0.0
        self.last_usage: dict = {}

    def correct(
        self,
        state: str,
        proposed: Dict[str, str],
        legal: Dict[str, List[str]],
        legal_tags: Optional[Dict[str, Dict[str, str]]] = None,
        draft_diag: str = "",
    ) -> Optional[Dict[str, str]]:
        legal = legal or {}
        prop_txt = " ".join(f"{u}={lab}" for u, lab in proposed.items())
        legal_short = " ".join(f"{u}:{'/'.join(labs[:8])}" for u, labs in legal.items())
        user = (
            "Correct this StarCraft army assignment. Return one JSON object "
            "mapping each Uid to one LEGAL label.\n"
            f"{draft_diag}\nPROPOSED {prop_txt}\nLEGAL {legal_short}"
        )
        n_units = max(1, len(legal))
        body = {
            "model": self.model,
            "instructions": "Output one JSON object only. No markdown. No extra keys.",
            "input": user,
            "temperature": 0,
            "max_output_tokens": min(512, 64 + 32 * n_units),
            "reasoning": {"effort": "none"},
        }
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-4",
                    "--connect-timeout",
                    "3",
                    "--max-time",
                    str(int(self.timeout)),
                    "-H",
                    "Authorization: Bearer " + self._key,
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(body),
                    self.url,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout + 2,
            )
        except (subprocess.TimeoutExpired, OSError):
            self.n_fail += 1
            self.infer_s += time.perf_counter() - t0
            print("    s2_http fail timeout", flush=True)
            return None
        self.infer_s += time.perf_counter() - t0
        if proc.returncode != 0 or not proc.stdout.strip():
            self.n_fail += 1
            err = (proc.stderr or proc.stdout or "")[:160].replace("\n", " ")
            print(f"    s2_http fail code={proc.returncode} {err}", flush=True)
            return None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.n_fail += 1
            return None
        if payload.get("error"):
            self.n_fail += 1
            print("    s2_http err", str(payload["error"])[:160], flush=True)
            return None
        self.n_calls += 1
        types = [i.get("type") for i in (payload.get("output") or []) if isinstance(i, dict)]
        if "reasoning" in types:
            print("    s2 warning: gateway still returned reasoning", flush=True)
        text = _extract_text(payload)
        parsed = _parse_json_map(text, legal)
        if os.environ.get("S2_VERBOSE"):
            print(f"    s2 {(time.perf_counter()-t0)*1000:.0f}ms parsed={parsed}", flush=True)
        return parsed


    def fill_json(self, instructions: str, user: str, timeout: Optional[float] = None) -> Optional[dict]:
        """One JSON object. reasoning off. Never logs the key."""
        body = {
            "model": self.model,
            "instructions": instructions,
            "input": user,
            "temperature": 0,
            "max_output_tokens": 400,
            "reasoning": {"effort": "none"},
        }
        t0 = time.perf_counter()
        to = timeout if timeout is not None else self.timeout
        try:
            proc = subprocess.run(
                [
                    "curl", "-sS", "-4",
                    "--connect-timeout", "3",
                    "--max-time", str(int(to)),
                    "-H", "Authorization: Bearer " + self._key,
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(body),
                    self.url,
                ],
                capture_output=True, text=True, timeout=to + 2,
            )
        except (subprocess.TimeoutExpired, OSError):
            self.n_fail += 1
            self.infer_s += time.perf_counter() - t0
            print("    api_plan fail timeout", flush=True)
            return None
        self.infer_s += time.perf_counter() - t0
        if proc.returncode != 0 or not proc.stdout.strip():
            self.n_fail += 1
            print("    api_plan fail curl", flush=True)
            return None
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.n_fail += 1
            return None
        if payload.get("error"):
            self.n_fail += 1
            print("    api_plan err", str(payload["error"])[:160], flush=True)
            return None
        self.n_calls += 1
        text_out = _extract_text(payload)
        m = re.search(r"\{.*\}", text_out or "", re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    def system_one(self, state, questions):
        """Answer independent job questions. Same return shape as JevClient.system_one."""
        allowed = {}
        for name, q in (questions or {}).items():
            crit = (q or {}).get("criteria") or {}
            allowed[name] = list(crit.keys()) if isinstance(crit, dict) else []
        instructions = (
            "You command StarCraft unit-level micro. Code executes movement. "
            "Output one JSON object mapping each question name to exactly one legal option string. "
            "No markdown, no extra keys. "
            "If we are outnumbered vs melee and have no allied tanks: pick peel unless guns are ready "
            "AND this ranged line is not in blades. "
            "If allied melee is still tanking and this ranged line is not in blades: pick fight, not peel. "
            "If they have extra heavy tanks, pick heaviest not weakest_in_range."
        )
        user = json.dumps(
            {"state": state, "questions": questions, "legal": allowed},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        obj = self.fill_json(instructions, user)
        answers = {}
        if isinstance(obj, dict):
            for name, opts in allowed.items():
                val = obj.get(name)
                if isinstance(val, dict):
                    val = val.get("choice") or val.get("pick") or val.get("value")
                if val in opts:
                    answers[name] = {"choice": val}
        if not answers:
            return None
        return {"answers": answers}


def _extract_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("text"):
                    return str(c["text"])
    return ""


def _parse_json_map(text: str, legal: Dict[str, List[str]]) -> Optional[Dict[str, str]]:
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            cleaned = m.group(0).replace("'", '"')
            cleaned = re.sub(r",\s*}", "}", cleaned)
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
    out = {}
    for k, v in obj.items():
        uk = str(k).strip().upper()
        if uk == "FOCUS":
            continue
        if not uk.startswith("U"):
            uk = "U" + uk
        lab = str(v).strip().upper()
        if uk in legal and lab in legal[uk]:
            out[uk] = lab
    return out or None
