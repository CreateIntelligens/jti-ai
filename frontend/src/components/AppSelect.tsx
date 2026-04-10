import * as RadixSelect from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';

export interface AppSelectOption {
  value: string;
  label: string;
}

interface AppSelectProps {
  options: AppSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  contentClassName?: string;
  disabled?: boolean;
}

// Radix Select forbids empty-string item values (it reserves '' for "no selection").
// We map '' ↔ '__none__' internally so callers can use '' as a valid option value.
const NONE_SENTINEL = '__none__';
const toRadix = (v: string) => v === '' ? NONE_SENTINEL : v;
const fromRadix = (v: string) => v === NONE_SENTINEL ? '' : v;

export default function AppSelect({
  options,
  value,
  onChange,
  placeholder = '—',
  className = '',
  contentClassName = '',
  disabled = false,
}: AppSelectProps) {
  return (
    <RadixSelect.Root
      value={toRadix(value)}
      onValueChange={(v) => onChange(fromRadix(v))}
      disabled={disabled}
    >
      <RadixSelect.Trigger className={`app-select-trigger ${className}`}>
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon className="app-select-icon">
          <ChevronDown size={14} />
        </RadixSelect.Icon>
      </RadixSelect.Trigger>

      <RadixSelect.Portal>
        <RadixSelect.Content className={`app-select-content ${contentClassName}`} position="popper" sideOffset={4}>
          <RadixSelect.Viewport className="app-select-viewport">
            {options.map((option) => (
              <RadixSelect.Item
                key={option.value}
                value={toRadix(option.value)}
                className="app-select-item"
              >
                <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                <RadixSelect.ItemIndicator className="app-select-item-indicator">
                  <Check size={12} />
                </RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
