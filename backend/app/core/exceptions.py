class AppError(Exception):
    """业务异常基类，全局 exception handler 统一转换为 {code, message, detail} 响应。"""

    status_code: int = 400
    code: str = "app_error"

    def __init__(
        self,
        message: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.message = message
        self.detail = detail
        # 需要随错误响应一起下发的头（例如清会话 cookie 的 Set-Cookie）。
        # FastAPI 注入的 Response 在抛异常时会被丢弃，所以这类头必须挂在异常上。
        self.headers = headers
        super().__init__(message)


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int, detail: str | None = None):
        self.retry_after = retry_after
        super().__init__(message, detail)


class RegistrationDisabledError(AppError):
    status_code = 403
    code = "registration_disabled"


class AdminAlreadyInitializedError(AppError):
    status_code = 409
    code = "admin_already_initialized"


class AdminNotInitializedError(AppError):
    status_code = 409
    code = "admin_not_initialized"
