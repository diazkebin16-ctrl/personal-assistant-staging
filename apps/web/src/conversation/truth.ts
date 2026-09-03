import type { ConversationMessage } from "../api/contracts";

export type TruthfulPresentation = Readonly<{
  tone: "normal" | "waiting" | "denied" | "unsupported" | "failed" | "prepared";
  label: string;
  content: string;
  confirmationId: string | null;
}>;

export function presentAssistantMessage(
  message: ConversationMessage,
): TruthfulPresentation {
  if (
    message.status === "FAILED" ||
    message.outcome === "FAILED" ||
    message.outcome === null
  ) {
    return Object.freeze({
      tone: "failed",
      label: "Failed",
      content: message.content,
      confirmationId: null,
    });
  }
  switch (message.outcome) {
    case "ACTION_WAITING_PERMISSION":
    case "MEMORY_PERMISSION_REQUIRED":
    case "RESEARCH_PERMISSION_REQUIRED":
      return Object.freeze({
        tone: "waiting",
        label: "Permission required",
        content: message.content,
        confirmationId: null,
      });
    case "ACTION_WAITING_CONFIRMATION":
    case "MEMORY_CONFIRMATION_REQUIRED":
    case "RESEARCH_CONFIRMATION_REQUIRED":
      return Object.freeze({
        tone: "waiting",
        label: "Confirmation required",
        content: message.content,
        confirmationId: message.confirmation_request_id,
      });
    case "ACTION_READY_FOR_FUTURE_EXECUTION":
      return Object.freeze({
        tone: "prepared",
        label: "Prepared — not executed",
        content: message.content,
        confirmationId: null,
      });
    case "ACTION_DENIED":
    case "RESEARCH_POLICY_DENIED":
      return Object.freeze({
        tone: "denied",
        label: "Denied",
        content: message.content,
        confirmationId: null,
      });
    case "ACTION_UNSUPPORTED":
    case "MEMORY_TARGET_REQUIRED":
    case "RESEARCH_UNAVAILABLE":
    case "RESEARCH_INSUFFICIENT_EVIDENCE":
      return Object.freeze({
        tone: "unsupported",
        label: "Unsupported",
        content: message.content,
        confirmationId: null,
      });
    default:
      return Object.freeze({
        tone: "normal",
        label: "Completed",
        content: message.content,
        confirmationId: null,
      });
  }
}
