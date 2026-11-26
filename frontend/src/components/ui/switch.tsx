import * as S from "@radix-ui/react-switch";
export function Switch({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <S.Root
      aria-label={label}
      checked={checked}
      onCheckedChange={onChange}
      className="switch"
    >
      <S.Thumb />
    </S.Root>
  );
}
