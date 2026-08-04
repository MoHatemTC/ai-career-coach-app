import { useId, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/cn";

/**
 * Replaces Streamlit's `st.multiselect(accept_new_options=True)` for skills:
 * remove what the parser got wrong, type to add what it missed.
 *
 * Deliberately not a dropdown. The options are whatever the parser found, so
 * there is no fixed list to pick from, and a combobox would imply one.
 */
export function TagInput({
  label,
  hint,
  value,
  onChange,
  placeholder = "Type a skill and press Enter",
}: {
  label: string;
  hint?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const id = useId();
  const [draft, setDraft] = useState("");

  function commit() {
    const entry = draft.trim();
    if (!entry) return;
    // Case-insensitive dedupe: "Python" and "python" are the same skill, and
    // sending both would weight the embedding toward it.
    if (!value.some((item) => item.toLowerCase() === entry.toLowerCase())) {
      onChange([...value, entry]);
    }
    setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
      return;
    }
    // Backspace on an empty field removes the last tag, which is the behaviour
    // every tag input has and people expect without being told.
    if (event.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div>
      <div className="mb-1.5">
        <label htmlFor={id} className="text-sm font-semibold text-ink">
          {label}
        </label>
        {hint && <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{hint}</p>}
      </div>

      <div
        className={cn(
          "flex flex-wrap gap-1.5 rounded-control border border-line bg-surface p-2",
          "transition-colors duration-state ease-enter focus-within:border-brand",
        )}
      >
        {value.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-chip bg-brand/[0.08] py-1 pl-2.5 pr-1 text-xs font-semibold text-brand"
          >
            {tag}
            <button
              type="button"
              onClick={() => onChange(value.filter((item) => item !== tag))}
              aria-label={`Remove ${tag}`}
              className="grid h-4 w-4 place-items-center rounded-full text-brand/70 transition-colors duration-state hover:bg-brand hover:text-white"
            >
              &times;
            </button>
          </span>
        ))}

        <input
          id={id}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          // Committing on blur means a typed-but-not-entered skill is not
          // silently lost when the user tabs to Save.
          onBlur={commit}
          placeholder={value.length ? "" : placeholder}
          className="min-w-[10rem] flex-1 bg-transparent px-1.5 py-1 text-sm text-ink outline-none placeholder:text-ink-muted/60"
        />
      </div>
    </div>
  );
}
