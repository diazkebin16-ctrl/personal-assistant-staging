import axe from "axe-core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ConversationViewState } from "../../src/conversation/controller";
import { ChatView } from "../../src/components/ChatView";
import { Dialog } from "../../src/components/Dialog";
import { LoginView } from "../../src/components/LoginView";
import { conversation, message } from "../helpers";

describe("web accessibility", () => {
  it("has no automated violations on the login surface", async () => {
    const { container } = render(
      <LoginView
        busy={false}
        message={null}
        onSignIn={() => Promise.resolve()}
      />,
    );
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it("has no automated violations on an active conversation", async () => {
    const state: ConversationViewState = Object.freeze({
      selectedId: conversation.id,
      conversation,
      messages: [message("USER"), message("ASSISTANT")],
      pending: null,
      error: null,
    });
    const { container } = render(
      <ChatView
        online
        onConfirmation={() => Promise.reject(new Error("not applicable"))}
        onRetry={() => Promise.resolve()}
        onSend={() => Promise.resolve()}
        state={state}
      />,
    );
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it("traps focus, closes on Escape and restores prior focus", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    const prior = document.createElement("button");
    prior.textContent = "Open";
    document.body.append(prior);
    prior.focus();
    const { unmount } = render(
      <Dialog onClose={close} title="Confirm">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>,
    );
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(close).toHaveBeenCalledTimes(1);
    unmount();
    expect(prior).toHaveFocus();
    prior.remove();
  });

  it("keeps the composer disabled while offline", () => {
    const state: ConversationViewState = Object.freeze({
      selectedId: conversation.id,
      conversation,
      messages: [],
      pending: null,
      error: null,
    });
    render(
      <ChatView
        online={false}
        onConfirmation={() => Promise.reject(new Error("not applicable"))}
        onRetry={() => Promise.resolve()}
        onSend={() => Promise.resolve()}
        state={state}
      />,
    );
    expect(screen.getByLabelText("Message")).toBeDisabled();
    expect(screen.getByText("Offline")).toBeVisible();
  });
});
