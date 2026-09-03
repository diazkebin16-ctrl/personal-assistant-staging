import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../../src/App";
import { BackendClient } from "../../src/api/client";
import type { MemoryRecord, Permission } from "../../src/api/contracts";
import { ConversationController } from "../../src/conversation/controller";
import { SessionController } from "../../src/session/sessionController";
import {
  FakeAuthGateway,
  FakeSessionChannel,
  assistantResponse,
  conversation,
  identity,
  jsonResponse,
} from "../helpers";

const memory: MemoryRecord = Object.freeze({
  id: "88888888-8888-4888-8888-888888888888",
  source_device_id: null,
  memory_class: "PERSISTENT_PREFERENCE",
  content: "Use concise answers",
  summary: null,
  subject: "Style",
  source_type: "USER_EXPLICIT",
  source_reference: null,
  confidence: 1,
  importance: 0.5,
  sensitivity: "PRIVATE",
  status: "ACTIVE",
  created_at: "2026-09-02T12:00:00Z",
  updated_at: "2026-09-02T12:00:00Z",
  expires_at: null,
  archived_at: null,
  version: 1,
  metadata: {},
});

const permission: Permission = Object.freeze({
  id: "99999999-9999-4999-8999-999999999999",
  capability: {
    key: "calendar.read",
    name: "Read calendar",
    description: "Read calendar events",
    category: "READ",
    default_risk_level: 1,
    allowed_actions: ["READ"],
    external_side_effect: false,
    financial: false,
    data_destructive: false,
    privacy_impact: true,
    enabled: true,
  },
  scope: {},
  device_id: null,
  status: "ACTIVE",
  confirmation_policy: "NONE",
  auto_execute: false,
  grant_source: "USER",
  granted_at: "2026-09-02T12:00:00Z",
  expires_at: null,
  revoked_at: null,
  reason: null,
  last_relevant_use_at: null,
});

function requestDetails(input: RequestInfo | URL, init?: RequestInit) {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
  const method =
    init?.method ?? (input instanceof Request ? input.method : "GET");
  return { url, method };
}

function createHarness() {
  const auth = new FakeAuthGateway();
  const channel = new FakeSessionChannel();
  const fetcher = vi.fn<typeof fetch>((input, init) => {
    const { url, method } = requestDetails(input, init);
    if (url.endsWith("/me")) return Promise.resolve(jsonResponse(identity));
    if (url.includes("/conversations?") && method === "GET")
      return Promise.resolve(jsonResponse([conversation]));
    if (
      url.includes(`/conversations/${conversation.id}/messages`) &&
      method === "GET"
    )
      return Promise.resolve(jsonResponse([]));
    if (
      url.includes(`/conversations/${conversation.id}/messages`) &&
      method === "POST"
    )
      return Promise.resolve(jsonResponse(assistantResponse()));
    if (url.includes("/memories?") && method === "GET")
      return Promise.resolve(jsonResponse([memory]));
    if (url.endsWith("/permissions") && method === "GET")
      return Promise.resolve(jsonResponse([permission]));
    return Promise.resolve(jsonResponse({ error: { code: "NOT_FOUND" } }, 404));
  });
  const session = new SessionController(auth, {
    channel,
    onClear: () => {
      client.abortAll();
      conversations.clear();
    },
  });
  const client = new BackendClient({
    baseUrl: "/api/v1",
    tokenProvider: () => session.getToken(),
    fetcher,
    onAuthenticationRequired: () => session.expire(),
  });
  const conversations = new ConversationController(client);
  return { auth, channel, client, conversations, fetcher, session };
}

async function signIn(harness: ReturnType<typeof createHarness>) {
  const user = userEvent.setup();
  render(
    <App
      client={harness.client}
      conversations={harness.conversations}
      session={harness.session}
    />,
  );
  await user.type(screen.getByLabelText("Email"), "avery@example.com");
  await user.type(screen.getByLabelText("Password"), "correct-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByText("Project notes");
  return user;
}

describe("web client integration", () => {
  it("authenticates, opens a conversation and renders the server outcome", async () => {
    const harness = createHarness();
    const user = await signIn(harness);
    await user.click(screen.getByRole("button", { name: /Project notes/ }));
    await screen.findByRole("heading", { name: "Project notes" });
    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Hello, Avery.")).toBeVisible();
    expect(screen.getByText("Completed")).toBeVisible();
    harness.session.dispose();
  });

  it("shows only server-owned Memory records", async () => {
    const harness = createHarness();
    const user = await signIn(harness);
    await user.click(screen.getByRole("button", { name: "Memory" }));
    const card = await screen.findByRole("heading", { name: "Style" });
    expect(card).toBeVisible();
    expect(screen.getByText("Use concise answers")).toBeVisible();
    expect(screen.getByText("private")).toBeVisible();
    harness.session.dispose();
  });

  it("renders permissions as read-only server authority", async () => {
    const harness = createHarness();
    const user = await signIn(harness);
    await user.click(screen.getByRole("button", { name: "Permissions" }));
    const card = (
      await screen.findByRole("heading", { name: "Read calendar" })
    ).closest("article");
    if (!card) throw new Error("Permission card was not rendered.");
    expect(within(card).getByText("active")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /grant/i }),
    ).not.toBeInTheDocument();
    harness.session.dispose();
  });

  it("clears the authenticated shell after logout", async () => {
    const harness = createHarness();
    const user = await signIn(harness);
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    expect(screen.queryByText("Project notes")).not.toBeInTheDocument();
    expect(harness.channel.logoutPosts).toBe(1);
    harness.session.dispose();
  });
});
