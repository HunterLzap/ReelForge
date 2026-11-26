import type { ComponentProps } from "react";
export function Button({
  variant = "default",
  className = "",
  type = "button",
  ...props
}: ComponentProps<"button"> & {
  variant?: "default" | "primary" | "ghost" | "danger";
}) {
  return (
    <button type={type} className={`btn ${variant} ${className}`} {...props} />
  );
}
