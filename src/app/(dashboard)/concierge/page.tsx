import { ConciergeWorkspace } from '@/components/concierge/workspace';
import { redirect } from 'next/navigation';

export default function ConciergePage() {
  if (process.env.WACRM_STANDALONE === '1') redirect('/dogfood');
  return <ConciergeWorkspace />;
}
