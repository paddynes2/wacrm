import { ProspectsWorkspace } from '@/components/concierge/prospects';

import { redirect } from 'next/navigation';

export default function ProspectsPage() {
  if (process.env.WACRM_STANDALONE === '1') redirect('/dogfood');
  return <ProspectsWorkspace />;
}
