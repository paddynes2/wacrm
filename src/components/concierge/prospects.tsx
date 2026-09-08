'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  Loader2,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import type { ProspectRow } from '@/lib/concierge/prospecting';

const EXAMPLE =
  'name,phone,email,company,profile_url,fit,source\nJamie Smith,+27820000004,jamie@example.com,Example Studio,https://example.com/team,"Workflow implementation partner, complementary services",Operator research: example team page';
type ImportResult = {
  row: number;
  status: string;
  error?: string;
  contact_id?: string;
};
const STATUS: Record<string, string> = {
  imported: 'Imported',
  already_imported: 'Already imported; source note checked',
  duplicate: 'Existing contact retained',
  invalid: 'Needs correction',
  failed: 'Contact not saved',
  note_failed: 'Contact saved; note needs retry',
};

export function ProspectsWorkspace() {
  const [csv, setCsv] = useState('');
  const [rows, setRows] = useState<ProspectRow[] | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [results, setResults] = useState<ImportResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const eligible =
    rows?.filter(
      (row) => !row.errors.length && (!row.duplicate || row.retryable)
    ) ?? [];
  async function run(action: 'preview' | 'import') {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/concierge/prospects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          csv,
          ...(action === 'import' ? { selected_rows: selected } : {}),
        }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.error || 'The import could not be processed.');
      if (action === 'preview') {
        setRows(data.rows);
        setSelected([]);
        setResults(null);
      } else {
        setResults((current) =>
          [
            ...(current ?? []).filter(
              (old) =>
                !data.results.some((next: ImportResult) => next.row === old.row)
            ),
            ...data.results,
          ].sort((a, b) => a.row - b.row)
        );
        setSelected(
          data.results
            .filter((r: ImportResult) =>
              ['failed', 'note_failed'].includes(r.status)
            )
            .map((r: ImportResult) => r.row)
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Request failed. If importing, inspect Contacts or retry: repeated imports reuse the same contact.'
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  function changeCsv(value: string) {
    setCsv(value);
    setRows(null);
    setSelected([]);
    setResults(null);
    setError('');
  }
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-muted-foreground mb-2 flex items-center gap-2 text-sm">
            <Search className="size-4" /> Research to relationships
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Prospects</h1>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-6">
            Bring your research into the CRM with its source and reason for
            reaching out. Review every row before importing.
          </p>
        </div>
        <Link
          href="/contacts"
          className="hover:bg-muted flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
        >
          View contacts <ArrowRight className="size-4" />
        </Link>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
        <section className="bg-card space-y-4 rounded-xl border p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 font-medium">
              <FileSpreadsheet className="text-primary size-4" /> 1. Paste your
              research
            </h2>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => changeCsv(EXAMPLE)}
            >
              Load sample
            </Button>
          </div>
          <label
            htmlFor="prospect-csv"
            className="text-muted-foreground block text-sm"
          >
            CSV with a header row. Name, international phone and source are
            required.
          </label>
          <Textarea
            id="prospect-csv"
            value={csv}
            onChange={(event) => changeCsv(event.target.value)}
            disabled={busy}
            maxLength={200000}
            className="min-h-56 resize-y font-mono text-xs leading-6"
            placeholder="name,phone,email,company,profile_url,fit,source"
            spellCheck={false}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-muted-foreground text-xs">
              Up to 200 rows · Include + and country code · Quoted commas
              supported
            </p>
            <Button
              disabled={busy || !csv.trim()}
              onClick={() => run('preview')}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}{' '}
              Preview prospects
            </Button>
          </div>
        </section>
        <aside className="bg-muted/30 space-y-3 rounded-xl border p-5 text-sm">
          <ShieldCheck className="text-primary size-5" />
          <h2 className="font-medium">Keep the evidence</h2>
          <p className="text-muted-foreground leading-6">
            Include the profile or research source and a specific reason the
            relationship makes sense. These become a note on the contact.
          </p>
          <p className="text-muted-foreground leading-6">
            Imports create contacts only. They do not send messages, verify
            research, or establish permission to contact someone.
          </p>
          <p className="text-muted-foreground text-xs leading-5">
            Existing contacts are preserved. Add further research to their CRM
            notes. No external databases or paid enrichment are queried.
          </p>
        </aside>
      </div>
      {error && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border p-4 text-sm"
        >
          {error}
        </div>
      )}
      {rows && (
        <section className="bg-card overflow-hidden rounded-xl border">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-5">
            <div>
              <h2 className="font-medium">2. Review and select</h2>
              <p className="text-muted-foreground mt-1 text-sm">
                {eligible.length} ready ·{' '}
                {rows.filter((row) => row.errors.length).length} need correction
                · {rows.filter((row) => row.duplicate).length} already in your
                CRM
              </p>
            </div>
            <Button
              variant="outline"
              disabled={busy || !eligible.length || !!results}
              onClick={() =>
                setSelected(
                  selected.length === eligible.length
                    ? []
                    : eligible.map((row) => row.row)
                )
              }
            >
              {selected.length === eligible.length
                ? 'Clear selection'
                : 'Select ready rows'}
            </Button>
          </div>
          <div className="divide-y">
            {rows.map((row) => (
              <div key={row.row} className="flex items-start gap-3 p-5">
                <input
                  type="checkbox"
                  aria-label={`Select ${row.prospect.name || `row ${row.row}`}`}
                  className="accent-primary mt-1 size-4"
                  disabled={
                    busy ||
                    !!row.errors.length ||
                    (row.duplicate && !row.retryable) ||
                    !!results
                  }
                  checked={selected.includes(row.row)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, row.row]
                        : current.filter((n) => n !== row.row)
                    )
                  }
                />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {row.prospect.name || 'Unnamed prospect'}
                    </span>
                    <Badge variant="secondary">Row {row.row}</Badge>
                    {row.duplicate && (
                      <Badge variant="outline">
                        {row.retryable
                          ? 'Previously imported; can repair source note'
                          : 'Already in CRM'}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground text-sm break-words">
                    {[
                      row.prospect.phone,
                      row.prospect.company,
                      row.prospect.email,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  {row.prospect.fit && (
                    <p className="text-sm break-words whitespace-pre-wrap">
                      {row.prospect.fit}
                    </p>
                  )}
                  <p className="text-muted-foreground text-xs break-words">
                    Source: {row.prospect.source || 'Missing'}
                  </p>
                  {row.prospect.profile_url && (
                    <p className="text-muted-foreground text-xs break-all">
                      Profile: {row.prospect.profile_url}
                    </p>
                  )}
                  {row.errors.map((message) => (
                    <p key={message} className="text-destructive text-sm">
                      {message}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="bg-muted/20 flex flex-wrap items-center justify-between gap-3 border-t p-5">
            <p className="text-muted-foreground text-sm">
              {selected.length} selected{results ? ' for retry' : ' for import'}
            </p>
            <Button
              disabled={busy || !selected.length}
              onClick={() => run('import')}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ArrowRight className="size-4" />
              )}
              {results
                ? 'Retry incomplete rows'
                : `Import ${selected.length} selected`}
            </Button>
          </div>
        </section>
      )}
      {results && (
        <section
          aria-live="polite"
          className="bg-card space-y-4 rounded-xl border p-5"
        >
          <h2 className="flex items-center gap-2 font-medium">
            <CheckCircle2 className="size-4" /> Import results
          </h2>
          <ul className="space-y-2 text-sm">
            {results.map((result) => (
              <li key={result.row} className="flex flex-wrap gap-x-2">
                <span className="font-medium">Row {result.row}:</span>
                <span>{STATUS[result.status] || result.status}</span>
                {result.error && (
                  <span className="text-destructive">{result.error}</span>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-4 text-sm">
            <Link
              href="/contacts"
              className="text-primary underline underline-offset-4"
            >
              Review contacts and source notes
            </Link>
            <Link
              href="/concierge"
              className="text-primary underline underline-offset-4"
            >
              Open Concierge
            </Link>
          </div>
        </section>
      )}
    </main>
  );
}
