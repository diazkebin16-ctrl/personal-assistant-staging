import { expect, test, type Page, type Route } from "@playwright/test";

const USER_ID = "11111111-1111-4111-8111-111111111111";
const CONVERSATION_ID = "33333333-3333-4333-8333-333333333333";
const CREATED_CONVERSATION_ID = "77777777-7777-4777-8777-777777777777";
const CONFIRMATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const messagePostCounts = new WeakMap<Page, () => number>();
const ACCESS_TOKEN = [
  Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString(
    "base64url",
  ),
  Buffer.from(
    JSON.stringify({
      sub: USER_ID,
      role: "authenticated",
      aud: "authenticated",
      exp: 2_000_000_000,
    }),
  ).toString("base64url"),
  "controlled-signature",
].join(".");

const conversation = {
  id: CONVERSATION_ID,
  device_id: null,
  title: "Project notes",
  version: 1,
  created_at: "2026-09-02T12:00:00Z",
  updated_at: "2026-09-02T12:00:00Z",
  last_message_at: null,
};

function message(
  role: "USER" | "ASSISTANT",
  conversationId: string,
  content: string,
) {
  return {
    id:
      role === "USER"
        ? "44444444-4444-4444-8444-444444444444"
        : "55555555-5555-4555-8555-555555555555",
    conversation_id: conversationId,
    role,
    status: "COMPLETED",
    outcome:
      role === "ASSISTANT" && content.startsWith("Approval")
        ? "ACTION_WAITING_CONFIRMATION"
        : role === "ASSISTANT"
          ? "ANSWERED"
          : null,
    sequence: role === "USER" ? 1 : 2,
    content,
    sensitivity: "PRIVATE",
    orchestration_id: null,
    confirmation_request_id: content.startsWith("Approval")
      ? CONFIRMATION_ID
      : null,
    memory_id: null,
    reason_code: null,
    citations: [],
    created_at: "2026-09-02T12:00:01Z",
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Origin": "http://127.0.0.1:4173",
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers":
        "apikey, authorization, content-type, x-client-info, x-supabase-api-version",
    },
    body: JSON.stringify(body),
  });
}

async function installControlledBackend(page: Page) {
  let messagePosts = 0;
  messagePostCounts.set(page, () => messagePosts);
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (
      url.origin === "http://127.0.0.1:4173" &&
      url.pathname.startsWith("/auth/v1/")
    ) {
      if (request.method() === "OPTIONS") {
        await route.fulfill({
          status: 204,
          headers: {
            "Access-Control-Allow-Origin": "http://127.0.0.1:4173",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers":
              "apikey, authorization, content-type, x-client-info, x-supabase-api-version",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          },
        });
        return;
      }
      if (url.pathname === "/auth/v1/token") {
        await json(route, {
          access_token: ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 3600,
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          refresh_token: "controlled-memory-refresh-token",
          user: {
            id: USER_ID,
            aud: "authenticated",
            role: "authenticated",
            email: "avery@example.com",
            app_metadata: { provider: "email", providers: ["email"] },
            user_metadata: {},
            created_at: "2026-09-02T12:00:00Z",
          },
        });
        return;
      }
      if (url.pathname === "/auth/v1/logout") {
        await route.fulfill({ status: 204 });
        return;
      }
    }
    if (
      url.origin === "http://127.0.0.1:4173" &&
      url.pathname.startsWith("/api/v1/")
    ) {
      if (url.pathname === "/api/v1/me") {
        await json(route, {
          user_id: USER_ID,
          display_name: "Avery",
          device_id: null,
          authenticated: true,
          authentication_level: "aal1",
        });
        return;
      }
      if (
        url.pathname === "/api/v1/conversations" &&
        request.method() === "GET"
      ) {
        await json(route, [conversation]);
        return;
      }
      if (
        url.pathname === "/api/v1/conversations" &&
        request.method() === "POST"
      ) {
        await json(route, {
          ...conversation,
          id: CREATED_CONVERSATION_ID,
          title: null,
        });
        return;
      }
      const messageRoute = /^\/api\/v1\/conversations\/([^/]+)\/messages$/.exec(
        url.pathname,
      );
      if (messageRoute && request.method() === "GET") {
        await json(route, []);
        return;
      }
      if (messageRoute && request.method() === "POST") {
        messagePosts += 1;
        const conversationId = messageRoute[1] ?? CONVERSATION_ID;
        const body = request.postDataJSON() as { content?: unknown };
        const userContent =
          typeof body.content === "string" ? body.content : "Message";
        const actionRequest = userContent.toLowerCase().includes("schedule");
        const assistantContent = actionRequest
          ? "Approval is required before this prepared action can proceed."
          : "Hello from the certified backend.";
        await json(route, {
          conversation: { ...conversation, id: conversationId, version: 2 },
          user_message: message("USER", conversationId, userContent),
          assistant_message: message(
            "ASSISTANT",
            conversationId,
            assistantContent,
          ),
        });
        return;
      }
      if (
        url.pathname === `/api/v1/confirmations/${CONFIRMATION_ID}/approve` &&
        request.method() === "POST"
      ) {
        await json(route, {
          id: CONFIRMATION_ID,
          authorization_decision_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          capability_key: "calendar.create",
          action: "CREATE",
          status: "APPROVED",
          requested_at: "2026-09-02T12:00:00Z",
          expires_at: "2026-09-02T12:05:00Z",
          confirmed_at: "2026-09-02T12:01:00Z",
          rejected_at: null,
          consumed_at: null,
        });
        return;
      }
      if (url.pathname === "/api/v1/memories" && request.method() === "GET") {
        await json(route, []);
        return;
      }
      if (
        url.pathname === "/api/v1/permissions" &&
        request.method() === "GET"
      ) {
        await json(route, []);
        return;
      }
      await json(route, { error: { code: "NOT_FOUND" } }, 404);
      return;
    }
    await route.continue();
  });
}

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill("avery@example.com");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Project notes")).toBeVisible();
}

test.beforeEach(async ({ page }) => installControlledBackend(page));

test("sign in, open conversation, and send through the certified API path", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(
    page.getByRole("heading", { name: "Untitled conversation" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("Hello");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Hello from the certified backend."),
  ).toBeVisible();
  await expect(page.getByText("Completed")).toBeVisible();
});

test("action request remains confirmation-only and never claims execution", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Project notes/ }).click();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("Schedule a meeting");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Confirmation required")).toBeVisible();
  await page.getByRole("button", { name: "Approve on server" }).click();
  await expect(
    page.getByText(/Server confirmation: approved.*No action was executed/),
  ).toBeVisible();
});

test("offline state blocks sends and reconnect sends exactly once", async ({
  context,
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Project notes/ }).click();
  await context.setOffline(true);
  await expect(page.getByText("Offline")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeDisabled();
  await context.setOffline(false);
  await expect(page.getByText("Connected")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("Recovered safely");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Hello from the certified backend."),
  ).toBeVisible();
  expect(messagePostCounts.get(page)?.()).toBe(1);
});

test("mobile navigation keeps Chat, Memory, and Permissions available", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await expect(
    page.getByRole("button", { name: "Chat", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Memory", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Permissions", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Memory", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  await page.getByRole("button", { name: "Permissions", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Assistant permissions" }),
  ).toBeVisible();
});

test("logout removes account-bound UI", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await expect(page.getByText("Project notes")).toHaveCount(0);
});
