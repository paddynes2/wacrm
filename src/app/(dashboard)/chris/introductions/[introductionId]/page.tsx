import { ChrisWorkspace } from '@/components/chris/workspace';
export default async function Page({ params }: { params: Promise<{ introductionId: string }> }) { const { introductionId } = await params; return <ChrisWorkspace section="introductions" entityId={introductionId} />; }
