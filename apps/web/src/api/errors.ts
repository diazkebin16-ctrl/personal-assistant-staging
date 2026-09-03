import type { ApiErrorEnvelope } from "./contracts";

export type ErrorCategory =
  | "AUTH_REQUIRED"
  | "FORBIDDEN"
  | "VALIDATION_ERROR"
  | "NETWORK_OFFLINE"
  | "TIMEOUT"
  | "SERVER_UNAVAILABLE"
  | "CONFLICT"
  | "PERMISSION_REQUIRED"
  | "CONFIRMATION_REQUIRED"
  | "SAFE_MODE"
  | "UNSUPPORTED"
  | "INTERNAL_ERROR";

export class ApiError extends Error {
  readonly category: ErrorCategory;
  readonly status: number | null;
  readonly code: string | null;
  readonly confirmationId: string | null;

  constructor(
    category: ErrorCategory,
    message: string,
    options: {
      status?: number;
      code?: string;
      confirmationId?: string | null;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.category = category;
    this.status = options.status ?? null;
    this.code = options.code ?? null;
    this.confirmationId = options.confirmationId ?? null;
  }
}

const SAFE_MESSAGES: Record<ErrorCategory, string> = {
  AUTH_REQUIRED: "Your session has expired. Sign in again.",
  FORBIDDEN: "The server denied this request.",
  VALIDATION_ERROR: "The request could not be validated.",
  NETWORK_OFFLINE: "The assistant is unavailable while you are offline.",
  TIMEOUT: "The server did not respond in time.",
  SERVER_UNAVAILABLE: "The assistant service is temporarily unavailable.",
  CONFLICT: "Server state changed. Refresh before trying again.",
  PERMISSION_REQUIRED: "Assistant permission is required.",
  CONFIRMATION_REQUIRED: "Server confirmation is required.",
  SAFE_MODE: "Safe Mode prevents this operation.",
  UNSUPPORTED: "This request is not supported.",
  INTERNAL_ERROR: "The request could not be completed.",
};

export function classifyHttpError(
  status: number,
  body: ApiErrorEnvelope,
): ApiError {
  const code = typeof body.error?.code === "string" ? body.error.code : "";
  let category: ErrorCategory = "INTERNAL_ERROR";
  if (status === 401) category = "AUTH_REQUIRED";
  else if (code.includes("CONFIRMATION_REQUIRED"))
    category = "CONFIRMATION_REQUIRED";
  else if (code.includes("PERMISSION_REQUIRED"))
    category = "PERMISSION_REQUIRED";
  else if (code.includes("SAFE_MODE")) category = "SAFE_MODE";
  else if (code.includes("UNSUPPORTED") || code.includes("ACTION_NOT_ALLOWED"))
    category = "UNSUPPORTED";
  else if (status === 403) category = "FORBIDDEN";
  else if (status === 409) category = "CONFLICT";
  else if (status === 400 || status === 422) category = "VALIDATION_ERROR";
  else if (status >= 500) category = "SERVER_UNAVAILABLE";
  return new ApiError(category, SAFE_MESSAGES[category], {
    status,
    ...(code ? { code } : {}),
    confirmationId:
      typeof body.confirmation_id === "string" ? body.confirmation_id : null,
  });
}

export function classifyTransportError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError("TIMEOUT", SAFE_MESSAGES.TIMEOUT);
  }
  if (!globalThis.navigator.onLine) {
    return new ApiError("NETWORK_OFFLINE", SAFE_MESSAGES.NETWORK_OFFLINE);
  }
  return new ApiError("SERVER_UNAVAILABLE", SAFE_MESSAGES.SERVER_UNAVAILABLE);
}
