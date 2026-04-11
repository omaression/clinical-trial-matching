from app.api.schemas import ErrorResponse


def _error_response(status_code: int, description: str, detail: str, code: str):
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {
                    "detail": detail,
                    "code": code,
                    "request_id": "7d3f998a-865f-4adf-a1b9-4cd34a6f70ef",
                }
            }
        },
    }


UNAUTHORIZED_RESPONSE = _error_response(
    401,
    "Missing or invalid API key",
    "Valid X-API-Key header required",
    "invalid_api_key",
)
NOT_FOUND_RESPONSE = _error_response(404, "Requested resource was not found", "Trial not found", "not_found")
CONFLICT_RESPONSE = _error_response(
    409,
    "Request conflicts with current resource state",
    "Criterion review has already been resolved",
    "conflict",
)
VALIDATION_RESPONSE = _error_response(
    422,
    "Request validation error",
    "nct_id: String should match pattern '^NCT\\d{8}$'",
    "validation_error",
)
RATE_LIMIT_RESPONSE = _error_response(
    429,
    "Operational rate limit exceeded",
    "Operational request rate limit exceeded",
    "rate_limit_exceeded",
)
INTERNAL_SERVER_ERROR_RESPONSE = _error_response(
    500,
    "Unhandled server error",
    "Internal server error",
    "internal_server_error",
)
SERVICE_UNAVAILABLE_RESPONSE = _error_response(
    503,
    "Required backend dependency unavailable",
    "Extraction pipeline unavailable",
    "service_unavailable",
)

COMMON_ERROR_RESPONSES = {
    422: VALIDATION_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
READ_ERROR_RESPONSES = {
    404: NOT_FOUND_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
PROTECTED_OPERATIONAL_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    422: VALIDATION_RESPONSE,
    429: RATE_LIMIT_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
    503: SERVICE_UNAVAILABLE_RESPONSE,
}
PROTECTED_REVIEW_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    404: NOT_FOUND_RESPONSE,
    409: CONFLICT_RESPONSE,
    422: VALIDATION_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
PROTECTED_READ_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
PROTECTED_MUTATION_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    422: VALIDATION_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
PROTECTED_RESOURCE_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    404: NOT_FOUND_RESPONSE,
    422: VALIDATION_RESPONSE,
    500: INTERNAL_SERVER_ERROR_RESPONSE,
}
