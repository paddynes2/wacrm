/** Next may normalize the internal URL to localhost; the browser's Host remains exact. */
export function sameOrigin(request: Request): boolean {
  const raw = request.headers.get('origin');
  if (!raw) return true;
  try {
    const origin = new URL(raw);
    const target = new URL(request.url);
    const host = request.headers.get('host') || target.host;
    return (
      ['http:', 'https:'].includes(origin.protocol) &&
      origin.protocol === target.protocol &&
      origin.host === host
    );
  } catch {
    return false;
  }
}
