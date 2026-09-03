import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

export function Dialog(props: {
  title: string;
  children: ReactNode;
  onClose(): void;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}): ReactNode {
  const panel = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    previousFocus.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const target =
      props.initialFocusRef?.current ??
      panel.current?.querySelector<HTMLElement>(
        "button, input, textarea, select",
      );
    target?.focus();
    return () => previousFocus.current?.focus();
  }, [props.initialFocusRef]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      props.onClose();
      return;
    }
    if (event.key !== "Tab" || !panel.current) return;
    const focusable = [
      ...panel.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ),
    ];
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first && last) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last && first) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation">
      <div
        aria-labelledby="dialog-title"
        aria-modal="true"
        className="dialog-panel"
        onKeyDown={onKeyDown}
        ref={panel}
        role="dialog"
      >
        <div className="dialog-heading">
          <h2 id="dialog-title">{props.title}</h2>
          <button
            aria-label="Close dialog"
            className="icon-button"
            onClick={() => props.onClose()}
            type="button"
          >
            ×
          </button>
        </div>
        {props.children}
      </div>
    </div>
  );
}
