import { describe, expect, it } from 'vitest';
import { previewProspects, normalizeProspectPhone } from './prospecting';

describe('source-grounded CSV preview', () => {
  it.each([
    'jane..doe@example.com',
    '.jane@example.com',
    'jane@-example.com',
    'jane@example..com',
    'jane@localhost',
  ])('conservatively rejects malformed email %s', (email) => {
    expect(
      previewProspects(
        `name,phone,source,email\nJane,+27820000004,Research,${email}`
      )[0].errors
    ).toContain('Email is invalid.');
  });
  it('parses BOM, CRLF, quoted commas, escaped quotes and multiline evidence', () => {
    const rows = previewProspects(
      '\uFEFFname,phone,source,fit\r\n"Jane, Doe",+27 (82) 000-0004,"An article\nby Jane","Said ""hello"""\r\n'
    );
    expect(rows[0]).toMatchObject({
      row: 2,
      errors: [],
      prospect: {
        name: 'Jane, Doe',
        phone: '+27820000004',
        source: 'An article\nby Jane',
        fit: 'Said "hello"',
      },
    });
  });
  it.each([
    '0820000004',
    '0027820000004',
    '+012345678',
    '+27820000004 ext 3',
    '+2782/0000004',
    '=123456789',
  ])('refuses ambiguous or unsafe phone %s', (phone) =>
    expect(normalizeProspectPhone(phone)).toBeNull()
  );
  it('rejects duplicate normalized phone numbers within a file', () => {
    const rows = previewProspects(
      'name,phone,source\nJane,+27 82 000 0004,Research\nJane,+27820000004,Research'
    );
    expect(rows[1].errors).toContain('Duplicate phone in this CSV.');
  });
  it.each([
    'name,phone\nJane,+27820000004',
    'name,phone,source,phone\nJane,+27820000004,x,y',
    'name,phone,source,extra\nJane,+27820000004,x,y',
    'name,phone,source\n"Jane,+27820000004,x',
    'name,phone,source\n"Jane"x,+27820000004,x',
  ])('refuses malformed CSV', (csv) =>
    expect(() => previewProspects(csv)).toThrow()
  );
  it('reports row errors without losing valid neighbors', () => {
    const rows = previewProspects(
      'name,phone,source,email,profile_url\nJane,+27820000004,,,javascript:alert(1)\nJohn,+27820000005,Research,john@example.com,https://example.com'
    );
    expect(rows[0].errors).toHaveLength(2);
    expect(rows[1].errors).toEqual([]);
  });
  it('rejects formula prefixes and credential URLs without executing or fetching them', () => {
    const row = previewProspects(
      'name,phone,source,profile_url\n=HYPERLINK(x),+27820000004,Research,https://user:password@example.com'
    )[0];
    expect(row.errors).toHaveLength(2);
  });
  it('bounds row counts and source field size', () => {
    expect(() =>
      previewProspects(
        'name,phone,source\n' + 'Jane,+27820000004,Research\n'.repeat(201)
      )
    ).toThrow('200');
    expect(
      previewProspects(
        'name,phone,source\nJane,+27820000004,' + 'a'.repeat(1001)
      )[0].errors
    ).toContain('source is too long.');
  });
});
