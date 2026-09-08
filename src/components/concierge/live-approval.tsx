'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import type { PendingDecision } from './model';

export function LiveApproval({decision, busy, onConfirm}: {decision: PendingDecision; busy: boolean; onConfirm: () => Promise<Record<string, unknown> | null>}) {
  const [open,setOpen] = useState(false);
  const [result,setResult] = useState('');
  return <><Button disabled={busy || decision.stale || !decision.digest} onClick={() => {setResult('');setOpen(true);}}>Review live action</Button>
    <Dialog open={open} onOpenChange={value => {if (!busy) setOpen(value);}}><DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
      <DialogHeader><DialogTitle>Confirm this exact action</DialogTitle><DialogDescription>This requests real delivery through the connected account. Existing transport and calendar checks still apply.</DialogDescription></DialogHeader>
      <div className="bg-muted space-y-3 rounded-lg p-4 text-sm">
        <p className="font-medium">{decision.review?.purpose === 'booking' ? 'Create meeting and invite participants' : decision.review?.purpose === 'introduction' ? 'Create the introduction group' : 'Send WhatsApp message'}</p>
        <p className="break-words"><span className="text-muted-foreground">To: </span>{decision.review?.recipients?.map(value => typeof value === 'string' ? value.replace('@s.whatsapp.net','') : JSON.stringify(value)).join(', ') || 'See exact action details below'}</p>
        {decision.review?.text && <p className="whitespace-pre-wrap break-words leading-6">{decision.review.text}</p>}
        {decision.review?.summary && <p>{decision.review.summary}</p>}
        {decision.review?.start && <p>{decision.review.start} to {decision.review.end}</p>}
      </div>
      <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">Exact action details</summary><pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(decision.action,null,2)}</pre></details>
      {result && <p role="status" className="text-sm">{result}</p>}
      <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setOpen(false)}>Back</Button><Button disabled={busy || !!result} onClick={async () => {
        const response = await onConfirm();
        if (response) {
          const outcome = response.result as Record<string, unknown> | undefined;
          setResult(typeof outcome?.reason === 'string' ? outcome.reason : `Execution status: ${String(outcome?.status ?? 'unknown')}. Refresh the conversation to verify the outcome.`);
        }
      }}>{busy ? 'Checking…' : 'Confirm exact action'}</Button></DialogFooter>
    </DialogContent></Dialog>
  </>;
}
