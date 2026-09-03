import { describe, expect, it, vi } from "vitest";

import {
  FakeAuthGateway,
  FakeSessionChannel,
  OTHER_USER_ID,
  identity,
} from "../../tests/helpers";
import { SessionController } from "./sessionController";

describe("session lifecycle", () => {
  it("does not become authenticated before backend identity validation", async () => {
    const controller = new SessionController(new FakeAuthGateway(), {
      channel: new FakeSessionChannel(),
    });
    await controller.signIn("user@example.com", "password");
    expect(controller.state.status).toBe("VALIDATING");
    controller.acceptIdentity(identity);
    expect(controller.state.status).toBe("AUTHENTICATED");
    controller.dispose();
  });

  it("rejects a forged or mismatched user identity", async () => {
    const clear = vi.fn();
    const controller = new SessionController(new FakeAuthGateway(), {
      channel: new FakeSessionChannel(),
      onClear: clear,
    });
    await controller.signIn("user@example.com", "password");
    expect(() =>
      controller.acceptIdentity({ ...identity, auth_user_id: OTHER_USER_ID }),
    ).toThrow("did not match");
    expect(controller.state.status).toBe("EXPIRED");
    expect(clear).toHaveBeenCalled();
    controller.dispose();
  });

  it("clears account state and broadcasts logout", async () => {
    const clear = vi.fn();
    const channel = new FakeSessionChannel();
    const controller = new SessionController(new FakeAuthGateway(), {
      channel,
      onClear: clear,
    });
    await controller.signIn("user@example.com", "password");
    controller.acceptIdentity(identity);
    await controller.logout();
    expect(controller.state).toMatchObject({
      status: "SIGNED_OUT",
      identity: null,
    });
    expect(clear).toHaveBeenCalled();
    expect(channel.logoutPosts).toBe(1);
    controller.dispose();
  });

  it("clears local state even when provider logout fails", async () => {
    const auth = new FakeAuthGateway();
    auth.failSignOut = true;
    const clear = vi.fn();
    const controller = new SessionController(auth, {
      channel: new FakeSessionChannel(),
      onClear: clear,
    });
    await expect(controller.logout()).rejects.toThrow(
      "local session was cleared",
    );
    expect(controller.state.status).toBe("SIGNED_OUT");
    expect(clear).toHaveBeenCalled();
    controller.dispose();
  });

  it("expires without retrying a stale session", () => {
    const clear = vi.fn();
    const controller = new SessionController(new FakeAuthGateway(), {
      channel: new FakeSessionChannel(),
      onClear: clear,
    });
    controller.expire();
    expect(controller.state).toMatchObject({
      status: "EXPIRED",
      identity: null,
    });
    expect(clear).toHaveBeenCalledTimes(1);
    controller.dispose();
  });

  it("propagates refresh only in memory", async () => {
    const auth = new FakeAuthGateway();
    const controller = new SessionController(auth, {
      channel: new FakeSessionChannel(),
    });
    await controller.signIn("user@example.com", "password");
    auth.emit("TOKEN_REFRESHED", {
      accessToken: "refreshed-memory-token",
      expiresAt: 2_000_000_001,
      subject: identity.user_id,
    });
    await expect(controller.getToken()).resolves.toBe("refreshed-memory-token");
    controller.dispose();
  });

  it("updates only the in-memory token after TOTP verification", async () => {
    const auth = new FakeAuthGateway();
    const controller = new SessionController(auth, {
      channel: new FakeSessionChannel(),
    });

    await controller.signIn("user@example.com", "password");
    controller.acceptIdentity(identity);

    const before = controller.state;

    await controller.verifyTotp("factor-test", "123456");

    expect(controller.state).toEqual(before);
    await expect(controller.getToken()).resolves.toBe("memory-only-token");

    controller.dispose();
  });

  it("responds to multi-tab logout without rebroadcast loops", async () => {
    const auth = new FakeAuthGateway();
    const channel = new FakeSessionChannel();
    const clear = vi.fn();
    const controller = new SessionController(auth, { channel, onClear: clear });
    channel.remoteLogout();
    await vi.waitFor(() => expect(auth.signOutCalls).toBe(1));
    expect(channel.logoutPosts).toBe(0);
    expect(controller.state.status).toBe("SIGNED_OUT");
    controller.dispose();
  });

  it("disposes subscriptions and channel state", () => {
    const channel = new FakeSessionChannel();
    const controller = new SessionController(new FakeAuthGateway(), {
      channel,
    });
    controller.dispose();
    expect(channel.closed).toBe(true);
  });
});
