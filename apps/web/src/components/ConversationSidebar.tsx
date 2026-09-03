import type { Conversation, UUID } from "../api/contracts";

function conversationLabel(conversation: Conversation): string {
  const title = conversation.title?.trim();
  return title && title.length > 0 ? title : "Untitled conversation";
}

export function ConversationSidebar(props: {
  conversations: readonly Conversation[];
  selectedId: UUID | null;
  busy: boolean;
  open: boolean;
  onCreate(): void;
  onSelect(conversation: Conversation): void;
  onClose(): void;
}) {
  return (
    <aside
      aria-label="Conversation navigation"
      className={`sidebar ${props.open ? "sidebar-open" : ""}`}
    >
      <div className="sidebar-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h2>Conversations</h2>
        </div>
        <button
          aria-label="Close conversations"
          className="mobile-only icon-button"
          onClick={() => props.onClose()}
          type="button"
        >
          ×
        </button>
      </div>
      <button
        className="new-conversation"
        disabled={props.busy}
        onClick={() => props.onCreate()}
        type="button"
      >
        <span aria-hidden="true">＋</span> New conversation
      </button>
      <nav aria-label="Your conversations" className="conversation-list">
        {props.conversations.length === 0 ? (
          <p className="empty-copy">No conversations yet.</p>
        ) : (
          props.conversations.map((conversation) => (
            <button
              aria-current={
                props.selectedId === conversation.id ? "page" : undefined
              }
              className="conversation-link"
              key={conversation.id}
              onClick={() => props.onSelect(conversation)}
              type="button"
            >
              <span>{conversationLabel(conversation)}</span>
              <time dateTime={conversation.updated_at}>
                {new Intl.DateTimeFormat(undefined, {
                  month: "short",
                  day: "numeric",
                }).format(new Date(conversation.updated_at))}
              </time>
            </button>
          ))
        )}
      </nav>
    </aside>
  );
}
