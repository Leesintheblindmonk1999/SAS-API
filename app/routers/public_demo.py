"""
app/routers/public_demo.py - SAS Public Demo Endpoint
=====================================================

GET  /public/demo/audit - onboarding/help for browsers and accidental GETs.
POST /public/demo/audit - no API key required.

Uses run_diff(text_a, text_b), the same forensic comparison engine used by /v1/diff.

Source = text_a, reference / ground truth.
Response = text_b, suspicious text to audit.

Security:
- No API key in frontend
- Full text is never stored
- Only input lengths are logged
- IP is hashed before logging
- Simple in-memory rate limit by IP hash
- No stack traces in API responses
- Max 2000 chars per field by default

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger("sas.public_demo")

router = APIRouter()

# ==============================================================================
# SAFE CONFIG FALLBACKS
# ==============================================================================

PUBLIC_DEMO_ENABLED: bool = bool(getattr(settings, "public_demo_enabled", True))
PUBLIC_DEMO_MAX_CHARS: int = int(getattr(settings, "public_demo_max_chars", 2000))
PUBLIC_DEMO_LIMIT_PER_DAY: int = int(getattr(settings, "public_demo_limit_per_day", 25))

# In-memory rate limit:
# { ip_hash: {"count": int, "date": "YYYY-MM-DD"} }
_RATE: dict[str, dict[str, Any]] = {}


# ==============================================================================
# HELPERS
# ==============================================================================


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:12]


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("true-client-ip")
        or request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def _check_rate(ip_hash: str) -> None:
    today = _utc_day()
    entry = _RATE.get(ip_hash)

    if entry and entry.get("date") == today:
        if int(entry.get("count", 0)) >= PUBLIC_DEMO_LIMIT_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Demo rate limit exceeded",
                    "message": (
                        f"Demo limit reached ({PUBLIC_DEMO_LIMIT_PER_DAY} requests/day per IP). "
                        "Request a Free API key to continue."
                    ),
                    "free_key": {
                        "cli": 'sas request-key --email you@example.com --name "Your Name"',
                        "endpoint": "POST /public/request-key",
                        "url": "https://sas-api.onrender.com/public/request-key",
                    },
                },
            )

        entry["count"] = int(entry.get("count", 0)) + 1
        return

    _RATE[ip_hash] = {"count": 1, "date": today}


def _to_dict(value: Any) -> dict[str, Any]:
    """
    Normalize run_diff output to a plain dict.

    This protects the public demo if the internal engine returns a Pydantic model
    or another object instead of a plain dictionary.
    """
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}

    if hasattr(value, "dict"):
        dumped = value.dict()
        return dumped if isinstance(dumped, dict) else {}

    return {}


def _extract_isi(raw: dict[str, Any]) -> float:
    """
    Extract ISI from run_diff output.
    """
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}

    candidates = [
        raw.get("isi"),
        raw.get("manifold_score"),
        evidence.get("isi_final"),
        evidence.get("isi_hard"),
        evidence.get("isi_tda"),
    ]

    for item in candidates:
        if item is not None:
            try:
                return float(item)
            except (TypeError, ValueError):
                continue

    return 0.0


def _extract_verdict(raw: dict[str, Any], isi: float) -> str:
    verdict = raw.get("verdict")

    if isinstance(verdict, str) and verdict.strip():
        return verdict.strip()

    kappa = float(getattr(settings, "kappa_d", 0.56))
    return "MANIFOLD_RUPTURE" if isi < kappa else "COHERENT"


def _extract_fired_modules(raw: dict[str, Any]) -> list[str]:
    """
    Return only modules that actually fired.

    Internal evidence fields may include diagnostic strings such as:
    '[E10] skipped: local knowledge base not configured; no penalty applied'.

    Those are useful for internal debugging, but the public demo should expose
    only modules that actually triggered.
    """
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}

    candidates = [
        evidence.get("fired_modules"),
        raw.get("fired_modules"),
        evidence.get("extended_modules"),
        raw.get("extended_modules"),
        evidence.get("module_notes"),
        raw.get("module_notes"),
    ]

    fired: list[str] = []

    for item in candidates:
        if not isinstance(item, list):
            continue

        for module in item:
            if isinstance(module, str):
                text = module.strip()
                lower = text.lower()

                if not text:
                    continue

                skip_markers = [
                    "skipped",
                    "not configured",
                    "no penalty applied",
                    "triggered=false",
                    '"triggered": false',
                    "'triggered': false",
                    "enabled=false",
                    '"enabled": false',
                    "'enabled': false",
                ]

                if any(marker in lower for marker in skip_markers):
                    continue

                fired.append(text)
                continue

            if isinstance(module, dict):
                if "triggered" in module and not bool(module.get("triggered")):
                    continue

                if "penalty" in module:
                    try:
                        penalty = float(module.get("penalty", 1.0))
                        triggered = bool(module.get("triggered", False))

                        if penalty >= 1.0 and not triggered:
                            continue
                    except (TypeError, ValueError):
                        pass

                code = module.get("code")
                name = module.get("name")

                if code and name:
                    fired.append(f"{code} {name}")
                elif code:
                    fired.append(str(code))
                elif name:
                    fired.append(str(name))
                else:
                    fired.append(str(module))

    seen = set()
    clean: list[str] = []

    for item in fired:
        if item not in seen:
            seen.add(item)
            clean.append(item)

    return clean


def _extract_manipulation_alert(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Return a sanitized manipulation_alert object.

    The public demo exposes only:
    - triggered: bool
    - sources: list[str]

    Internal details are intentionally omitted.
    """
    alert = raw.get("manipulation_alert", {})

    if isinstance(alert, dict):
        sources = alert.get("sources", [])

        if not isinstance(sources, list):
            sources = []

        return {
            "triggered": bool(alert.get("triggered", False)),
            "sources": [str(item) for item in sources],
        }

    if hasattr(alert, "triggered"):
        sources = getattr(alert, "sources", [])

        if not isinstance(sources, list):
            sources = []

        return {
            "triggered": bool(getattr(alert, "triggered", False)),
            "sources": [str(item) for item in sources],
        }

    return {
        "triggered": False,
        "sources": [],
    }


