/** Join class names, dropping falsy ones. Small enough not to warrant clsx. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
