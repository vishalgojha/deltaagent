function parseSimpleMode(raw: string | undefined): boolean {
  if (!raw) return true;
  const value = raw.trim().toLowerCase();
  if (value === "0" || value === "false" || value === "off" || value === "no") {
    return false;
  }
  return true;
}

export const SIMPLE_MODE = parseSimpleMode(import.meta.env.VITE_SIMPLE_MODE);
