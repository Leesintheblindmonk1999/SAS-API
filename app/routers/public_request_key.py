"""
app/routers/public_request_key.py - Public free API key request endpoint.

GET  /public/request-key  -> onboarding help
POST /public/request-key  -> request a Free SAS API key

E0 improvements:
- More tolerant JSON parsing.
- Clear validation responses.
- Safe failed-attempt tracking without storing raw email/body.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError

from app.db.auth_store import (
    RateLimitError,
    create_or_rotate_key_for_email,
    register_failed_attempt,
)
from app.middleware.rate_limit import check_rate_limit, ip_hash
from app.services.audit_store import hash_ip_daily, save_validation_error
from app.services.email import send_api_key_email

router = APIRouter()
logger = logging.getLogger("sas.public_request_key")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RequestKeyPayload(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)


class RequestKeyResponse(BaseModel):
    status: str
    message: str
    plan: str
    email_delivery: dict[str, Any]


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("true-client-ip")
        or request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def _country(request: Request) -> str:
    return (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("x-country")
        or "unknown"
    )


def _safe_email_valid(value: Any) -> bool:
    if value is None:
        return False
    return bool(_EMAIL_RE.match(str(value).strip()))


async def _record_request_key_validation_failure(
    request: Request,
    *,
    reason: str,
    json_valid: bool,
    email_present: bool,
    email_valid: bool,
    name_present: bool,
    validation_error_types: list[str],
) -> None:
    """
    Store safe validation failure metadata.
    No raw body and no raw email are stored.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    client_ip = _client_ip(request)
    daily_ip_hash = hash_ip_daily(client_ip)

    try:
        register_failed_attempt(
            ip_hash=daily_ip_hash,
            reason=reason,
            email_present=email_present,
            name_present=name_present,
        )
    except Exception as exc:
        logger.warning(
            "request_key_failed_attempt_record_failed request_id=%s error=%s",
            request_id,
            exc,
        )

    try:
        content_length_raw = request.headers.get("content-length")
        try:
            content_length = int(content_length_raw) if content_length_raw else None
        except ValueError:
            content_length = None

        await save_validation_error(
            {
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method.upper(),
                "status": 422,
                "content_type": request.headers.get("content-type", ""),
                "content_length": content_length,
                "json_valid": json_valid,
                "email_present": email_present,
                "email_valid": email_valid,
                "name_present": name_present,
                "validation_error_types": json.dumps(validation_error_types),
                "ip_hash": daily_ip_hash,
                "country": _country(request).upper(),
            }
        )
    except Exception as exc:
        logger.warning(
            "request_key_validation_audit_record_failed request_id=%s error=%s",
            request_id,
            exc,
        )


def _validation_response(
    *,
    reason: str,
    missing_fields: list[str] | None = None,
    invalid_fields: list[str] | None = None,
    status_code: int = 422,
) -> JSONResponse:
    logger.warning(
        "request_key_validation_failure reason=%s status=%s missing=%s invalid=%s",
        reason, status_code, missing_fields or [], invalid_fields or [],
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "Validation error",
            "detail": (
                f"Missing required fields: {', '.join(missing_fields)}"
                if missing_fields
                else "Invalid request body for /public/request-key."
            ),
            "reason": reason,
            "missing_fields": missing_fields or [],
            "invalid_fields": invalid_fields or [],
            "required_format": {
                "email": "string, valid email address, required",
                "name": "optional string, max 120 characters",
            },
            "example": {
                "email": "you@example.com",
                "name": "Your Name",
            },
            "fix": {
                "cli": 'sas request-key --email you@example.com --name "Your Name"',
                "curl": (
                    "curl -X POST https://sas-api.onrender.com/public/request-key "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"email\":\"you@example.com\",\"name\":\"Your Name\"}'"
                ),
                "powershell": (
                    'Invoke-RestMethod -Method Post '
                    '-Uri "https://sas-api.onrender.com/public/request-key" '
                    '-ContentType "application/json" '
                    '-Body \'{"email":"you@example.com","name":"Your Name"}\''
                ),
                "help": "GET https://sas-api.onrender.com/public/request-key",
            },
        },
    )


