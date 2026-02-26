export interface Tab {
  key: string;
  label: string;
  disabled?: boolean;
  title?: string;
  onClick?: () => void;
}

interface TabsProps {
  tabs: Tab[];
  activeKey: string;
  onChange: (key: string) => void;
  className?: string;
  tabClassName?: string;
}

export default function Tabs({
  tabs,
  activeKey,
  onChange,
  className = 'jti-settings-tabs',
  tabClassName = 'jti-settings-tab',
}: TabsProps) {
  return (
    <div className={className}>
      {tabs.map(tab => (
        <button
          key={tab.key}
          className={`${tabClassName} ${tab.key === activeKey ? 'active' : ''} ${tab.disabled ? 'disabled' : ''}`}
          onClick={() => {
            if (tab.disabled) return;
            onChange(tab.key);
            tab.onClick?.();
          }}
          disabled={tab.disabled}
          title={tab.title}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
