import { describe, expect, it } from 'vitest';
import { csvCell, neutralizeFormula, tsvCell } from './spreadsheetSafety';

describe('neutralizeFormula', () => {
  it.each([
    ['=1+1', "'=1+1"],
    ['=HYPERLINK("http://example.invalid","x")', '\'=HYPERLINK("http://example.invalid","x")'],
    ['+SUM(A1:A2)', "'+SUM(A1:A2)"],
    ['-1+1', "'-1+1"],
    ['@SUM(A1)', "'@SUM(A1)"],
    ['\t=1+1', "'\t=1+1"],
    ['\r=1+1', "'\r=1+1"],
  ])('prefixes formula trigger %j', (input, expected) => {
    expect(neutralizeFormula(input)).toBe(expected);
  });

  it('leaves ordinary text untouched', () => {
    expect(neutralizeFormula('')).toBe('');
    expect(neutralizeFormula('Baseline')).toBe('Baseline');
    expect(neutralizeFormula('a=b')).toBe('a=b');
  });
});

describe('csvCell', () => {
  it('neutralizes formula-leading strings and quotes when required', () => {
    expect(csvCell('=1+1')).toBe("'=1+1");
    expect(csvCell('=HYPERLINK("http://example.invalid","x")')).toBe(
      '"\'=HYPERLINK(""http://example.invalid"",""x"")"',
    );
    expect(csvCell('+100')).toBe("'+100");
    expect(csvCell('-5')).toBe("'-5");
    expect(csvCell('@A1')).toBe("'@A1");
    expect(csvCell('\tfoo')).toBe("'\tfoo");
    expect(csvCell('\rfoo')).toBe('"\'\rfoo"');
  });

  it('keeps numeric values unchanged, including negatives', () => {
    expect(csvCell(-5)).toBe('-5');
    expect(csvCell(-12.34)).toBe('-12.34');
    expect(csvCell(0)).toBe('0');
    expect(csvCell(2025)).toBe('2025');
  });

  it('quotes strings containing commas, quotes, or newlines without altering safe values', () => {
    expect(csvCell('SAMPLE-0001')).toBe('SAMPLE-0001');
    expect(csvCell('a,b')).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell('line1\nline2')).toBe('"line1\nline2"');
  });
});

describe('tsvCell', () => {
  it('neutralizes formula-leading strings while leaving numbers and commas plain', () => {
    expect(tsvCell('=1+1')).toBe("'=1+1");
    expect(tsvCell('=HYPERLINK("http://example.invalid","x")')).toBe(
      '"\'=HYPERLINK(""http://example.invalid"",""x"")"',
    );
    expect(tsvCell(-5)).toBe('-5');
    expect(tsvCell('a,b')).toBe('a,b');
    expect(tsvCell('a\tb')).toBe('"a\tb"');
    expect(tsvCell('\t=1+1')).toBe('"\'\t=1+1"');
  });
});
