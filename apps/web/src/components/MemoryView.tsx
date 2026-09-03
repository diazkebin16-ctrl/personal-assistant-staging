import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type SyntheticEvent,
} from "react";

import type { BackendClient } from "../api/client";
import type { MemoryRecord } from "../api/contracts";
import { ApiError } from "../api/errors";
import { Dialog } from "./Dialog";

type MemoryClass =
  | "OPERATIONAL"
  | "PERSISTENT_PREFERENCE"
  | "HISTORICAL_DECISION"
  | "DISCARDABLE";

const MEMORY_CLASSES = new Set<MemoryClass>([
  "OPERATIONAL",
  "PERSISTENT_PREFERENCE",
  "HISTORICAL_DECISION",
  "DISCARDABLE",
]);

export function MemoryView(props: { client: BackendClient }) {
  const subjectId = useId();
  const contentId = useId();
  const classId = useId();
  const [records, setRecords] = useState<readonly MemoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [target, setTarget] = useState<MemoryRecord | null>(null);
  const [serverConfirmationId, setServerConfirmationId] = useState<
    string | null
  >(null);
  const [message, setMessage] = useState<string | null>(null);
  const contentRef = useRef<HTMLTextAreaElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setRecords(await props.client.listMemories());
      setMessage(null);
    } catch {
      setMessage("Memory is temporarily unavailable.");
    } finally {
      setLoading(false);
    }
  }, [props.client]);

  useEffect(() => {
    let active = true;
    props.client
      .listMemories()
      .then((value) => {
        if (active) setRecords(value);
      })
      .catch(() => {
        if (active) setMessage("Memory is temporarily unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [props.client]);

  const create = async (
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const rawContent = form.get("content");
    const rawSubject = form.get("subject");
    const rawClass = form.get("memoryClass");
    const content = typeof rawContent === "string" ? rawContent : "";
    const subject = typeof rawSubject === "string" ? rawSubject.trim() : "";
    if (
      typeof rawClass !== "string" ||
      !MEMORY_CLASSES.has(rawClass as MemoryClass)
    ) {
      setMessage("Choose a supported Memory type.");
      return;
    }
    try {
      await props.client.createMemory({
        memoryClass: rawClass as MemoryClass,
        content,
        ...(subject ? { subject } : {}),
      });
      setShowCreate(false);
      await refresh();
    } catch {
      setMessage("The server did not save this memory.");
    }
  };

  const archive = async (memory: MemoryRecord) => {
    try {
      await props.client.archiveMemory(memory);
      await refresh();
    } catch {
      setMessage("The server did not archive this memory.");
    }
  };

  const remove = async () => {
    if (!target) return;
    try {
      if (serverConfirmationId)
        await props.client.approveConfirmation(serverConfirmationId);
      await props.client.deleteMemory(
        target,
        serverConfirmationId ?? undefined,
      );
      setTarget(null);
      setServerConfirmationId(null);
      await refresh();
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.category === "CONFIRMATION_REQUIRED" &&
        error.confirmationId
      ) {
        setServerConfirmationId(error.confirmationId);
      } else {
        setMessage("The server did not delete this memory.");
        setTarget(null);
        setServerConfirmationId(null);
      }
    }
  };

  return (
    <section aria-labelledby="memory-title" className="utility-view">
      <header className="utility-heading">
        <div>
          <p className="eyebrow">User controlled</p>
          <h2 id="memory-title">Memory</h2>
          <p>Only explicit, server-owned Memory records appear here.</p>
        </div>
        <button
          className="primary-button"
          onClick={() => setShowCreate(true)}
          type="button"
        >
          Save memory
        </button>
      </header>
      <div aria-live="polite" className="form-status">
        {message}
      </div>
      {loading ? (
        <p role="status">Loading Memory…</p>
      ) : records.length === 0 ? (
        <div className="empty-card">
          <h3>No active memories</h3>
          <p>Nothing is inferred or saved automatically by this browser.</p>
        </div>
      ) : (
        <div className="memory-grid">
          {records.map((memory) => (
            <article className="memory-card" key={memory.id}>
              <div className="memory-meta">
                <span>
                  {memory.memory_class.replaceAll("_", " ").toLowerCase()}
                </span>
                <span>{memory.sensitivity.toLowerCase()}</span>
              </div>
              <h3>{memory.subject ?? "Saved memory"}</h3>
              <p>{memory.content}</p>
              <div className="card-actions">
                <button onClick={() => void archive(memory)} type="button">
                  Archive
                </button>
                <button
                  className="danger-button"
                  onClick={() => setTarget(memory)}
                  type="button"
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {showCreate ? (
        <Dialog
          initialFocusRef={contentRef}
          onClose={() => setShowCreate(false)}
          title="Save an explicit memory"
        >
          <form
            className="dialog-form"
            onSubmit={(event) => void create(event)}
          >
            <label htmlFor={contentId}>
              What should the assistant remember?
            </label>
            <textarea
              id={contentId}
              maxLength={16_000}
              name="content"
              ref={contentRef}
              required
              rows={5}
            />
            <label htmlFor={subjectId}>Subject (optional)</label>
            <input id={subjectId} maxLength={200} name="subject" />
            <label htmlFor={classId}>Memory type</label>
            <select
              defaultValue="PERSISTENT_PREFERENCE"
              id={classId}
              name="memoryClass"
            >
              <option value="PERSISTENT_PREFERENCE">
                Persistent preference
              </option>
              <option value="OPERATIONAL">Operational context</option>
              <option value="HISTORICAL_DECISION">Historical decision</option>
              <option value="DISCARDABLE">Discardable</option>
            </select>
            <p className="muted">
              The backend decides authorization, provenance and final stored
              state.
            </p>
            <div className="dialog-actions">
              <button onClick={() => setShowCreate(false)} type="button">
                Cancel
              </button>
              <button className="primary-button" type="submit">
                Save on server
              </button>
            </div>
          </form>
        </Dialog>
      ) : null}
      {target ? (
        <Dialog
          onClose={() => {
            setTarget(null);
            setServerConfirmationId(null);
          }}
          title={
            serverConfirmationId
              ? "Server confirmation required"
              : "Delete memory?"
          }
        >
          <p>
            {serverConfirmationId
              ? "The backend requires an unexpired confirmation for this exact deletion. Approval still does not bypass server authorization."
              : `Delete “${target.subject ?? "Saved memory"}”? This request will be evaluated by the backend.`}
          </p>
          <div className="dialog-actions">
            <button
              onClick={() => {
                setTarget(null);
                setServerConfirmationId(null);
              }}
              type="button"
            >
              Cancel
            </button>
            <button
              className="danger-button"
              onClick={() => void remove()}
              type="button"
            >
              {serverConfirmationId
                ? "Approve and request deletion"
                : "Request deletion"}
            </button>
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
