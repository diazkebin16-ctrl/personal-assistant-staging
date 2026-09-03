import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ConversationViewState } from "../conversation/controller";
import { conversation, message } from "../../tests/helpers";
import { ChatView, safeCitationUrl } from "./ChatView";

describe("research citation safety", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,attack",
    "file:///etc/passwd",
    "https://user:pass@example.com/a",
    "http://localhost/a",
    "http://127.0.0.1/a",
    "http://10.0.0.1/a",
    "http://172.20.0.1/a",
    "http://192.168.1.1/a",
    "http://169.254.169.254/a",
    "https://service.internal/a",
    "https://printer.local/a",
  ])("blocks unsafe citation URL %s", (url) => {
    expect(safeCitationUrl(url)).toBeNull();
  });

  it.each([
    ["https://example.com/report", "https://example.com/report"],
    ["http://example.com/a", "http://example.com/a"],
  ])("accepts public HTTP(S) URL %s", (url, prefix) => {
    expect(safeCitationUrl(url)).toBe(prefix);
  });

  it("renders server citations as isolated external links", () => {
    const assistant = message("ASSISTANT", {
      outcome: "RESEARCH_ANSWERED",
      content: "Grounded result [cit_0123456789abcdef]",
      citations: [
        {
          citation_id: "cit_0123456789abcdef",
          evidence_id: "ev_0123456789abcdef",
          url: "https://example.com/report",
          title: "Public report",
          retrieved_at: "2026-09-02T12:00:00Z",
          locator: "passage-1",
        },
      ],
    });
    const state: ConversationViewState = Object.freeze({
      selectedId: conversation.id,
      conversation,
      messages: [assistant],
      pending: null,
      error: null,
    });
    render(
      <ChatView
        online
        onConfirmation={() => Promise.reject(new Error("not applicable"))}
        onRetry={() => Promise.resolve()}
        onSend={() => Promise.resolve()}
        state={state}
      />,
    );
    const link = screen.getByRole("link", { name: "Public report" });
    expect(link).toHaveAttribute("href", "https://example.com/report");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByLabelText("Research citations")).toBeVisible();
  });

  it("never makes an unsafe citation clickable", () => {
    const assistant = message("ASSISTANT", {
      outcome: "RESEARCH_ANSWERED",
      citations: [
        {
          citation_id: "cit_0123456789abcdef",
          evidence_id: "ev_0123456789abcdef",
          url: "javascript:alert(1)",
          title: "Blocked source",
          retrieved_at: "2026-09-02T12:00:00Z",
          locator: "passage-1",
        },
      ],
    });
    const state: ConversationViewState = Object.freeze({
      selectedId: conversation.id,
      conversation,
      messages: [assistant],
      pending: null,
      error: null,
    });
    render(
      <ChatView
        online
        onConfirmation={() => Promise.reject(new Error("not applicable"))}
        onRetry={() => Promise.resolve()}
        onSend={() => Promise.resolve()}
        state={state}
      />,
    );
    expect(screen.queryByRole("link", { name: "Blocked source" })).toBeNull();
    expect(screen.getByText("Blocked link", { exact: false })).toBeVisible();
  });
});
