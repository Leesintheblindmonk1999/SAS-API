"""
app/routers/tribunal.py — SAS Multimetric Tribunal v1.1.0
═══════════════════════════════════════════════════════════════════════════════
/v2/audit endpoint — Full multimetric tribunal analysis.

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_api_key
from app.models.tribunal import TribunalRequest, TribunalResponse, ModuloTribunal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tribunal"])

# ── Import tribunal core ───────────────────────────────────────────────────────
try:
    from core.tribunal_multimetrico import evaluar_par, VeredictoTribunal
    _TRIBUNAL_AVAILABLE = True
except ImportError as exc:
    _TRIBUNAL_AVAILABLE = False
    logger.warning("Tribunal multimétrico no disponible: %s", exc)


def _veredicto_to_response(
    v: VeredictoTribunal,
    request_id: str,
    start_ns: int,
) -> TribunalResponse:
    """Convert VeredictoTribunal to TribunalResponse model."""
    elapsed_ms = (time.time_ns() - start_ns) / 1_000_000

    # Build module list
    modulos = [
        ModuloTribunal(
            nombre="lexical_baseline_score",
            peso=0.35,
            valor=v.lexical_baseline_score,
            disparado=v.lexical_baseline_score < 1.0,
            descripcion="Jaccard lexical overlap",
        ),
        ModuloTribunal(
            nombre="source_target_guard",
            peso=0.25,
            valor=v.source_target_guard,
            disparado=v.source_target_guard < 1.0,
            descripcion="Critical entity mutation detection",
        ),
        ModuloTribunal(
            nombre="flow_penalty",
            peso=0.12,
            valor=v.flow_penalty,
            disparado=v.flow_penalty < 1.0,
            descripcion="Semantic flow rupture",
        ),
        ModuloTribunal(
            nombre="negation_penalty",
            peso=0.08,
            valor=v.negation_penalty,
            disparado=v.negation_penalty < 1.0,
            descripcion="Logical inversions",
        ),
        ModuloTribunal(
            nombre="cre_isi",
            peso=0.12,
            valor=v.cre_isi,
            disparado=v.cre_isi < 1.0,
            descripcion="Ricci semantic curvature",
        ),
        ModuloTribunal(
            nombre="arithmetic_penalty",
            peso=0.04,
            valor=v.arithmetic_penalty,
            disparado=v.arithmetic_penalty < 1.0,
            descripcion="Arithmetic errors",
        ),
        ModuloTribunal(
            nombre="reference_penalty",
            peso=0.04,
            valor=v.reference_penalty,
            disparado=v.reference_penalty < 1.0,
            descripcion="Reference fabrication",
        ),
    ]

    # Fired modules list
    fired = [m.nombre for m in modulos if m.disparado]

    # R3.1 guard
    r3_1_fired = v.r3_1_guard < 1.0 if hasattr(v, "r3_1_guard") else False

    return TribunalResponse(
        hash_source=v.hash_source,
        hash_response=v.hash_response,
        request_id=request_id,
        lexical_baseline_score=v.lexical_baseline_score,
        source_target_guard=v.source_target_guard,
        flow_penalty=v.flow_penalty,
        negation_penalty=v.negation_penalty,
        cre_isi=v.cre_isi,
        arithmetic_penalty=v.arithmetic_penalty,
        reference_penalty=v.reference_penalty,
        r3_1_guard=v.r3_1_guard if hasattr(v, "r3_1_guard") else None,
        isi_hard=v.isi_hard,
        isi_soft=v.isi_soft,
        isi_final=v.isi_final,
        kappa_d=v.kappa_d,
        kappa_r=v.kappa_r,
        zona=v.zona,
        riesgo=v.riesgo,
        codigo_zona=v.codigo_zona,
        modulos_disparados=fired,
        modulos=modulos,
        r3_1_fired=r3_1_fired,
        latency_ms=round(elapsed_ms, 2),
    )


@router.get(
    "/v2/audit",
    summary="Help: how to use the tribunal endpoint",
    include_in_schema=False,
)
async def tribunal_help():
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={
            "error": "This endpoint requires POST, not GET.",
            "usage": {
                "method": "POST",
                "url": "/v2/audit",
                "headers": {
                    "X-API-Key": "your_api_key_here",
                    "Content-Type": "application/json",
                },
                "body": {
                    "source": "Original text to audit against",
                    "response": "Response text to evaluate",
                    "enable_r3_1": True,
                    "kappa_d": 0.56,
                    "kappa_r": 0.15,
                },
                "how_to_get_a_key": {
                    "cli": "pip install sas-client && sas request-key --email you@example.com",
                    "http": "POST https://sas-api.onrender.com/public/request-key",
                    "landing": "https://leesintheblindmonk1999.github.io/sas-landing/#access",
                },
            },
        },
    )


@router.post(
    "/v2/audit",
    response_model=TribunalResponse,
    summary="Full multimetric tribunal analysis (7 modules + optional R3.1 Guard)",
)
async def tribunal_audit(
    request: TribunalRequest,
    api_key: str = Depends(get_api_key),
) -> TribunalResponse:
    """
    Evaluate a (source, response) pair using the SAS Multimetric Tribunal v1.1.0.

    The tribunal runs 7 detection modules with cascading multiplicative penalty:
      1. lexical_baseline_score  — Jaccard lexical overlap (0.35)
      2. source_target_guard     — Critical entity mutation (0.25)
      3. flow_penalty            — Semantic flow rupture (0.12)
      4. negation_penalty        — Logical inversions (0.08)
      5. cre_isi                 — Ricci semantic curvature (0.12)
      6. arithmetic_penalty      — Arithmetic errors (0.04)
      7. reference_penalty       — Reference fabrication (0.04)

    Plus optional R3.1 Differential Guard (grounding + compression + short-response).

    Returns ISI, structural zone (A/B/F-S), per-module scores, and fired modules.
    """
    if not _TRIBUNAL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Tribunal multimétrico no disponible")

    request_id = str(uuid.uuid4())
    start_ns = time.time_ns()

    try:
        # Set R3.1 flag before calling
        import core.tribunal_multimetrico as tm
        tm.R3_1_GUARD_ENABLED = request.enable_r3_1

        # Run tribunal
        kd = request.kappa_d or 0.56
        kr = request.kappa_r or 0.15
        verdicto = evaluar_par(
            source=request.source,
            response=request.response,
            kappa_d=kd,
            kappa_r=kr,
            request_id=request_id,
        )

        return _veredicto_to_response(verdicto, request_id, start_ns)

    except Exception as exc:
        logger.exception("Error en tribunal audit")
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}")