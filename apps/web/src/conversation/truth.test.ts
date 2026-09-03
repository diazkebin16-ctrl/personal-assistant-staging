import { describe, expect, it } from "vitest";

import { message } from "../../tests/helpers";
import { presentAssistantMessage } from "./truth";

describe("truthful assistant presentation", () => {
  it.each([
    ["ANSWERED", "normal", "Completed"],
    ["MEMORY_SAVED", "normal", "Completed"],
    ["ACTION_WAITING_PERMISSION", "waiting", "Permission required"],
    ["MEMORY_PERMISSION_REQUIRED", "waiting", "Permission required"],
    ["RESEARCH_PERMISSION_REQUIRED", "waiting", "Permission required"],
    ["ACTION_WAITING_CONFIRMATION", "waiting", "Confirmation required"],
    ["MEMORY_CONFIRMATION_REQUIRED", "waiting", "Confirmation required"],
    ["RESEARCH_CONFIRMATION_REQUIRED", "waiting", "Confirmation required"],
    [
      "ACTION_READY_FOR_FUTURE_EXECUTION",
      "prepared",
      "Prepared — not executed",
    ],
    ["ACTION_DENIED", "denied", "Denied"],
    ["RESEARCH_POLICY_DENIED", "denied", "Denied"],
    ["ACTION_UNSUPPORTED", "unsupported", "Unsupported"],
    ["MEMORY_TARGET_REQUIRED", "unsupported", "Unsupported"],
    ["RESEARCH_UNAVAILABLE", "unsupported", "Unsupported"],
    ["RESEARCH_INSUFFICIENT_EVIDENCE", "unsupported", "Unsupported"],
    ["RESEARCH_ANSWERED", "normal", "Completed"],
    ["FAILED", "failed", "Failed"],
  ] as const)(
    "maps %s without manufacturing completion",
    (outcome, tone, label) => {
      const result = presentAssistantMessage(message("ASSISTANT", { outcome }));
      expect(result).toMatchObject({ tone, label });
    },
  );

  it("failed server status outranks an answered outcome", () => {
    expect(
      presentAssistantMessage(
        message("ASSISTANT", { status: "FAILED", outcome: "ANSWERED" }),
      ).tone,
    ).toBe("failed");
  });

  it("uses only a server confirmation identifier", () => {
    const result = presentAssistantMessage(
      message("ASSISTANT", {
        outcome: "ACTION_WAITING_CONFIRMATION",
        confirmation_request_id: "server-confirmation",
      }),
    );
    expect(result.confirmationId).toBe("server-confirmation");
  });
});
