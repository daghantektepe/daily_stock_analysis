export const OPEN_COMMAND_PALETTE_EVENT = 'dsa:open-command-palette';

export function openCommandPalette(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT));
  }
}
