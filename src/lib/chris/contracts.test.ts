import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { parse, validateCommand, canonical } from './contracts';
import { safeSource, overview } from './view';

const corpus = JSON.parse(readFileSync('concierge_service/tests/fixtures/chris/contracts/corpus.json', 'utf8')) as { name: string; raw: string; accept: boolean }[];
describe('shared Python/TypeScript command corpus', () => {
  for (const fixture of corpus) it(fixture.name, () => {
    const run = () => validateCommand(parse(fixture.raw));
    if (fixture.accept) expect(run).not.toThrow(); else expect(run).toThrow();
  });
  it('canonical encoding preserves Unicode and sorts object fields', () => {
    expect(canonical({ z: ['é', 2], a: true })).toBe('{"a":true,"z":["é",2]}');
  });
  it('does not expose executable source links or unvalidated success', () => {
    for (const link of ['javascript:alert(1)', 'data:text/html,test', 'https://user:password@example.com']) expect(safeSource(link)).toBeUndefined();
    expect(safeSource('https://example.com/source')).toBe('https://example.com/source');
    expect(() => overview({ introduced: true })).toThrow();
  });
});
