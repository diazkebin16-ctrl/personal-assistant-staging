import { useId, useState, type SyntheticEvent } from "react";

export function LoginView(props: {
  busy: boolean;
  message: string | null;
  onSignIn(email: string, password: string): Promise<void>;
}) {
  const emailId = useId();
  const passwordId = useId();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = async (
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) => {
    event.preventDefault();
    setLocalError(null);
    try {
      await props.onSignIn(email, password);
      setPassword("");
    } catch {
      setLocalError("Check your credentials and try again.");
    }
  };

  return (
    <main className="auth-shell">
      <section aria-labelledby="welcome-title" className="auth-card">
        <div aria-hidden="true" className="brand-mark">
          PA
        </div>
        <p className="eyebrow">Personal Assistant</p>
        <h1 id="welcome-title">Welcome back</h1>
        <p className="muted">
          Sign in to continue to your conversations and saved memory.
        </p>
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <label htmlFor={emailId}>Email</label>
          <input
            autoComplete="username"
            id={emailId}
            inputMode="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor={passwordId}>Password</label>
          <input
            autoComplete="current-password"
            id={passwordId}
            minLength={8}
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          <div aria-live="polite" className="form-status">
            {localError ?? props.message}
          </div>
          <button
            className="primary-button"
            disabled={props.busy}
            type="submit"
          >
            {props.busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="privacy-note">
          Credentials are sent only to Supabase Auth. Tokens are kept in memory
          and cleared on logout.
        </p>
      </section>
    </main>
  );
}
