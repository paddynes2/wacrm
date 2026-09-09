import { ConnectionReadiness } from '@/components/concierge/readiness';

import { redirect } from 'next/navigation';

export default function ConnectionsPage() {
  if (process.env.WACRM_STANDALONE === '1') redirect('/dogfood');
  return <ConnectionReadiness />;
}
