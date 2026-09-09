import { ConciergeOperations } from '@/components/concierge/operations';

import { redirect } from 'next/navigation';

export default function OperationsPage() {
  if (process.env.WACRM_STANDALONE === '1') redirect('/dogfood');
  return <ConciergeOperations />;
}
