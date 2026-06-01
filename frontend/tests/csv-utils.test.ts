import { describe, expect, it } from 'vitest';

import {
  buildCsvString,
  normalizeCsvHeader,
  parseCsvAsObjects,
  parseCsvRecords,
} from '../src/utils/csv';

describe('parseCsvRecords', () => {
  it('parses simple comma-separated rows', () => {
    expect(parseCsvRecords('a,b,c\n1,2,3')).toEqual([
      ['a', 'b', 'c'],
      ['1', '2', '3'],
    ]);
  });

  it('handles quoted fields with embedded commas and newlines', () => {
    const text = 'q,a\n"hello, world","line1\nline2"';
    expect(parseCsvRecords(text)).toEqual([
      ['q', 'a'],
      ['hello, world', 'line1\nline2'],
    ]);
  });

  it('unescapes doubled quotes inside quoted fields', () => {
    expect(parseCsvRecords('q\n"say ""hi"""')).toEqual([['q'], ['say "hi"']]);
  });

  it('treats CRLF and LF line endings the same', () => {
    expect(parseCsvRecords('a,b\r\n1,2\r\n3,4')).toEqual([
      ['a', 'b'],
      ['1', '2'],
      ['3', '4'],
    ]);
  });

  it('drops fully blank records but keeps rows with any content', () => {
    expect(parseCsvRecords('a,b\n\n1,2\n  ,  ')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });

  it('round-trips output of buildCsvString', () => {
    const csv = buildCsvString(
      ['index', 'q', 'a'],
      [[1, 'comma, here', 'quote " here']],
    );
    expect(parseCsvRecords(csv)).toEqual([
      ['index', 'q', 'a'],
      ['1', 'comma, here', 'quote " here'],
    ]);
  });
});

describe('normalizeCsvHeader', () => {
  it('strips a leading BOM, trims, and lowercases', () => {
    expect(normalizeCsvHeader('﻿ Display ')).toBe('display');
  });
});

describe('parseCsvAsObjects', () => {
  it('keys rows by normalized header name', () => {
    const result = parseCsvAsObjects('﻿Q,A,Display\nfoo,bar,false');
    expect(result).toEqual({
      headers: ['q', 'a', 'display'],
      rows: [{ q: 'foo', a: 'bar', display: 'false' }],
    });
  });

  it('returns null when there are no data rows', () => {
    expect(parseCsvAsObjects('q,a,display')).toBeNull();
    expect(parseCsvAsObjects('')).toBeNull();
  });

  it('lets the first occurrence win for duplicate headers', () => {
    const result = parseCsvAsObjects('q,q\nfirst,second');
    expect(result?.rows).toEqual([{ q: 'first' }]);
  });

  it('fills missing trailing cells with empty strings', () => {
    const result = parseCsvAsObjects('q,a,url\nfoo,bar');
    expect(result?.rows).toEqual([{ q: 'foo', a: 'bar', url: '' }]);
  });
});
