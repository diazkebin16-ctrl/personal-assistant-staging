"""Safe application errors and API error responses."""

from enum import StrEnum

from pydantic import BaseModel


class ErrorCode(StrEnum):
    """Stable machine-readable error codes."""

    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"  # noqa: S105 - public error code, not a credential.
    EXPIRED_TOKEN = "EXPIRED_TOKEN"  # noqa: S105 - public error code, not a credential.
    AUTH_VERIFICATION_UNAVAILABLE = "AUTH_VERIFICATION_UNAVAILABLE"
    USER_DISABLED = "USER_DISABLED"
    SESSION_REVOKED = "SESSION_REVOKED"
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    INVALID_DEVICE_DATA = "INVALID_DEVICE_DATA"
    INVALID_REQUEST = "INVALID_REQUEST"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    PERMISSION_NOT_FOUND = "PERMISSION_NOT_FOUND"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    PERMISSION_EXPIRED = "PERMISSION_EXPIRED"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    DEVICE_SCOPE_MISMATCH = "DEVICE_SCOPE_MISMATCH"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"
    CAPABILITY_NOT_FOUND = "CAPABILITY_NOT_FOUND"
    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_NOT_FOUND = "CONFIRMATION_NOT_FOUND"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
    RISK_POLICY_DENIED = "RISK_POLICY_DENIED"
    FINANCIAL_EXECUTION_DENIED = "FINANCIAL_EXECUTION_DENIED"
    STEP_UP_AUTHENTICATION_REQUIRED = "STEP_UP_AUTHENTICATION_REQUIRED"
    AUTHORIZATION_UNAVAILABLE = "AUTHORIZATION_UNAVAILABLE"
    INVALID_PERMISSION_DATA = "INVALID_PERMISSION_DATA"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    INVALID_TASK_DATA = "INVALID_TASK_DATA"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_ALREADY_TERMINAL = "TASK_ALREADY_TERMINAL"
    INVALID_TASK_TRANSITION = "INVALID_TASK_TRANSITION"
    TASK_IDEMPOTENCY_CONFLICT = "TASK_IDEMPOTENCY_CONFLICT"
    TASK_EXPIRED = "TASK_EXPIRED"
    TASK_NOT_CLAIMABLE = "TASK_NOT_CLAIMABLE"
    TASK_CONCURRENT_MODIFICATION = "TASK_CONCURRENT_MODIFICATION"
    TASK_DEVICE_INVALID = "TASK_DEVICE_INVALID"
    TASK_AUTHORIZATION_DENIED = "TASK_AUTHORIZATION_DENIED"
    INVALID_MEMORY_DATA = "INVALID_MEMORY_DATA"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    MEMORY_AUTHORIZATION_DENIED = "MEMORY_AUTHORIZATION_DENIED"
    MEMORY_CONFIRMATION_REQUIRED = "MEMORY_CONFIRMATION_REQUIRED"
    MEMORY_CONCURRENT_MODIFICATION = "MEMORY_CONCURRENT_MODIFICATION"
    MEMORY_DUPLICATE_CONFLICT = "MEMORY_DUPLICATE_CONFLICT"
    MEMORY_IMMUTABLE = "MEMORY_IMMUTABLE"
    AI_ROUTING_DENIED = "AI_ROUTING_DENIED"
    AI_PROVIDER_FAILURE = "AI_PROVIDER_FAILURE"
    INVALID_ORCHESTRATION_DATA = "INVALID_ORCHESTRATION_DATA"
    ORCHESTRATION_NOT_FOUND = "ORCHESTRATION_NOT_FOUND"
    INVALID_ORCHESTRATION_TRANSITION = "INVALID_ORCHESTRATION_TRANSITION"
    ORCHESTRATION_ALREADY_TERMINAL = "ORCHESTRATION_ALREADY_TERMINAL"
    ORCHESTRATION_CONCURRENT_MODIFICATION = "ORCHESTRATION_CONCURRENT_MODIFICATION"
    ORCHESTRATION_IDEMPOTENCY_CONFLICT = "ORCHESTRATION_IDEMPOTENCY_CONFLICT"
    ORCHESTRATION_DENIED = "ORCHESTRATION_DENIED"
    INVALID_CONVERSATION_DATA = "INVALID_CONVERSATION_DATA"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    CONVERSATION_CONCURRENT_MODIFICATION = "CONVERSATION_CONCURRENT_MODIFICATION"
    MESSAGE_IDEMPOTENCY_CONFLICT = "MESSAGE_IDEMPOTENCY_CONFLICT"
    INVALID_VOICE_DATA = "INVALID_VOICE_DATA"
    VOICE_SESSION_NOT_FOUND = "VOICE_SESSION_NOT_FOUND"
    VOICE_SESSION_AUTH_FAILED = "VOICE_SESSION_AUTH_FAILED"
    VOICE_SESSION_EXPIRED = "VOICE_SESSION_EXPIRED"
    VOICE_SESSION_CONFLICT = "VOICE_SESSION_CONFLICT"
    INVALID_VOICE_TRANSITION = "INVALID_VOICE_TRANSITION"
    REALTIME_MODEL_UNAVAILABLE = "REALTIME_MODEL_UNAVAILABLE"
    VOICE_TURN_IDEMPOTENCY_CONFLICT = "VOICE_TURN_IDEMPOTENCY_CONFLICT"
    VOICE_RECONNECT_EXHAUSTED = "VOICE_RECONNECT_EXHAUSTED"


