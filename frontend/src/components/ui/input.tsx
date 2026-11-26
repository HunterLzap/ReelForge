import type { ComponentProps, ReactNode } from "react";
export function Input(props: ComponentProps<"input">) {
  return <input className="input" {...props} />;
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
