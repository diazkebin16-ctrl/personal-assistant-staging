import { useCallback, useEffect, useState } from "react";

import type { BackendClient } from "../api/client";
import type { Permission } from "../api/contracts";
import type { MfaState, TotpEnrollment } from "../auth/authGateway";
import type { SessionController } from "../session/sessionController";

export function PermissionsView(props: {
  client: BackendClient;
  session: SessionController;
}) {
  const [permissions, setPermissions] = useState<readonly Permission[]>([]);
  const [mfa, setMfa] = useState<MfaState | null>(null);
  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [permissionState, mfaState] = await Promise.all([
      props.client.listPermissions(),
      props.session.getMfaState(),
    ]);
    setPermissions(permissionState);
    setMfa(mfaState);
  }, [props.client, props.session]);

  useEffect(() => {
    let active = true;
    refresh()
      .then(() => {
        if (active) setError(null);
      })
      .catch(() => {
        if (active)
          setError("Permission or authentication state is temporarily unavailable.");
      });
    return () => {
      active = false;
    };
  }, [refresh]);

  const beginEnrollment = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const started = await props.session.enrollTotp();
      setEnrollment(started);
      setMessage(
        "Add the secret below to your authenticator app, then enter its current code.",
      );
    } catch {
      setError("Authenticator setup could not be started.");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    if (busy) return;

    const factorId =
      enrollment?.factorId ?? mfa?.verifiedTotpFactorIds[0] ?? null;

    if (!factorId) {
      setError("No authenticator factor is available.");
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await props.session.verifyTotp(factorId, code);

      // Security boundary: the browser does not declare itself AAL2.
      // The newly issued JWT must be accepted and mapped by the backend.
      const identity = await props.client.currentIdentity();
      if (identity.authentication_level !== "AAL2") {
        throw new Error("Backend did not confirm AAL2.");
      }
      props.session.acceptIdentity(identity);

      setEnrollment(null);
      setCode("");
      await refresh();
      setMessage("Stronger authentication verified by the server.");
    } catch {
      setError("The authenticator code was not accepted or AAL2 was not confirmed.");
    } finally {
      setBusy(false);
    }
  };

  const enableMemory = async () => {
    if (busy || mfa?.currentLevel !== "aal2") return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await props.client.grantMemoryPermission("memory.read", ["read"]);
      await props.client.grantMemoryPermission("memory.write", [
        "create",
        "update",
        "archive",
        "delete",
      ]);
      await refresh();
      setMessage("Memory access was explicitly granted by the authenticated user.");
    } catch {
      setError(
        "Memory permissions were not granted. The server kept the operation denied.",
      );
    } finally {
      setBusy(false);
    }
  };

  const activeKeys = new Set(
    permissions
      .filter((permission) => permission.status === "ACTIVE")
      .map((permission) => permission.capability.key),
  );
  const memoryReady =
    activeKeys.has("memory.read") && activeKeys.has("memory.write");

  return (
    <section aria-labelledby="permissions-title" className="utility-view">
      <header className="utility-heading">
        <div>
          <p className="eyebrow">Server authority</p>
          <h2 id="permissions-title">Assistant permissions</h2>
          <p>
            Permissions remain server-owned. Sensitive account-control changes
            require stronger authentication.
          </p>
        </div>
      </header>

      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}

      <article className="permission-card">
        <div>
          <h3>Strong authentication</h3>
          <p>
            Current level: {mfa?.currentLevel ?? "checking"} · Next level:{" "}
            {mfa?.nextLevel ?? "checking"}
          </p>
        </div>

        {mfa?.currentLevel !== "aal2" &&
        mfa?.verifiedTotpFactorIds.length === 0 &&
        !enrollment ? (
          <button
            className="primary-button"
            disabled={busy}
            onClick={() => void beginEnrollment()}
            type="button"
          >
            Set up authenticator
          </button>
        ) : null}

        {enrollment ? (
          <div>
            <p>
              Authenticator secret: <code>{enrollment.secret}</code>
            </p>
            <p>
              Keep this secret private. Add it manually to an authenticator app.
            </p>
          </div>
        ) : null}

        {mfa?.currentLevel !== "aal2" &&
        (enrollment || mfa?.verifiedTotpFactorIds.length) ? (
          <div>
            <label>
              Authenticator code
              <input
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={8}
                onChange={(event) => setCode(event.target.value)}
                value={code}
              />
            </label>
            <button
              className="primary-button"
              disabled={busy || !/^[0-9]{6,8}$/.test(code.trim())}
              onClick={() => void verify()}
              type="button"
            >
              Verify stronger authentication
            </button>
          </div>
        ) : null}

        {mfa?.currentLevel === "aal2" && !memoryReady ? (
          <button
            className="primary-button"
            disabled={busy}
            onClick={() => void enableMemory()}
            type="button"
          >
            Enable memory access
          </button>
        ) : null}

        {memoryReady ? (
          <p role="status">
            Memory read and write permissions are active.
          </p>
        ) : null}
      </article>

      <div className="permission-list">
        {permissions.length === 0 && !error ? (
          <p role="status">No permission grants are available.</p>
        ) : null}

        {permissions.map((permission) => (
          <article className="permission-card" key={permission.id}>
            <div>
              <h3>{permission.capability.name}</h3>
              <p>{permission.capability.description}</p>
            </div>
            <span
              className={`permission-status status-${permission.status.toLowerCase()}`}
            >
              {permission.status.toLowerCase()}
            </span>
            <dl>
              <div>
                <dt>Confirmation</dt>
                <dd>
                  {permission.confirmation_policy
                    .toLowerCase()
                    .replaceAll("_", " ")}
                </dd>
              </div>
              <div>
                <dt>External side effect</dt>
                <dd>
                  {permission.capability.external_side_effect
                    ? "Possible — server controlled"
                    : "No"}
                </dd>
              </div>
              <div>
                <dt>Financial</dt>
                <dd>
                  {permission.capability.financial
                    ? "Execution always prohibited"
                    : "No"}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
