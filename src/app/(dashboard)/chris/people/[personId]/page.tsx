import { ChrisWorkspace } from '@/components/chris/workspace';
export default async function Page({ params }: { params: Promise<{ personId: string }> }) { const { personId } = await params; return <ChrisWorkspace section="people" entityId={personId} />; }