class ErrorDetail(BaseModel):
    """Public error detail without internal implementation data."""

    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    """Consistent public error envelope."""

    error: ErrorDetail


class ApplicationError(Exception):
    """Base exception carrying only safe response information."""

    def __init__(self, code: ErrorCode, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


class InvalidOrchestrationDataError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.INVALID_ORCHESTRATION_DATA, 422, "The orchestration request is invalid."
        )


class OrchestrationNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.ORCHESTRATION_NOT_FOUND, 404, "The orchestration is not available."
        )


class InvalidOrchestrationTransitionError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.INVALID_ORCHESTRATION_TRANSITION,
            409,
            "The requested orchestration transition is invalid.",
        )


class OrchestrationAlreadyTerminalError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.ORCHESTRATION_ALREADY_TERMINAL,
            409,
            "The orchestration is already terminal.",
        )


class OrchestrationConcurrentModificationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.ORCHESTRATION_CONCURRENT_MODIFICATION,
            409,
            "The orchestration changed before this operation could be applied.",
        )


class OrchestrationIdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.ORCHESTRATION_IDEMPOTENCY_CONFLICT,
            409,
            "The idempotency key belongs to a different orchestration request.",
        )


class AuthenticationRequiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AUTHENTICATION_REQUIRED,
            401,
            "Authentication is required.",
        )


class InvalidTokenError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.INVALID_TOKEN, 401, "The authentication token is invalid.")


class ExpiredTokenError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.EXPIRED_TOKEN, 401, "The authentication token has expired.")


class AuthVerificationUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AUTH_VERIFICATION_UNAVAILABLE,
            503,
            "Authentication verification is temporarily unavailable.",
        )


class UserDisabledError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.USER_DISABLED, 403, "The user identity is disabled.")


class SessionRevokedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.SESSION_REVOKED, 401, "The authenticated session is revoked.")


class DeviceNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.DEVICE_NOT_FOUND, 404, "The device is not available.")


class DeviceRevokedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.DEVICE_REVOKED, 403, "The device has been revoked.")


class IdentityConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.IDENTITY_CONFLICT,
            409,
            "The identity state conflicts with the authenticated session.",
        )


class DatabaseUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.DATABASE_UNAVAILABLE,
            503,
            "Identity persistence is unavailable.",
        )


class PermissionNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.PERMISSION_NOT_FOUND, 404, "The permission is not available.")


class CapabilityNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CAPABILITY_NOT_FOUND, 404, "The capability is not available.")


class CapabilityDisabledError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CAPABILITY_DISABLED, 409, "The capability is disabled.")


class ActionNotAllowedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.ACTION_NOT_ALLOWED,
            422,
            "The requested operation is not defined for this capability.",
        )


class ConfirmationNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONFIRMATION_NOT_FOUND,
            404,
            "The confirmation request is not available.",
        )


class ConfirmationExpiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONFIRMATION_EXPIRED,
            409,
            "The confirmation request has expired.",
        )


class ConfirmationRejectedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONFIRMATION_REJECTED,
            409,
            "The confirmation request was rejected.",
        )


class StepUpAuthenticationRequiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.STEP_UP_AUTHENTICATION_REQUIRED,
            403,
            "AAL2 authentication is required for permission administration.",
        )


class AuthorizationUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AUTHORIZATION_UNAVAILABLE,
            503,
            "Authorization cannot be established safely.",
        )


class InvalidPermissionDataError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.INVALID_PERMISSION_DATA,
            422,
            "The permission data is invalid.",
        )


class AuditUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AUDIT_UNAVAILABLE,
            503,
            "Required audit evidence cannot be recorded safely.",
        )


class TaskNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TASK_NOT_FOUND, 404, "The task is not available.")


class TaskAlreadyTerminalError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TASK_ALREADY_TERMINAL, 409, "The task is already terminal.")


class InvalidTaskTransitionError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.INVALID_TASK_TRANSITION, 409, "The requested task transition is invalid."
        )


class TaskIdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.TASK_IDEMPOTENCY_CONFLICT,
            409,
            "The idempotency key belongs to a different task request.",
        )


class TaskExpiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TASK_EXPIRED, 409, "The task has expired.")


class TaskNotClaimableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TASK_NOT_CLAIMABLE, 409, "The task is not claimable.")


class TaskConcurrentModificationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.TASK_CONCURRENT_MODIFICATION,
            409,
            "The task changed before this operation could be applied.",
        )


class TaskDeviceInvalidError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.TASK_DEVICE_INVALID, 422, "The task device is not an active owned device."
        )


class TaskAuthorizationDeniedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.TASK_AUTHORIZATION_DENIED,
            403,
            "Task creation is denied by the authorization boundary.",
        )


class InvalidMemoryDataError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.INVALID_MEMORY_DATA, 422, "The memory data is invalid.")


class MemoryConcurrentModificationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.MEMORY_CONCURRENT_MODIFICATION,
            409,
            "The memory changed before this operation could be applied.",
        )


class MemoryDuplicateConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.MEMORY_DUPLICATE_CONFLICT,
            409,
            "The update conflicts with an existing active memory.",
        )


class MemoryImmutableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.MEMORY_IMMUTABLE,
            409,
            "Historical decisions cannot be overwritten.",
        )


class AIRoutingDeniedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AI_ROUTING_DENIED,
            503,
            "No model can satisfy the authoritative routing policy safely.",
        )


class AIProviderExecutionError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.AI_PROVIDER_FAILURE,
            503,
            "The bounded provider attempt chain could not complete safely.",
        )


class ConversationNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONVERSATION_NOT_FOUND, 404, "The conversation is not available."
        )


class ConversationConcurrentModificationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONVERSATION_CONCURRENT_MODIFICATION,
            409,
            "The conversation changed before this message could be submitted.",
        )


class MessageIdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT,
            409,
            "The idempotency key belongs to a different message request.",
        )


class VoiceSessionNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_SESSION_NOT_FOUND, 404, "The voice session is unavailable."
        )


class VoiceSessionAuthFailedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_SESSION_AUTH_FAILED,
            401,
            "The voice session credential is invalid.",
        )


class VoiceSessionExpiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_SESSION_EXPIRED,
            401,
            "The voice session credential has expired.",
        )


class VoiceSessionConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_SESSION_CONFLICT,
            409,
            "The voice session already has an active connection.",
        )


class InvalidVoiceTransitionApplicationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.INVALID_VOICE_TRANSITION,
            409,
            "The requested voice session transition is invalid.",
        )


class RealtimeModelUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.REALTIME_MODEL_UNAVAILABLE,
            503,
            "No approved realtime voice provider is available.",
        )


class VoiceTurnIdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_TURN_IDEMPOTENCY_CONFLICT,
            409,
            "The voice turn identity belongs to different final content.",
        )


class VoiceReconnectExhaustedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.VOICE_RECONNECT_EXHAUSTED,
            409,
            "The bounded voice reconnect policy is exhausted.",
        )
