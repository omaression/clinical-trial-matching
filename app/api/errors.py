import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_DEFAULT_ERROR_CODES = {
    400: "bad_request",
    401: "invalid_api_key",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_server_error",
    503: "service_unavailable",
}


def error_code_for_status(status_code: int) -> str:
    return _DEFAULT_ERROR_CODES.get(status_code, "request_error")


def api_exception(
    status_code: int,
    detail: str,
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "code": code or error_code_for_status(status_code),
        },
        headers=headers,
    )


def error_payload(request: Request, detail: str, code: str | None = None) -> dict[str, str | None]:
    return {
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        detail = str(exc.detail.get("detail", "Request failed"))
        code = str(exc.detail.get("code") or error_code_for_status(exc.status_code))
    else:
        detail = str(exc.detail)
        code = error_code_for_status(exc.status_code)

    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, detail, code),
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else None
    detail = "Request validation error"
    if first_error:
        location = ".".join(str(part) for part in first_error.get("loc", ()) if part != "body")
        prefix = f"{location}: " if location else ""
        detail = f"{prefix}{first_error.get('msg', detail)}"

    return JSONResponse(
        status_code=422,
        content=error_payload(request, detail, error_code_for_status(422)),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(request, "Internal server error", error_code_for_status(500)),
    )
