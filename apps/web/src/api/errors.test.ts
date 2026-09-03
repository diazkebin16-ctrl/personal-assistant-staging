import { describe, expect, it } from "vitest";

import { classifyHttpError } from "./errors";

describe("API error classification", () => {
  it.each([
    [401, "EXPIRED_TOKEN", "AUTH_REQUIRED"],
    [403, "RISK_POLICY_DENIED", "FORBIDDEN"],
    [422, "INVALID_CONVERSATION_DATA", "VALIDATION_ERROR"],
    [409, "CONVERSATION_CONCURRENT_MODIFICATION", "CONFLICT"],
    [503, "DATABASE_UNAVAILABLE", "SERVER_UNAVAILABLE"],
    [403, "PERMISSION_REQUIRED", "PERMISSION_REQUIRED"],
    [409, "MEMORY_CONFIRMATION_REQUIRED", "CONFIRMATION_REQUIRED"],
    [409, "SAFE_MODE_BLOCKED", "SAFE_MODE"],
    [422, "ACTION_NOT_ALLOWED", "UNSUPPORTED"],
  ] as const)("maps %s/%s to %s", (status, code, category) => {
    expect(classifyHttpError(status, { error: { code } }).category).toBe(
      category,
    );
  });

  it("never exposes a backend-provided message", () => {
    const error = classifyHttpError(500, {
      error: { code: "UNKNOWN", message: "stack trace secret" },
    });
    expect(error.message).not.toContain("stack trace");
    expect(error.message).not.toContain("secret");
  });

  it("preserves only the server confirmation identifier", () => {
    const error = classifyHttpError(409, {
      error: { code: "MEMORY_CONFIRMATION_REQUIRED" },
      confirmation_id: "confirmation-id",
    });
    expect(error.confirmationId).toBe("confirmation-id");
  });
});
