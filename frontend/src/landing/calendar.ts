/** Read the current year on each render, never a fixed launch year. */
export function copyrightYear(date = new Date()): number {
  return date.getFullYear();
}