export const MAX_PROSPECT_ROWS = 200;
export const MAX_CSV_LENGTH = 200_000;
export const PROSPECT_COLUMNS = [
  'name',
  'phone',
  'email',
  'company',
  'profile_url',
  'fit',
  'source',
] as const;
export type Prospect = Record<(typeof PROSPECT_COLUMNS)[number], string>;
export type ProspectRow = {
  row: number;
  prospect: Prospect;
  errors: string[];
  duplicate?: boolean;
  retryable?: boolean;
};

/** Country codes must be supplied by the operator; never guess a person's country. */
export function normalizeProspectPhone(value: string): string | null {
  const phone = value.trim().replace(/[ ()\-.]/g, '');
  return /^\+[1-9]\d{7,14}$/.test(phone) ? phone : null;
}

function validEmail(value: string): boolean {
  if (value.length > 254) return false;
  const parts = value.split('@');
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  return (
    local.length <= 64 &&
    /^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+$/i.test(local) &&
    !local.startsWith('.') &&
    !local.endsWith('.') &&
    !local.includes('..') &&
    domain.includes('.') &&
    domain
      .split('.')
      .every((label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label))
  );
}

function parseCsv(csv: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [],
    cell = '',
    quoted = false,
    closed = false;
  const pushRow = () => {
    row.push(cell);
    if (row.some((v) => v.trim())) rows.push(row);
    row = [];
    cell = '';
    closed = false;
  };
  for (let i = 0; i < csv.length; i++) {
    const c = csv[i];
    if (quoted) {
      if (c === '"' && csv[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
        closed = true;
      } else cell += c;
    } else if (c === ',' || c === '\n' || c === '\r') {
      if (c === ',') {
        row.push(cell);
        cell = '';
        closed = false;
      } else {
        if (c === '\r' && csv[i + 1] === '\n') i++;
        pushRow();
      }
    } else if (c === '"') {
      if (cell || closed)
        throw new Error(
          'Unexpected quote. Quote the entire CSV field and double quotes inside it.'
        );
      quoted = true;
    } else {
      if (closed) throw new Error('Unexpected text after a quoted CSV field.');
      cell += c;
    }
  }
  if (quoted) throw new Error('Unclosed quoted CSV field.');
  pushRow();
  return rows;
}

export function previewProspects(csv: string): ProspectRow[] {
  if (csv.length > MAX_CSV_LENGTH)
    throw new Error('CSV is too large. Maximum 200,000 characters.');
  const [header, ...data] = parseCsv(csv.replace(/^\uFEFF/, ''));
  if (!header || !data.length)
    throw new Error('Include a header and at least one prospect.');
  const columns = header.map((v) => v.trim().toLowerCase());
  if (
    new Set(columns).size !== columns.length ||
    columns.some(
      (v) => !PROSPECT_COLUMNS.includes(v as (typeof PROSPECT_COLUMNS)[number])
    )
  )
    throw new Error(
      'Use unique supported column names: ' + PROSPECT_COLUMNS.join(', ')
    );
  if (['name', 'phone', 'source'].some((v) => !columns.includes(v)))
    throw new Error('The name, phone and source columns are required.');
  if (data.length > MAX_PROSPECT_ROWS)
    throw new Error('Import at most 200 prospects at a time.');
  const seen = new Set<string>();
  return data.map((cells, index) => {
    const prospect = Object.fromEntries(
      PROSPECT_COLUMNS.map((key) => [
        key,
        (cells[columns.indexOf(key)] ?? '').trim(),
      ])
    ) as Prospect;
    const errors: string[] = [];
    if (cells.length !== columns.length)
      errors.push('Column count differs from the header.');
    for (const key of PROSPECT_COLUMNS)
      if (prospect[key].length > (key === 'fit' ? 4000 : 1000))
        errors.push(`${key} is too long.`);
    if (!prospect.name) errors.push('Name is required.');
    if (!prospect.source) errors.push('Source evidence is required.');
    const phone = normalizeProspectPhone(prospect.phone);
    if (!phone)
      errors.push(
        'Use an international phone number beginning with + and its country code.'
      );
    else {
      prospect.phone = phone;
      if (seen.has(phone)) errors.push('Duplicate phone in this CSV.');
      else seen.add(phone);
    }
    if (prospect.email && !validEmail(prospect.email))
      errors.push('Email is invalid.');
    if (prospect.profile_url) {
      try {
        const url = new URL(prospect.profile_url);
        if (
          !['https:', 'http:'].includes(url.protocol) ||
          url.username ||
          url.password
        )
          throw new Error();
      } catch {
        errors.push(
          'Profile must be an HTTP or HTTPS URL without credentials.'
        );
      }
    }
    // Spreadsheet expressions are inert text here, but reject them before downstream CSV export.
    if (
      PROSPECT_COLUMNS.some(
        (key) => key !== 'phone' && /^[=+@\-\t\r]/.test(prospect[key])
      )
    )
      errors.push('Spreadsheet formula prefixes are not accepted.');
    return { row: index + 2, prospect, errors };
  });
}
