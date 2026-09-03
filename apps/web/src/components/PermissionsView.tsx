import { useEffect, useState } from "react";

import type { BackendClient } from "../api/client";
import type { Permission } from "../api/contracts";

export function PermissionsView(props: { client: BackendClient }) {
  const [permissions, setPermissions] = useState<readonly Permission[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    props.client
      .listPermissions()
      .then(setPermissions)
      .catch(() => setError("Permission state is temporarily unavailable."));
  }, [props.client]);
  return (
    <section aria-labelledby="permissions-title" className="utility-view">
      <header className="utility-heading">
        <div>
          <p className="eyebrow">Server authority</p>
          <h2 id="permissions-title">Assistant permissions</h2>
          <p>
            This read-only view never grants, expands or interprets permission.
          </p>
        </div>
      </header>
      {error ? <p role="alert">{error}</p> : null}
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