async def _parse_request_body(request: Request) -> tuple[dict[str, Any] | None, str, bool]:
    """
    Parse body in a tolerant way.

    Returns:
        payload, reason_if_failed, json_valid

    Supports:
    - application/json
    - missing Content-Type if body starts with "{"
    - text/plain containing JSON
    - application/x-www-form-urlencoded as a compatibility fallback
    """
    content_type = (request.headers.get("content-type") or "").lower()
    raw = await request.body()
    stripped = raw.strip()

    if not stripped:
        return None, "invalid_json", False

    # JSON with proper content-type, missing content-type, or text/plain JSON.
    if (
        "application/json" in content_type
        or not content_type
        or "text/plain" in content_type
        or stripped.startswith(b"{")
    ):
        if "application/json" not in content_type:
            logger.warning(
                "request_key_json_without_content_type request_id=%s content_type=%s",
                getattr(request.state, "request_id", "unknown"),
                content_type or "missing",
            )

        try:
            parsed = json.loads(stripped.decode("utf-8"))
            if not isinstance(parsed, dict):
                return None, "invalid_json", False
            return parsed, "", True
        except Exception:
            return None, "invalid_json", False

    # Compatibility fallback for simple form posts.
    if "application/x-www-form-urlencoded" in content_type:
        parsed_qs = parse_qs(stripped.decode("utf-8", errors="ignore"))
        payload = {
            "email": parsed_qs.get("email", [""])[0],
            "name": parsed_qs.get("name", [""])[0] or None,
        }
        return payload, "", False

    return None, "wrong_content_type", False


@router.get(
    "/public/request-key",
    tags=["Public"],
    summary="Free API key onboarding help",
    include_in_schema=False,
)
async def request_key_help(request: Request) -> JSONResponse:
    """
    Help endpoint.

    If someone tries GET /public/request-key?email=..., explain clearly that key
    creation requires POST JSON.
    """
    if request.query_params.get("email"):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Use POST with JSON body to request a Free API key.",
                "required_format": {
                    "email": "string, valid email address, required",
                    "name": "optional string",
                },
                "example": {
                    "email": "you@example.com",
                    "name": "Your Name",
                },
                "fix": {
                    "cli": 'sas request-key --email you@example.com --name "Your Name"',
                    "curl": (
                        "curl -X POST https://sas-api.onrender.com/public/request-key "
                        "-H 'Content-Type: application/json' "
                        "-d '{\"email\":\"you@example.com\",\"name\":\"Your Name\"}'"
                    ),
                },
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "info",
            "message": "Use POST /public/request-key to request a Free SAS API key.",
            "recommended": {
                "cli": {
                    "install": "pip install sas-client",
                    "command": 'sas request-key --email you@example.com --name "Your Name"',
                },
                "curl": (
                    "curl -X POST https://sas-api.onrender.com/public/request-key "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"email\":\"you@example.com\",\"name\":\"Your Name\"}'"
                ),
                "powershell": (
                    'Invoke-RestMethod -Method Post '
                    '-Uri "https://sas-api.onrender.com/public/request-key" '
                    '-ContentType "application/json" '
                    '-Body \'{"email":"you@example.com","name":"Your Name"}\''
                ),
            },
            "free_plan": {
                "plan": "free",
                "limit": "50 requests/day",
                "delivery": "API key is sent by email automatically.",
                "rate_limit": "Limited by IP and email to reduce abuse.",
            },
            "next_steps": [
                "Install the CLI: pip install sas-client",
                'Request a key: sas request-key --email you@example.com --name "Your Name"',
                "Set SAS_API_KEY or SAS_KEY with the key received by email.",
                "Run: sas whoami",
                'Run: sas diff "source" "response"',
            ],
            "docs": {
                "api": "https://sas-api.onrender.com/docs",
                "landing": "https://leesintheblindmonk1999.github.io/sas-landing/#access",
                "pypi": "https://pypi.org/project/sas-client/",
                "github": "https://github.com/Leesintheblindmonk1999/SAS",
            },
        },
    )


