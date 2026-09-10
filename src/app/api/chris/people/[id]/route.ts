import { detail } from '@/lib/chris/routes';
export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) { const { id } = await context.params; return detail('people', id); }
