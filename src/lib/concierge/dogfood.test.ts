import { afterEach, describe, expect, it, vi } from 'vitest';
import { dogfoodRequest, validateDogfoodCommand } from './dogfood';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
describe('dogfood commands', () => {
  it('validates calendar scenario bounds without granting availability', () => {
    const value = {
      command: 'calendar_preferences',
      prospect_id: 'p',
      party: 'recipient',
      timezone: 'Africa/Johannesburg',
      windows: [{ weekday: 0, start: '09:00', end: '17:00' }],
      calendar_access: false,
      source_ref: 'Synthetic calendar scenario',
    };
    expect(validateDogfoodCommand(value)).toMatchObject({
      calendar_access: false,
    });
    expect(() =>
      validateDogfoodCommand({
        ...value,
        windows: [{ weekday: 7, start: '09:00', end: '17:00' }],
      })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({
        ...value,
        simulated_busy: [{ start: 'tomorrow', end: 'later' }],
      })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({ ...value, calendar_access: 'yes' })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({
        command: 'request_calendar_exception',
        prospect_id: 'p',
        party: 'other',
        start: '2026-10-01T08:00:00Z',
        end: '2026-10-01T09:00:00Z',
        source_ref: 'evidence',
      })
    ).toThrow();
  });
  it('binds booking amendments to reviewed digest and attributed change', () => {
    expect(
      validateDogfoodCommand({
        command: 'prepare_amendment',
        prospect_id: 'p',
        operation: 'cancel',
        source_ref: 'attested cancellation',
      })
    ).toMatchObject({ operation: 'cancel' });
    expect(() =>
      validateDogfoodCommand({
        command: 'prepare_amendment',
        prospect_id: 'p',
        operation: 'reschedule',
        source_ref: 'agreement',
      })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({
        command: 'approve_amendment',
        prospect_id: 'p',
        digest: 'spoof',
      })
    ).toThrow();
    expect(
      validateDogfoodCommand({
        command: 'approve_amendment',
        prospect_id: 'p',
        digest: 'a'.repeat(64),
      })
    ).toMatchObject({ command: 'approve_amendment' });
  });
  it('refuses browser-selected identity, transport and arbitrary commands', () => {
    for (const command of [
      { command: 'process', account_id: 'other' },
      { command: 'process', attested_by: 'other' },
      { command: 'link_contact', prospect_id: 'p' },
      { command: '__proto__' },
      null,
      [],
    ])
      expect(() => validateDogfoodCommand(command)).toThrow();
  });
  it('validates spending and discovery bounds', () => {
    for (const limit of [0, 21, 1.5, '2'])
      expect(() =>
        validateDogfoodCommand({ command: 'discover', source: 'treg', limit })
      ).toThrow();
    expect(
      validateDogfoodCommand({
        command: 'discover',
        source: 'fixture',
        limit: 10,
      })
    ).toMatchObject({ limit: 10 });
    expect(() =>
      validateDogfoodCommand({
        command: 'save_brief',
        brief: {
          principal_name: 'P',
          offer: 'Offer',
          audience: 'Operators',
          geography: 'ZA',
          timezone: 'Africa/Johannesburg',
          budget_usd: -1,
        },
      })
    ).toThrow();
  });
  it('requires attributed consent and valid explicit calendar offsets', () => {
    expect(() =>
      validateDogfoodCommand({
        command: 'consent',
        prospect_id: 'p',
        party: 'recipient',
        scope: 'contact',
        source_ref: '',
      })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({
        command: 'book',
        prospect_id: 'p',
        start: '2026-10-01T10:00:00',
        end: '2026-10-01T11:00:00',
      })
    ).toThrow();
    expect(() =>
      validateDogfoodCommand({
        command: 'book',
        prospect_id: 'p',
        start: '2026-10-01T11:00:00Z',
        end: '2026-10-01T10:00:00Z',
      })
    ).toThrow();
    expect(
      validateDogfoodCommand({
        command: 'book',
        prospect_id: 'p',
        start: '2026-10-01T10:00:00+02:00',
        end: '2026-10-01T11:00:00+02:00',
      })
    ).toMatchObject({ command: 'book' });
  });
  it('keeps unresolved numbers out of contact evidence', () => {
    expect(() =>
      validateDogfoodCommand({
        command: 'enrich',
        prospect_id: 'p',
        phone: '0820000000',
        source_ref: 'source',
      })
    ).toThrow();
    expect(
      validateDogfoodCommand({
        command: 'enrich',
        prospect_id: 'p',
        phone: '+27820000000',
        source_ref: 'source',
      })
    ).toMatchObject({ phone: '+27820000000' });
  });
});
describe('dogfood transport', () => {
  it('uses only server credentials and account-scoped endpoint', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:8317');
    vi.stubEnv('WACRM_BRIDGE_TOKEN', 'test-only');
    const fetch = vi
      .fn()
      .mockResolvedValue(Response.json({ mode: 'simulation' }));
    vi.stubGlobal('fetch', fetch);
    await dogfoodRequest('11111111-1111-4111-8111-111111111111', {
      command: 'process',
    });
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8317/workspace/11111111-1111-4111-8111-111111111111/dogfood',
      expect.objectContaining({
        method: 'POST',
        body: '{"command":"process"}',
        cache: 'no-store',
      })
    );
  });
  it('does not hide service errors as empty candidates', async () => {
    vi.stubEnv('WACRM_BRIDGE_URL', 'http://127.0.0.1:8317');
    vi.stubEnv('WACRM_BRIDGE_TOKEN', 'test-only');
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ detail: 'Provider unavailable' }, { status: 503 })
        )
    );
    await expect(
      dogfoodRequest('11111111-1111-4111-8111-111111111111')
    ).rejects.toThrow('Provider unavailable');
  });
});
