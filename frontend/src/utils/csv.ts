type CsvCell = string | number | null | undefined;

export function escapeCsvCell(value: CsvCell): string {
  const str = value == null ? '' : String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return `"${str}"`;
}

export function buildCsvString(header: string[], rows: CsvCell[][]): string {
  return [
    header.map(escapeCsvCell).join(','),
    ...rows.map((row) => row.map(escapeCsvCell).join(',')),
  ].join('\n');
}
