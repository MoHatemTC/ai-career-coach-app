import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useId } from "react";

import { cn } from "@/lib/cn";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3.5 py-2.5 text-body " +
  "text-ink placeholder:text-ink-muted/60 transition-colors duration-state ease-enter " +
  "hover:border-brand/40 focus:border-brand focus:outline-none";

function Label({ htmlFor, children, hint }: { htmlFor: string; children: ReactNode; hint?: string }) {
  return (
    <div className="mb-1.5">
      <label htmlFor={htmlFor} className="text-body-sm font-medium text-ink">
        {children}
      </label>
      {hint && <p className="mt-0.5 text-label text-ink-muted">{hint}</p>}
    </div>
  );
}

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
}

export function TextField({ label, hint, className, ...rest }: TextFieldProps) {
  const id = useId();
  return (
    <div>
      <Label htmlFor={id} {...(hint === undefined ? {} : { hint })}>
        {label}
      </Label>
      <input id={id} className={cn(CONTROL, className)} {...rest} />
    </div>
  );
}

interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  label: string;
  hint?: string;
}

export function TextAreaField({ label, hint, className, ...rest }: TextAreaFieldProps) {
  const id = useId();
  return (
    <div>
      <Label htmlFor={id} {...(hint === undefined ? {} : { hint })}>
        {label}
      </Label>
      <textarea id={id} className={cn(CONTROL, "resize-y", className)} {...rest} />
    </div>
  );
}

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  hint?: string;
  options: readonly string[];
}

export function SelectField({ label, hint, options, className, ...rest }: SelectFieldProps) {
  const id = useId();
  return (
    <div>
      <Label htmlFor={id} {...(hint === undefined ? {} : { hint })}>
        {label}
      </Label>
      <select id={id} className={cn(CONTROL, "capitalize", className)} {...rest}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

interface SliderFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type"> {
  label: string;
  hint?: string;
  value: number;
}

export function SliderField({ label, hint, value, className, ...rest }: SliderFieldProps) {
  const id = useId();
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Label htmlFor={id} {...(hint === undefined ? {} : { hint })}>
          {label}
        </Label>
        <span className="tabular text-body-sm font-semibold text-brand">{value.toFixed(2)}</span>
      </div>
      <input
        id={id}
        type="range"
        value={value}
        className={cn("w-full accent-brand", className)}
        {...rest}
      />
    </div>
  );
}
