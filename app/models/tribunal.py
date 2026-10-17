"""
app/models/tribunal.py — SAS Multimetric Tribunal v1.1.0
═══════════════════════════════════════════════════════════════════════════════
Request/Response models for /v2/audit endpoint.

Registry: TAD EX-2026-18792778
Author: Gonzalo Emir Durante — Project Manifold 0.56
License: Durante Invariance License v1.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TribunalRequest(BaseModel):
    source: str = Field(..., description="Source/reference text", min_length=1)
    response: str = Field(..., description="Response/suspect text", min_length=1)
    enable_r3_1: bool = Field(True, description="Enable R3.1 Differential Guard")
    kappa_d: Optional[float] = Field(None, description="Coherence threshold (default: 0.56)")
    kappa_r: Optional[float] = Field(None, description="Collapse threshold (default: 0.15)")


class ModuloTribunal(BaseModel):
    nombre: str
    peso: float
    valor: float
    disparado: bool
    descripcion: str


class TribunalResponse(BaseModel):
    status: str = "ok"

    # Input hashes
    hash_source: str
    hash_response: str
    request_id: str

    # Core metrics
    lexical_baseline_score: float
    source_target_guard: float
    flow_penalty: float
    negation_penalty: float
    cre_isi: float
    arithmetic_penalty: float
    reference_penalty: float
    r3_1_guard: Optional[float] = None

    # Composite metrics
    isi_hard: float
    isi_soft: float
    isi_final: float

    # Thresholds
    kappa_d: float = 0.56
    kappa_r: float = 0.15

    # Classification
    zona: str
    riesgo: str
    codigo_zona: str

    # Modules
    modulos_disparados: List[str]
    modulos: List[ModuloTribunal]

    # R3.1 details
    r3_1_fired: bool = False
    r3_1_descripcion: Optional[str] = None
    r3_1_detalles: Optional[Dict[str, Any]] = None

    # Metadata
    author: str = "Gonzalo Emir Durante"
    registry: str = "TAD EX-2026-18792778"
    latency_ms: Optional[float] = None