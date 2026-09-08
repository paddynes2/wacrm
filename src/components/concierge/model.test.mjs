import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('./model.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const model = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`
);

test('unknown status never becomes a claimed success', () => {
  assert.equal(model.statusLabel('unknown-provider-state'), 'Needs review');
  assert.equal(model.statusLabel('proposed'), 'Ready to approach');
});
test('unanswered reply takes precedence over mutually agreed introduction', () => {
  assert.match(
    model.nextStep({
      status: 'agreed',
      reply_required: true,
      introduction_agreed: true,
      group_agreed: true,
    }),
    /Reply to the latest message/
  );
});
test('human takeover and opt-out take precedence over next automated step', () => {
  assert.match(
    model.nextStep({ status: 'human_owned', reply_required: true }),
    /paused/
  );
  assert.match(
    model.nextStep({ status: 'opted_out', reply_required: true }),
    /No further contact/
  );
});
test('approval cards join only the exact pursuit', () => {
  const decision = {
    id: 'd1',
    action: { frozen: { concierge: { pursuit_id: 'wacrm:contact-1' } } },
  };
  assert.equal(model.belongsToDecision(decision, 'wacrm:contact-1'), true);
  assert.equal(model.belongsToDecision(decision, 'wacrm:contact-2'), false);
  assert.equal(model.belongsToDecision({ id: 'd2' }, 'wacrm:contact-1'), false);
  assert.equal(
    model.belongsToDecision(
      { id: 'booking', action: { context: { pursuit_id: 'wacrm:contact-1' } } },
      'wacrm:contact-1'
    ),
    true
  );
});
test('unsafe and credential-bearing profile links are not clickable', () => {
  for (const value of [
    'javascript:alert(1)',
    'data:text/html,x',
    'http://example.com',
    'https://user:password@example.com',
    '',
    undefined,
  ])
    assert.equal(model.safeLink(value), null);
  assert.equal(
    model.safeLink('https://example.com/profile'),
    'https://example.com/profile'
  );
});
test('timeline preserves exact text and does not manufacture a meeting', () => {
  assert.equal(
    model.eventText({
      kind: 'inbound',
      data: { text: 'Could you explain the offer?' },
    }),
    'Could you explain the offer?'
  );
  assert.equal(
    model.eventText({ kind: 'unexpected' }),
    'Conversation updated.'
  );
  assert.equal(
    model.eventText({ kind: 'consent', data: { scope: 'group' } }),
    'Permission recorded: A group conversation.'
  );
});
test('five consent scopes remain distinct', () => {
  assert.deepEqual(Object.keys(model.SCOPE_LABELS), [
    'contact',
    'introduction',
    'group',
    'scheduling',
    'booking',
  ]);
});
test('initials handle empty and multiword names', () => {
  assert.equal(model.initials(''), '?');
  assert.equal(model.initials('  Patrick Nesbitt  '), 'PN');
});
test('search dates resolve in the principal timezone including date-specific DST', () => {
  assert.equal(
    model.dateBoundary('2026-09-15', 'Africa/Johannesburg'),
    '2026-09-14T22:00:00.000Z'
  );
  assert.equal(
    model.dateBoundary('2026-09-15', 'Africa/Johannesburg', true),
    '2026-09-15T22:00:00.000Z'
  );
  assert.equal(
    model.dateBoundary('2026-11-02', 'America/Los_Angeles'),
    '2026-11-02T08:00:00.000Z'
  );
  assert.throws(() => model.dateBoundary('2011-12-30', 'Pacific/Apia'));
  assert.throws(() => model.dateBoundary('2026-02-30', 'UTC'));
});
