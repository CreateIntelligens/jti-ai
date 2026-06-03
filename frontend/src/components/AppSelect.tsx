import * as RadixSelect from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';

export interface AppSelectOption {
  value: string;
  label: string;
}

export interface AppSelectGroup {
  label: string;
  options: AppSelectOption[];
}

type AppSelectEntry = AppSelectOption | AppSelectGroup;

interface AppSelectProps {
  options: AppSelectEntry[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  title?: string;
  className?: string;
  contentClassName?: string;
  disabled?: boolean;
}

// Radix Select forbids empty-string item values (it reserves '' for "no selection").
// We map '' ↔ '__none__' internally so callers can use '' as a valid option value.
const NONE_SENTINEL = '__none__';
const toRadix = (v: string) => v === '' ? NONE_SENTINEL : v;
const fromRadix = (v: string) => v === NONE_SENTINEL ? '' : v;

function isGroup(option: AppSelectEntry): option is AppSelectGroup {
  return 'options' in option;
}

function findOption(options: AppSelectEntry[], value: string): AppSelectOption | undefined {
  for (const opt of options) {
    if (isGroup(opt)) {
      const found = opt.options.find((o) => o.value === value);
      if (found) return found;
    } else if (opt.value === value) {
      return opt;
    }
  }
  return undefined;
}

function SelectItem({ option }: { option: AppSelectOption }) {
  return (
    <RadixSelect.Item
      value={toRadix(option.value)}
      className="app-select-item"
    >
      <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
      <RadixSelect.ItemIndicator className="app-select-item-indicator">
        <Check size={12} />
      </RadixSelect.ItemIndicator>
    </RadixSelect.Item>
  );
}

export default function AppSelect({
  options,
  value,
  onChange,
  placeholder = '—',
  title,
  className = '',
  contentClassName = '',
  disabled = false,
}: AppSelectProps) {
  const selectedOption = findOption(options, value);

  // When the trigger label is truncated by CSS, expose the full text on hover.
  const triggerTitle = title ?? selectedOption?.label;

  const radixValue = (value === '' && !selectedOption) ? undefined : toRadix(value);

  return (
    <RadixSelect.Root
      value={radixValue}
      onValueChange={(v) => onChange(fromRadix(v))}
      disabled={disabled}
    >
      <RadixSelect.Trigger className={`app-select-trigger ${className}`} title={triggerTitle}>
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon className="app-select-icon">
          <ChevronDown size={14} />
        </RadixSelect.Icon>
      </RadixSelect.Trigger>

      <RadixSelect.Portal>
        <RadixSelect.Content className={`app-select-content ${contentClassName}`} position="popper" sideOffset={4}>
          <RadixSelect.Viewport className="app-select-viewport">
            {options.map((opt, i) => {
              if (isGroup(opt)) {
                return (
                  <RadixSelect.Group key={i} className="app-select-group">
                    <RadixSelect.Label className="app-select-label">
                      {opt.label}
                    </RadixSelect.Label>
                    {opt.options.map((option) => (
                      <SelectItem key={option.value} option={option} />
                    ))}
                  </RadixSelect.Group>
                );
              }

              return <SelectItem key={opt.value} option={opt} />;
            })}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
