import AppSelect, { type AppSelectOption } from '../AppSelect';

// Neutral select used by the shared QA knowledge workspace. Keeps the
// `qa-select-content` class so existing styling applies across apps.
interface QaSelectProps {
  options: AppSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export default function QaSelect(props: QaSelectProps) {
  return <AppSelect {...props} contentClassName="qa-select-content" />;
}
