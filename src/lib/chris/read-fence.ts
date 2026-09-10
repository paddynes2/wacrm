/** Account identity and request cancellation both fence asynchronous UI results. */
export function acceptRead(requestAccount: string | null | undefined, currentAccount: string | null | undefined,
  aborted: boolean, mounted: boolean, incomingRevision: number, currentRevision: number) {
  return requestAccount === currentAccount && !aborted && mounted && incomingRevision >= currentRevision;
}
