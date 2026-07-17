export const DEFAULT_TIMEZONE = "America/Chicago";
export const DEFAULT_RUN_TIMES = ["05:00", "07:00", "09:00", "11:00", "13:15"];

export function isValidTimeZone(value: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

export function isValidRunTime(value: string): boolean {
  return /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
}

export function validateRunTimes(values: string[]): string | null {
  if (!values.length) return "Add at least one run time.";
  if (values.some(value => !isValidRunTime(value))) return "Each run time must use a valid HH:MM value.";
  if (new Set(values).size !== values.length) return "Run times must be unique.";
  return null;
}

export function sortRunTimes(values: string[]): string[] {
  return [...values].sort((left, right) => left.localeCompare(right));
}

export function nextLocalRunLabel(values: string[], timeZone = DEFAULT_TIMEZONE, now = new Date()): string {
  const sorted = sortRunTimes(values);
  if (!sorted.length || !isValidTimeZone(timeZone)) return "Unavailable";
  const current = new Intl.DateTimeFormat("en-GB", {
    timeZone, hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(now);
  const today = sorted.find(value => value > current);
  return today ? `Today at ${today}` : `Tomorrow at ${sorted[0]}`;
}

export function utcTimeForLocal(value: string, timeZone = DEFAULT_TIMEZONE, date = new Date()): string {
  if (!isValidRunTime(value) || !isValidTimeZone(timeZone)) return "Invalid";
  const dateParts = new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => Number(dateParts.find(item => item.type === type)?.value);
  const [hour, minute] = value.split(":").map(Number);
  const desired = Date.UTC(part("year"), part("month") - 1, part("day"), hour, minute);
  let instant = desired;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const actualParts = new Intl.DateTimeFormat("en-US", {
      timeZone, hour12: false, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    }).formatToParts(new Date(instant));
    const actual = (type: Intl.DateTimeFormatPartTypes) => Number(actualParts.find(item => item.type === type)?.value);
    const rendered = Date.UTC(actual("year"), actual("month") - 1, actual("day"), actual("hour") % 24, actual("minute"));
    instant += desired - rendered;
  }
  return new Date(instant).toISOString().slice(11, 16);
}