# ==============================================================================
# SCHEMAS
# ==============================================================================


class DemoRequest(BaseModel):
    source: str = Field(
        ...,
        min_length=30,
        max_length=PUBLIC_DEMO_MAX_CHARS,
        description="Source text / texto fuente (ground truth)",
    )
    response: str = Field(
        ...,
        min_length=30,
        max_length=PUBLIC_DEMO_MAX_CHARS,
        description="AI response to audit / respuesta a auditar",
    )


class DemoResponse(BaseModel):
    status: str
    isi: float
    kappa_d: float
    kappa_r: float
    verdict: str
    zona: str
    riesgo: str
    fired_modules: list[str]
    manipulation_alert: dict[str, Any]
    latency_ms: float
    topological_score: float = 0.0
    lexical_overlap: float = 0.0
    audit_hash: str = ""
    demo: bool = True


class DemoHelpResponse(BaseModel):
    status: str
    message: str
    recommended: dict[str, Any]
    example_body: dict[str, str]
    expected_signal: dict[str, Any]
    next_steps: list[str]
    docs: dict[str, str]


# ==============================================================================
# ENDPOINTS
# ==============================================================================


@router.get(
    "/public/demo/audit",
    response_model=DemoHelpResponse,
    tags=["Public"],
    summary="How to use the public SAS demo audit",
    include_in_schema=False,
)
async def public_demo_audit_help() -> DemoHelpResponse:
    """
    Human-friendly help for users/browsers that open /public/demo/audit with GET.

    The real demo endpoint is POST /public/demo/audit.
    This converts accidental 405s into onboarding instructions.
    """
    source = "The Eiffel Tower is located in Paris, France, and was built in 1889."
    response = "The Eiffel Tower is located in Berlin, Germany, and was built in 1950."

    return DemoHelpResponse(
        status="info",
        message="Use POST /public/demo/audit with source and response fields.",
        recommended={
            "cli": {
                "install": "pip install sas-client",
                "command": f'sas demo-audit "{source}" "{response}"',
            },
            "curl": (
                "curl -X POST https://sas-api.onrender.com/public/demo/audit "
                "-H 'Content-Type: application/json' "
                f"-d '{{\"source\":\"{source}\",\"response\":\"{response}\"}}'"
            ),
            "powershell": (
                'Invoke-RestMethod -Method Post '
                '-Uri "https://sas-api.onrender.com/public/demo/audit" '
                '-ContentType "application/json" '
                f"-Body '{{\"source\":\"{source}\",\"response\":\"{response}\"}}'"
            ),
        },
        example_body={
            "source": source,
            "response": response,
        },
        expected_signal={
            "kappa_d": float(getattr(settings, "kappa_d", 0.56)),
            "note": (
                "The public demo returns a simplified response. "
                "Use /v1/diff with an API key for the full forensic response."
            ),
        },
        next_steps=[
            "Try the no-key demo with: sas demo-audit \"source\" \"response\"",
            'Request a Free key with: sas request-key --email you@example.com --name "Your Name"',
            "Set SAS_API_KEY or SAS_KEY with the key received by email.",
            'Run authenticated diff with: sas diff "source" "response"',
        ],
        docs={
            "api": "https://sas-api.onrender.com/docs",
            "landing_demo": "https://leesintheblindmonk1999.github.io/sas-landing/#demo",
            "pypi": "https://pypi.org/project/sas-client/",
            "github": "https://github.com/Leesintheblindmonk1999/SAS",
        },
    )


