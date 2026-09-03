import { useEffect, useId, useRef, useState, type SyntheticEvent } from "react";

import type { Confirmation, ConversationMessage } from "../api/contracts";
import type { ErrorCategory } from "../api/errors";
import type { ConversationViewState } from "../conversation/controller";
import { presentAssistantMessage } from "../conversation/truth";

export function safeCitationUrl(raw: string): string | null {
  try {
    const parsed = new URL(raw);
    if (
      !["https:", "http:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password
    )
      return null;
    const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
    if (
      host === "localhost" ||
      host.endsWith(".localhost") ||
      host.endsWith(".local") ||
      host.endsWith(".internal") ||
      host.startsWith("127.") ||
      host.startsWith("10.") ||
      host.startsWith("192.168.") ||
      host.startsWith("169.254.") ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
      host === "::1" ||
      /^\[(?:fc|fd|fe[89ab])/i.test(host) ||
      /^\[::ffff:(?:127\.|10\.|192\.168\.|169\.254\.)/i.test(host)
    )
      return null;
    return parsed.href;
  } catch {
    return null;
  }
}

function ConfirmationActions(props: {
  confirmationId: string;
  onDecision(id: string, decision: "approve" | "reject"): Promise<Confirmation>;
}) {
  const [status, setStatus] = useState<Confirmation["status"] | "BUSY" | null>(
    null,
  );
  const decide = async (decision: "approve" | "reject") => {
    setStatus("BUSY");
    try {
      const result = await props.onDecision(props.confirmationId, decision);
      setStatus(result.status);
    } catch {
      setStatus(null);
    }
  };
  if (status && status !== "BUSY") {
    return (
      <p className="confirmation-result">
        Server confirmation: {status.toLowerCase()}. No action was executed by
        the browser.
      </p>
    );
  }
  return (
    <div
      aria-label="Server confirmation controls"
      className="confirmation-actions"
    >
      <button
        disabled={status === "BUSY"}
        onClick={() => void decide("reject")}
        type="button"
      >
        Reject
      </button>
      <button
        className="primary-button"
        disabled={status === "BUSY"}
        onClick={() => void decide("approve")}
        type="button"
      >
        Approve on server
      </button>
    </div>
  );
}

function MessageItem(props: {
  message: ConversationMessage;
  onConfirmation(
    id: string,
    decision: "approve" | "reject",
  ): Promise<Confirmation>;
}) {
  if (props.message.role === "USER") {
    return (
      <article aria-label="You" className="message message-user">
        <span className="message-author">You</span>
        <p>{props.message.content}</p>
      </article>
    );
  }
  const presentation = presentAssistantMessage(props.message);
  return (
    <article
      aria-label={`Assistant: ${presentation.label}`}
      className={`message message-assistant tone-${presentation.tone}`}
    >
      <div className="message-meta">
        <span className="message-author">Assistant</span>
        <span className="outcome-label">{presentation.label}</span>
      </div>
      <p>{presentation.content}</p>
      {props.message.citations.length ? (
        <ol aria-label="Research citations" className="research-citations">
          {props.message.citations.map((citation) => {
            const href = safeCitationUrl(citation.url);
            return (
              <li key={citation.citation_id}>
                {href ? (
                  <a href={href} rel="noopener noreferrer" target="_blank">
                    {citation.title}
                  </a>
                ) : (
                  <span>{citation.title}</span>
                )}
                <small>
                  {href ? new URL(href).hostname : "Blocked link"} · retrieved{" "}
                  {new Date(citation.retrieved_at).toLocaleDateString()}
                </small>
              </li>
            );
          })}
        </ol>
      ) : null}
      {presentation.confirmationId ? (
        <ConfirmationActions
          confirmationId={presentation.confirmationId}
          onDecision={(id, decision) => props.onConfirmation(id, decision)}
        />
      ) : null}
    </article>
  );
}

const ERROR_LABELS: Record<ErrorCategory, string> = {
  AUTH_REQUIRED: "Authentication required",
  FORBIDDEN: "Denied",
  VALIDATION_ERROR: "Check your message",
  NETWORK_OFFLINE: "Offline",
  TIMEOUT: "Timed out",
  SERVER_UNAVAILABLE: "Service unavailable",
  CONFLICT: "Conversation changed",
  PERMISSION_REQUIRED: "Permission required",
  CONFIRMATION_REQUIRED: "Confirmation required",
  SAFE_MODE: "Safe Mode",
  UNSUPPORTED: "Unsupported",
  INTERNAL_ERROR: "Unable to send",
};

export function ChatView(props: {
  state: ConversationViewState;
  online: boolean;
  onSend(content: string): Promise<unknown>;
  onRetry(): Promise<unknown>;
  onConfirmation(
    id: string,
    decision: "approve" | "reject",
  ): Promise<Confirmation>;
}) {
  const editorId = useId();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [props.state.messages.length, sending]);

  const submit = async (
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) => {
    event.preventDefault();
    if (!draft.trim() || sending || !props.online) return;
    setSending(true);
    try {
      await props.onSend(draft);
      setDraft("");
      editorRef.current?.focus();
    } catch {
      // The classified state is rendered below and the draft remains available.
    } finally {
      setSending(false);
    }
  };

  if (!props.state.conversation) {
    return (
      <section aria-labelledby="empty-chat-title" className="chat-empty">
        <div aria-hidden="true" className="empty-orb" />
        <h2 id="empty-chat-title">A quiet place to think</h2>
        <p>
          Select a conversation or create a new one. The server remains the
          source of truth.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Conversation" className="chat-panel">
      <header className="chat-heading">
        <div>
          <p className="eyebrow">Conversation</p>
          <h2>{props.state.conversation.title ?? "Untitled conversation"}</h2>
        </div>
        <span
          className={`connection-pill ${props.online ? "online" : "offline"}`}
        >
          <span aria-hidden="true" /> {props.online ? "Connected" : "Offline"}
        </span>
      </header>
      <div
        aria-live="polite"
        aria-relevant="additions"
        className="message-stream"
      >
        {props.state.messages.length === 0 ? (
          <div className="conversation-intro">
            <p className="eyebrow">Ready when you are</p>
            <h3>What would you like to work through?</h3>
            <p>
              Responses, permissions, confirmations and denials are shown
              exactly as returned by the server.
            </p>
          </div>
        ) : (
          props.state.messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              onConfirmation={(id, decision) =>
                props.onConfirmation(id, decision)
              }
            />
          ))
        )}
        {sending ? (
          <div
            aria-label="Waiting for assistant"
            className="typing-state"
            role="status"
          >
            <span /> <span /> <span />
          </div>
        ) : null}
        <div ref={endRef} />
      </div>
      {props.state.error ? (
        <div className="error-banner" role="alert">
          <div>
            <strong>{ERROR_LABELS[props.state.error.category]}</strong>
            <p>{props.state.error.message}</p>
          </div>
          {props.state.pending ? (
            <button onClick={() => void props.onRetry()} type="button">
              Retry safely
            </button>
          ) : null}
        </div>
      ) : null}
      <form className="composer" onSubmit={(event) => void submit(event)}>
        <label className="sr-only" htmlFor={editorId}>
          Message
        </label>
        <textarea
          disabled={!props.online}
          id={editorId}
          maxLength={50_000}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={
            props.online ? "Message your assistant…" : "Reconnect to send"
          }
          ref={editorRef}
          rows={1}
          value={draft}
        />
        <button
          aria-label="Send message"
          className="send-button"
          disabled={!draft.trim() || sending || !props.online}
          type="submit"
        >
          <span aria-hidden="true">↑</span>
        </button>
      </form>
      <p className="composer-note">
        Enter to send · Shift + Enter for a new line · No browser-side execution
      </p>
    </section>
  );
}
