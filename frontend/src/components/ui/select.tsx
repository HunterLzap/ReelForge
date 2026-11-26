import * as S from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
export function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly (T | { value: T; label: string; disabled?: boolean })[];
  onChange: (value: T) => void;
}) {
  return (
    <S.Root value={value} onValueChange={(v) => onChange(v as T)}>
      <S.Trigger aria-label={label} className="select">
        <S.Value />
        <ChevronDown size={14} />
      </S.Trigger>
      <S.Portal>
        <S.Content className="select-menu" position="popper" sideOffset={4}>
          <S.Viewport>
            {options.map((o) => {
              const option = typeof o === "string" ? { value: o, label: o } : o;
              return (
                <S.Item
                  className="option"
                  disabled={option.disabled}
                  key={option.value}
                  value={option.value}
                >
                  <S.ItemText>{option.label}</S.ItemText>
                  <S.ItemIndicator>
                    <Check size={14} />
                  </S.ItemIndicator>
                </S.Item>
              );
            })}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}
