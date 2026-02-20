import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface MiniCalendarProps {
  label: string;
  value: string;           // 'YYYY-MM-DD' or ''
  onChange: (date: string) => void;
  highlightRange?: { from: string; to: string };
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

function pad(n: number) { return n < 10 ? `0${n}` : `${n}`; }
function toStr(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }

export default function MiniCalendar({ label, value, onChange, highlightRange }: MiniCalendarProps) {
  const today = new Date();
  const parsedValue = value && /^\d{4}-\d{2}(-\d{2})?$/.test(value) ? new Date(value) : null;
  const initial = (parsedValue && !isNaN(parsedValue.getTime())) ? parsedValue : today;
  const [year, setYear] = useState(initial.getFullYear());
  const [month, setMonth] = useState(initial.getMonth());

  // 當 value 從外部改變時，跳到對應年/月
  // 支援不完整的值：YYYY, YYYY-M, YYYY-MM, YYYY-MM-D, YYYY-MM-DD
  useEffect(() => {
    if (!value) return;
    const match = value.match(/^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$/);
    if (!match) return;
    const y = parseInt(match[1], 10);
    if (y < 1900 || y > 2100) return;
    setYear(y);
    if (match[2]) {
      const m = parseInt(match[2], 10);
      if (m >= 1 && m <= 12) setMonth(m - 1);
    }
  }, [value]);

  const prevMonth = () => { if (month === 0) { setYear(y => y - 1); setMonth(11); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 11) { setYear(y => y + 1); setMonth(0); } else setMonth(m => m + 1); };

  const startWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const dayStr = (day: number) => toStr(new Date(year, month, day));
  const isSelected = (day: number) => {
    if (!value) return false;
    // 完整匹配 YYYY-MM-DD
    if (value === dayStr(day)) return true;
    // 不完整日期：YYYY-M-D 或 YYYY-MM-D → 解析並比較
    const m = value.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (m) {
      return parseInt(m[1], 10) === year
        && parseInt(m[2], 10) === month + 1
        && parseInt(m[3], 10) === day;
    }
    return false;
  };
  const isToday = (day: number) => dayStr(day) === toStr(today);
  const isInRange = (day: number) => {
    if (!highlightRange?.from || !highlightRange?.to) return false;
    const d = dayStr(day);
    return d >= highlightRange.from && d <= highlightRange.to;
  };

  return (
    <div className="mini-cal">
      {label && <div className="mini-cal-label">{label}</div>}
      <div className="mini-cal-header">
        <button className="mini-cal-nav" onClick={prevMonth}><ChevronLeft size={14} /></button>
        <span className="mini-cal-title">{year} {MONTHS[month]}</span>
        <button className="mini-cal-nav" onClick={nextMonth}><ChevronRight size={14} /></button>
      </div>
      <div className="mini-cal-grid mini-cal-weekdays">
        {WEEKDAYS.map(w => <span key={w} className="mini-cal-wday">{w}</span>)}
      </div>
      <div className="mini-cal-grid">
        {cells.map((day, i) =>
          day ? (
            <button
              key={i}
              className={[
                'mini-cal-day',
                isSelected(day) ? 'selected' : '',
                isInRange(day) ? 'in-range' : '',
                isToday(day) ? 'today' : '',
              ].filter(Boolean).join(' ')}
              onClick={() => onChange(value === dayStr(day) ? '' : dayStr(day))}
            >
              {day}
            </button>
          ) : <span key={i} className="mini-cal-day empty" />
        )}
      </div>
    </div>
  );
}
