import * as P from "@radix-ui/react-popover";
import type { ReactElement, ReactNode } from "react";
export function Popover({
  trigger,
  children,
}: {
  trigger: ReactElement;
  children: ReactNode;
}) {
  return (
    <P.Root>
      <P.Trigger asChild>{trigger}</P.Trigger>
      <P.Portal>
        <P.Content
          className="popover"
          collisionPadding={10}
          align="end"
          sideOffset={8}
        >
          {children}
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}
