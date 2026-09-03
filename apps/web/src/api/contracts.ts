export type UUID = string;

export type Identity = Readonly<{
  user_id: UUID;
  auth_user_id: UUID;
  display_name: string | null;
  device_id: UUID | null;
  authenticated: boolean;
  authentication_level: string;
}>;

export type Conversation = Readonly<{
  id: UUID;
  device_id: UUID | null;
  title: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}>;

export type AssistantOutcome =
  | "ANSWERED"
  | "MEMORY_SAVED"
  | "MEMORY_RECALLED"
  | "MEMORY_PERMISSION_REQUIRED"
  | "MEMORY_TARGET_REQUIRED"
  | "MEMORY_CONFIRMATION_REQUIRED"
  | "MEMORY_DELETED"
  | "ACTION_WAITING_PERMISSION"
  | "ACTION_WAITING_CONFIRMATION"
  | "ACTION_READY_FOR_FUTURE_EXECUTION"
  | "ACTION_DENIED"
  | "ACTION_UNSUPPORTED"
  | "RESEARCH_ANSWERED"
  | "RESEARCH_PERMISSION_REQUIRED"
  | "RESEARCH_CONFIRMATION_REQUIRED"
  | "RESEARCH_POLICY_DENIED"
  | "RESEARCH_UNAVAILABLE"
  | "RESEARCH_INSUFFICIENT_EVIDENCE"
  | "FAILED";

export type ResearchCitation = Readonly<{
  citation_id: string;
  evidence_id: string;
  url: string;
  title: string;
  retrieved_at: string;
  locator: string;
}>;

export type ConversationMessage = Readonly<{
  id: UUID;
  conversation_id: UUID;
  role: "USER" | "ASSISTANT";
  status: "COMPLETED" | "FAILED";
  outcome: AssistantOutcome | null;
  sequence: number;
  content: string;
  sensitivity: "PUBLIC" | "INTERNAL" | "PRIVATE" | "SENSITIVE" | "CRITICAL";
  orchestration_id: UUID | null;
  confirmation_request_id: UUID | null;
  memory_id: UUID | null;
  reason_code: string | null;
  citations: readonly ResearchCitation[];
  created_at: string;
}>;

export type AssistantResponse = Readonly<{
  conversation: Conversation;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}>;

export type MemoryRecord = Readonly<{
  id: UUID;
  source_device_id: UUID | null;
  memory_class:
    | "TEMPORARY_CONTEXT"
    | "OPERATIONAL"
    | "PERSISTENT_PREFERENCE"
    | "HISTORICAL_DECISION"
    | "DISCARDABLE";
  content: string;
  summary: string | null;
  subject: string | null;
  source_type: string;
  source_reference: string | null;
  confidence: number;
  importance: number;
  sensitivity: "PUBLIC" | "INTERNAL" | "PRIVATE" | "SENSITIVE" | "CRITICAL";
  status: "ACTIVE" | "ARCHIVED" | "EXPIRED" | "DELETED";
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  archived_at: string | null;
  version: number;
  metadata: Readonly<Record<string, unknown>>;
}>;

export type Permission = Readonly<{
  id: UUID;
  capability: Readonly<{
    key: string;
    name: string;
    description: string;
    category: string;
    default_risk_level: number;
    allowed_actions: readonly string[];
    external_side_effect: boolean;
    financial: boolean;
    data_destructive: boolean;
    privacy_impact: boolean;
    enabled: boolean;
  }>;
  scope: Readonly<Record<string, unknown>>;
  device_id: UUID | null;
  status: "ACTIVE" | "REVOKED" | "EXPIRED";
  confirmation_policy: string;
  auto_execute: boolean;
  grant_source: string;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  reason: string | null;
  last_relevant_use_at: string | null;
}>;

export type Confirmation = Readonly<{
  id: UUID;
  authorization_decision_id: UUID;
  capability_key: string;
  action: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  requested_at: string;
  expires_at: string;
  confirmed_at: string | null;
  rejected_at: string | null;
  consumed_at: string | null;
}>;

export type ApiErrorEnvelope = Readonly<{
  error?: Readonly<{ code?: string; message?: string }>;
  confirmation_id?: UUID | null;
}>;
