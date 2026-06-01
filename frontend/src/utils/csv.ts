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

/**
 * Parse CSV text into rows of string cells.
 *
 * Handles RFC-4180 essentials: double-quoted fields, escaped quotes (`""`),
 * embedded commas/newlines inside quotes, and both `\n` and `\r\n` line
 * endings. Fully blank records are dropped. This is the single shared CSV
 * reader on the frontend — pair it with {@link buildCsvString} for writing.
 */
export function parseCsvRecords(text: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let cell = '';
  let inQuotes = false;

  const endCell = () => {
    record.push(cell);
    cell = '';
  };
  const endRecord = () => {
    endCell();
    records.push(record);
    record = [];
  };

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      endCell();
    } else if (char === '\n') {
      endRecord();
    } else if (char === '\r') {
      if (text[i + 1] === '\n') i++;
      endRecord();
    } else {
      cell += char;
    }
  }

  endRecord();

  return records.filter((row) => row.some((value) => value.trim().length > 0));
}

/** Normalize a CSV header cell: strip BOM, trim, lowercase. */
export function normalizeCsvHeader(value: string): string {
  return value.replace(/^\uFEFF/, '').trim().toLowerCase();
}

/**
 * Parse CSV text into a header list plus row objects keyed by normalized
 * header name. Returns `null` when the text has no data rows. Reuses
 * {@link parseCsvRecords} and {@link normalizeCsvHeader}.
 */
export function parseCsvAsObjects(
  text: string,
): { headers: string[]; rows: Record<string, string>[] } | null {
  const records = parseCsvRecords(text);
  if (records.length < 2) {
    return null;
  }

  const [headerRecord, ...dataRecords] = records;
  const headers = headerRecord.map(normalizeCsvHeader);
  const rows = dataRecords.map((record) => {
    const row: Record<string, string> = {};
    headers.forEach((header, index) => {
      // First occurrence wins for duplicate headers, matching the backend reader.
      if (!(header in row)) {
        row[header] = record[index] ?? '';
      }
    });
    return row;
  });

  return { headers, rows };
}