@router.post(
    "/public/request-key",
    response_model=RequestKeyResponse,
    tags=["Public"],
    summary="Request a free SAS API key",
)
async def request_key(request: Request) -> RequestKeyResponse | JSONResponse:
    try:
        return await _request_key_impl(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("request_key_unhandled_error error=%s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal error",
                "detail": f"Unexpected error: {exc}",
                "reason": "unhandled_exception",
                "fix": {
                    "cli": 'sas request-key --email you@example.com --name "Your Name"',
                    "curl": (
                        "curl -X POST https://sas-api.onrender.com/public/request-key "
                        "-H 'Content-Type: application/json' "
                        "-d '{\"email\":\"you@example.com\",\"name\":\"Your Name\"}'"
                    ),
                },
            },
        )


async def _request_key_impl(request: Request) -> RequestKeyResponse | JSONResponse:
    hashed_ip = ip_hash(request)

    check_rate_limit(
        key=f"request-key:{hashed_ip}",
        limit=5,
        window_seconds=60 * 10,
    )

    if request.query_params.get("email"):
        await _record_request_key_validation_failure(
            request,
            reason="email_in_query",
            json_valid=False,
            email_present=True,
            email_valid=_safe_email_valid(request.query_params.get("email")),
            name_present=bool(request.query_params.get("name")),
            validation_error_types=["email_in_query"],
        )
        return _validation_response(
            reason="email_in_query",
            missing_fields=[],
            invalid_fields=["query.email"],
            status_code=400,
        )

    payload_dict, parse_reason, json_valid = await _parse_request_body(request)

    if payload_dict is None:
        await _record_request_key_validation_failure(
            request,
            reason=parse_reason or "invalid_json",
            json_valid=json_valid,
            email_present=False,
            email_valid=False,
            name_present=False,
            validation_error_types=[parse_reason or "invalid_json"],
        )
        return _validation_response(
            reason=parse_reason or "invalid_json",
            missing_fields=["email"],
            status_code=422,
        )

    email_value = payload_dict.get("email")
    name_value = payload_dict.get("name")

    email_present = email_value is not None and str(email_value).strip() != ""
    name_present = name_value is not None and str(name_value).strip() != ""
    email_valid = _safe_email_valid(email_value)

    logger.info(
        "request_key_payload email_present=%s email_valid=%s name_present=%s json_valid=%s content_type=%s",
        email_present, email_valid, name_present, json_valid,
        request.headers.get("content-type", "missing"),
    )

    if not email_present:
        await _record_request_key_validation_failure(
            request,
            reason="missing_email",
            json_valid=json_valid,
            email_present=False,
            email_valid=False,
            name_present=name_present,
            validation_error_types=["missing_email"],
        )
        return _validation_response(
            reason="missing_email",
            missing_fields=["email"],
            status_code=422,
        )

    if not email_valid:
        await _record_request_key_validation_failure(
            request,
            reason="invalid_email",
            json_valid=json_valid,
            email_present=True,
            email_valid=False,
            name_present=name_present,
            validation_error_types=["invalid_email"],
        )
        return _validation_response(
            reason="invalid_email",
            invalid_fields=["email"],
            status_code=422,
        )

    try:
        payload = RequestKeyPayload(email=email_value, name=name_value)
    except ValidationError as exc:
        error_types = []
        invalid_fields = []
        for err in exc.errors():
            error_types.append(str(err.get("type", "validation_error")))
            loc = err.get("loc")
            if loc:
                invalid_fields.append(".".join(str(x) for x in loc))

        await _record_request_key_validation_failure(
            request,
            reason="payload_validation_error",
            json_valid=json_valid,
            email_present=email_present,
            email_valid=email_valid,
            name_present=name_present,
            validation_error_types=error_types or ["payload_validation_error"],
        )
        return _validation_response(
            reason="payload_validation_error",
            invalid_fields=invalid_fields,
            status_code=422,
        )

    try:
        result = create_or_rotate_key_for_email(
            email=str(payload.email),
            name=payload.name,
            ip_hash=hashed_ip,
        )
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    user = result["user"]
    api_key = result["api_key"]

    email_result = send_api_key_email(
        email=user["email"],
        api_key=api_key,
        plan=user["plan"],
        name=user.get("name"),
    )

    if email_result.get("provider") == "log":
        message = "API key generated. Email provider is not configured; check server logs."
    else:
        message = "API key sent by email."

    return RequestKeyResponse(
        status="ok",
        message=message,
        plan=user["plan"],
        email_delivery={
            "sent": bool(email_result.get("sent")),
            "provider": email_result.get("provider"),
        },
    )
