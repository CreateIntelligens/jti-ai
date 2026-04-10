import AppSelect, { type AppSelectOption } from '../AppSelect';

interface HciotSelectProps {
  options: AppSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export default function HciotSelect(props: HciotSelectProps) {
  return <AppSelect {...props} contentClassName="hciot-select-content" />;
}
