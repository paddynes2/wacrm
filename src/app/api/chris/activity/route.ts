import { get } from '@/lib/chris/routes';
export async function GET(request: Request) { return get(request, '/activity'); }
