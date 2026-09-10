import { expect, it } from 'vitest';
import { acceptRead } from './read-fence';
import { safeSource } from './view';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { DossierEvidence } from '@/components/chris/dossier-evidence';

it('P14 rejects a late account A response after switching to B, including manual refresh', async () => {
  let current = 'A';
  const pending = Promise.resolve({ account: current, revision: 900 });
  current = 'B';
  const result = await pending;
  expect(acceptRead(result.account, current, false, true, result.revision, 0)).toBe(false);
  expect(acceptRead('B', current, false, true, 1, 0)).toBe(true);
});

it('P15 accepts idle progress while refusing stale or aborted reads', () => {
  expect(acceptRead('A', 'A', false, true, 11, 10)).toBe(true);
  expect(acceptRead('A', 'A', false, true, 9, 10)).toBe(false);
  expect(acceptRead('A', 'A', true, true, 11, 10)).toBe(false);
});

it('P19 never renders executable or credential-bearing source links', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'https://user:password@example.com', '<img src=x onerror=alert(1)>']) expect(safeSource(value)).toBeUndefined();
  expect(safeSource('https://example.com/evidence')).toBe('https://example.com/evidence');
  const html = renderToStaticMarkup(createElement(DossierEvidence, { dossier: { facts: [{ text: '<img src=x onerror=alert(1)>', source_ids: [] }], inferences: [] }, sources: {} }));
  expect(html).not.toContain('<img'); expect(html).toContain('&lt;img');
});
