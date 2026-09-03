import { useEffect, useState } from "react";

import type { BackendClient } from "./api/client";
import type { Conversation, UUID } from "./api/contracts";
import type { ConversationController } from "./conversation/controller";
import type { SessionController } from "./session/sessionController";
import { ChatView } from "./components/ChatView";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { LoginView } from "./components/LoginView";
import { MemoryView } from "./components/MemoryView";
import { PermissionsView } from "./components/PermissionsView";
import { useConnectivity } from "./state/connectivity";
import { useExternalState } from "./state/useExternalState";

type View = "CHAT" | "MEMORY" | "PERMISSIONS";

function AuthenticatedWorkspace(props: {
  client: BackendClient;
  session: SessionController;
  conversations: ConversationController;
  displayName: string | null;
}) {
  const conversationState = useExternalState(props.conversations);
  const connectivity = useConnectivity();
  const [items, setItems] = useState<readonly Conversation[]>([]);
  const [view, setView] = useState<View>("CHAT");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [listBusy, setListBusy] = useState(true);
  const [shellMessage, setShellMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    props.client
      .listConversations()
      .then((value) => {
        if (active) {
          setItems(value);
          setShellMessage(null);
        }
      })
      .catch(() => {
        if (active)
          setShellMessage("Conversations are temporarily unavailable.");
      })
      .finally(() => {
        if (active) setListBusy(false);
      });
    return () => {
      active = false;
    };
  }, [props.client]);

  const createConversation = async () => {
    if (listBusy) return;
    setListBusy(true);
    try {
      const created = await props.client.createConversation();
      setItems((current) => [created, ...current]);
      setView("CHAT");
      setSidebarOpen(false);
      await props.conversations.select(created);
    } catch {
      setShellMessage("The server did not create a conversation.");
    } finally {
      setListBusy(false);
    }
  };

  const selectConversation = (conversation: Conversation) => {
    setView("CHAT");
    setSidebarOpen(false);
    void props.conversations.select(conversation);
  };

  const confirmation = (id: UUID, decision: "approve" | "reject") =>
    decision === "approve"
      ? props.client.approveConfirmation(id)
      : props.client.rejectConfirmation(id);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <ConversationSidebar
        busy={listBusy}
        conversations={items}
        onClose={() => setSidebarOpen(false)}
        onCreate={() => void createConversation()}
        onSelect={selectConversation}
        open={sidebarOpen}
        selectedId={conversationState.selectedId}
      />
      {sidebarOpen ? (
        <button
          aria-label="Close navigation overlay"
          className="sidebar-scrim"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      ) : null}
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button
              aria-label="Open conversations"
              className="mobile-only icon-button"
              onClick={() => setSidebarOpen(true)}
              type="button"
            >
              ☰
            </button>
            <div aria-hidden="true" className="brand-mark brand-small">
              PA
            </div>
            <div>
              <strong>Personal Assistant</strong>
              <span>{props.displayName ?? "Your private workspace"}</span>
            </div>
          </div>
          <nav aria-label="Workspace sections" className="section-tabs">
            <button
              aria-current={view === "CHAT" ? "page" : undefined}
              onClick={() => setView("CHAT")}
              type="button"
            >
              Chat
            </button>
            <button
              aria-current={view === "MEMORY" ? "page" : undefined}
              onClick={() => setView("MEMORY")}
              type="button"
            >
              Memory
            </button>
            <button
              aria-current={view === "PERMISSIONS" ? "page" : undefined}
              onClick={() => setView("PERMISSIONS")}
              type="button"
            >
              Permissions
            </button>
          </nav>
          <button
            className="quiet-button"
            onClick={() => {
              void props.session.logout().catch(() => undefined);
            }}
            type="button"
          >
            Sign out
          </button>
        </header>
        <div aria-live="polite" className="shell-status">
          {shellMessage}
        </div>
        <main id="main-content">
          {view === "CHAT" ? (
            <ChatView
              online={connectivity === "ONLINE"}
              onConfirmation={confirmation}
              onRetry={() => props.conversations.retry()}
              onSend={(content) =>
                props.conversations.send(content, connectivity === "ONLINE")
              }
              state={conversationState}
            />
          ) : null}
          {view === "MEMORY" ? <MemoryView client={props.client} /> : null}
          {view === "PERMISSIONS" ? (
            <PermissionsView client={props.client} session={props.session} />
          ) : null}
        </main>
      </div>
    </div>
  );
}

export function App(props: {
  client: BackendClient;
  session: SessionController;
  conversations: ConversationController;
}) {
  const sessionState = useExternalState(props.session);
  const signIn = async (email: string, password: string) => {
    await props.session.signIn(email, password);
    const identity = await props.client.currentIdentity();
    props.session.acceptIdentity(identity);
  };

  if (sessionState.status !== "AUTHENTICATED" || !sessionState.identity) {
    return (
      <LoginView
        busy={
          sessionState.status === "SIGNING_IN" ||
          sessionState.status === "VALIDATING"
        }
        message={sessionState.message}
        onSignIn={signIn}
      />
    );
  }

  return (
    <AuthenticatedWorkspace
      client={props.client}
      conversations={props.conversations}
      displayName={sessionState.identity.display_name}
      key={sessionState.identity.user_id}
      session={props.session}
    />
  );
}
