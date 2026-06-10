export function resolveHistoryPageJump(
  rawPage: string,
  totalPages: number,
  currentPage: number,
): number {
  const parsedPage = Number.parseInt(rawPage, 10);
  if (!Number.isFinite(parsedPage)) {
    return currentPage;
  }

  const lastPage = Math.max(1, totalPages);
  return Math.min(Math.max(parsedPage, 1), lastPage);
}
