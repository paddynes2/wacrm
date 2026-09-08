import { expect, it } from 'vitest';
import { sameOrigin } from './origin';
it('accepts the browser host despite Next internal URL normalization', () => {
  expect(
    sameOrigin(
      new Request('http://localhost:8316/api/concierge', {
        headers: { host: '127.0.0.1:8316', origin: 'http://127.0.0.1:8316' },
      })
    )
  ).toBe(true);
});
it('refuses cross origin, protocol and malformed origin', () => {
  for (const origin of [
    'http://evil.test',
    'http://127.0.0.1:8317',
    'https://127.0.0.1:8316',
    'null',
  ]) {
    expect(
      sameOrigin(
        new Request('http://localhost:8316/api/concierge', {
          headers: { host: '127.0.0.1:8316', origin },
        })
      )
    ).toBe(false);
  }
});
