import { useEffect, useRef, useState, type ReactNode } from 'react';

type DropdownProps = {
  label: ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: 'left' | 'right';
  active?: boolean;
};

/**
 * Minimal, dependency-free dropdown/popover. Closes on outside click, Escape,
 * or when the caller invokes the `close` callback passed to a function-form
 * `children` (used for one-shot actions; filter/checkbox content should pass
 * plain ReactNode so it stays open across multiple selections).
 */
export default function Dropdown({ label, children, align = 'left', active = false }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="dropdown" ref={containerRef}>
      <button
        type="button"
        className={`dropdown-trigger ${open ? 'open' : ''} ${active ? 'has-value' : ''}`}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="dropdown-caret" aria-hidden="true" />
      </button>
      {open ? (
        <div
          className={`dropdown-panel ${align === 'right' ? 'align-right' : ''}`}
          onClick={(event) => event.stopPropagation()}
        >
          {typeof children === 'function' ? children(() => setOpen(false)) : children}
        </div>
      ) : null}
    </div>
  );
}
