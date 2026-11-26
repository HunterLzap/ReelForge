import * as T from "@radix-ui/react-tooltip";
import type { ReactElement } from "react";
export const TooltipProvider = T.Provider;
export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactElement;
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content sideOffset={5} className="tooltip">
          {label}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