@router.post(
    "/public/demo/audit",
    response_model=DemoResponse,
    tags=["Public"],
    summary="Public SAS demo audit - no API key required",
    description=(
        "Public demo of the SAS forensic engine. Uses the same pipeline as /v1/diff: "
        "TDA H0+H1 + NIG + E9-E12 with kappa_D=0.56. "
        "Source = reference text. Response = text to audit. "
        "No API key required. Full text is not stored. "
        f"Max {PUBLIC_DEMO_MAX_CHARS} chars per field. "
        f"Limit: {PUBLIC_DEMO_LIMIT_PER_DAY} requests/day per IP."
    ),
)
async def public_demo_audit(payload: DemoRequest, request: Request) -> DemoResponse:
    if not PUBLIC_DEMO_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    source = payload.source.strip()
    response = payload.response.strip()

    if len(source) < 30 or len(response) < 30:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid demo payload",
                "message": "Both source and response must contain at least 30 characters for a meaningful structural audit.",
                "example": {
                    "source": "The Eiffel Tower is located in Paris, France, and was built in 1889.",
                    "response": "The Eiffel Tower is located in Berlin, Germany, and was built in 1950.",
                },
            },
        )

    if len(source) > PUBLIC_DEMO_MAX_CHARS or len(response) > PUBLIC_DEMO_MAX_CHARS:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "Payload too large",
                "message": f"Maximum length exceeded. Limit: {PUBLIC_DEMO_MAX_CHARS} characters per field.",
                "free_key": {
                    "cli": 'sas request-key --email you@example.com --name "Your Name"',
                    "endpoint": "POST /public/request-key",
                },
            },
        )

    client_ip = _client_ip(request)
    ip_hash = _hash_ip(client_ip)
    _check_rate(ip_hash)

    t0 = time.perf_counter()

    try:
        from app.services.detector import run_diff

        raw = _to_dict(
            run_diff(
                text_a=source,
                text_b=response,
                experimental=True,
                domain="generic",
                enable_modules=None,
            )
        )

    except Exception as exc:
        logger.error(
            "public_demo_audit_failed ip_hash=%s src_len=%d res_len=%d error=%s",
            ip_hash,
            len(source),
            len(response),
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal analysis error",
                "message": "Internal analysis error. No text was stored.",
            },
        )

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    isi = _extract_isi(raw)
    verdict = _extract_verdict(raw, isi)
    fired_modules = _extract_fired_modules(raw)
    manipulation_alert = _extract_manipulation_alert(raw)

    # ── Zona / Riesgo (3-zone classification) ─────────────────────────
    kappa_d = float(getattr(settings, "kappa_d", 0.56))
    kappa_r = float(getattr(settings, "kappa_r", 0.15))

    if isi < kappa_r:
        zona = "COLAPSO_ESTRUCTURAL"
        riesgo = "CRITICAL"
    elif isi < kappa_d:
        zona = "RUPTURA_RECUPERABLE"
        riesgo = "HIGH"
    else:
        zona = "COHERENTE"
        riesgo = "LOW"

    # ── R3.2 Topological score (optional module) ──────────────────────
    topological_score = 0.0
    lexical_overlap = 0.0
    audit_hash = ""
    try:
        from core.r3_2_topological import evaluate_r3_2

        r32 = evaluate_r3_2(source, response)
        topological_score = float(r32.get("topological_score", 0.0))
        lexical_overlap = float(r32.get("lexical_overlap", 0.0))
        audit_hash = str(r32.get("audit_hash", ""))
    except Exception:
        pass

    logger.info(
        "public_demo ip_hash=%s src_len=%d res_len=%d isi=%.6f verdict=%s modules=%d latency_ms=%.2f",
        ip_hash,
        len(source),
        len(response),
        isi,
        verdict,
        len(fired_modules),
        latency_ms,
    )

    return DemoResponse(
        status="ok",
        isi=round(isi, 6),
        kappa_d=kappa_d,
        kappa_r=kappa_r,
        verdict=verdict,
        zona=zona,
        riesgo=riesgo,
        fired_modules=fired_modules,
        manipulation_alert=manipulation_alert,
        latency_ms=latency_ms,
        topological_score=round(topological_score, 6),
        lexical_overlap=round(lexical_overlap, 6),
        audit_hash=audit_hash,
        demo=True,
    )
