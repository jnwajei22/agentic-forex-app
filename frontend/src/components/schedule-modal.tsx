"use client";

import { useMemo, useState } from "react";
import AppModal from "./app-modal";
import {
  DEFAULT_RUN_TIMES,
  DEFAULT_TIMEZONE,
  isValidTimeZone,
  nextLocalRunLabel,
  sortRunTimes,
  utcTimeForLocal,
  validateRunTimes,
} from "@/lib/schedule";

type ScheduleProfile = {
  name: string;
  accountAlias: string;
  strategy: string;
  executionMode: string;
};

export type ScheduleValue = {
  timezone: string;
  local_times: string[];
  enabled: boolean;
};

type ScheduleModalProps = {
  open: boolean;
  profile: ScheduleProfile;
  initial?: { timezone?: string; times?: string[]; enabled?: boolean };
  saving: boolean;
  onClose: () => void;
  onSave: (value: ScheduleValue) => Promise<void> | void;
};

export default function ScheduleModal({ open, profile, initial, saving, onClose, onSave }: ScheduleModalProps) {
  const [timezone, setTimezone] = useState(initial?.timezone ?? DEFAULT_TIMEZONE);
  const [times, setTimes] = useState(initial?.times?.length ? initial.times : DEFAULT_RUN_TIMES);
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const validation = useMemo(() => validateRunTimes(times), [times]);
  const timezoneError = isValidTimeZone(timezone) ? null : "Choose a valid timezone.";
  const sorted = useMemo(() => sortRunTimes(times), [times]);

  return (
    <AppModal open={open} onClose={onClose} title="Schedule Autonomous Runs"
      description="Configure durable local run times. Scheduling cannot arm a profile or bypass the kill switch.">
      <form onSubmit={event => {
        event.preventDefault();
        if (validation || timezoneError) return;
        void onSave({ timezone, local_times: sorted, enabled });
      }}>
        <dl className="modal-summary">
          <div><dt>Profile</dt><dd>{profile.name}</dd></div>
          <div><dt>Bound account</dt><dd>{profile.accountAlias}</dd></div>
          <div><dt>Strategy</dt><dd>{profile.strategy}</dd></div>
          <div><dt>Execution mode</dt><dd>{profile.executionMode}</dd></div>
        </dl>
        <div className="field">
          <label htmlFor="schedule-timezone">Timezone</label>
          <select id="schedule-timezone" value={timezone} onChange={event => setTimezone(event.target.value)}>
            <option value={DEFAULT_TIMEZONE}>America/Chicago</option>
            <option value="America/New_York">America/New_York</option>
            <option value="UTC">UTC</option>
          </select>
        </div>
        <fieldset className="time-editor">
          <legend>Run times</legend>
          {times.map((time, index) => (
            <div className="time-row" key={`${index}-${time}`}>
              <label className="sr-only" htmlFor={`run-time-${index}`}>Run time {index + 1}</label>
              <input id={`run-time-${index}`} type="time" value={time} onChange={event => {
                setTimes(current => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item));
              }} />
              <span>{utcTimeForLocal(time, timezone)} UTC</span>
              <button className="button text-danger" type="button" onClick={() => {
                setTimes(current => current.filter((_, itemIndex) => itemIndex !== index));
              }}>Remove Time</button>
            </div>
          ))}
          <button className="button secondary" type="button" onClick={() => setTimes(current => [...current, "12:00"])}>
            Add Time
          </button>
        </fieldset>
        {validation && <div className="inline-error" role="alert">{validation}</div>}
        {timezoneError && <div className="inline-error" role="alert">{timezoneError}</div>}
        <label className="toggle-row">
          <input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />
          <span>{enabled ? "Schedule enabled" : "Schedule paused"}</span>
        </label>
        {!validation && <div className="schedule-preview">
          <strong>Schedule preview</strong>
          <p>Local: {sorted.join(", ")} {timezone}</p>
          <p>UTC: {sorted.map(time => utcTimeForLocal(time, timezone)).join(", ")}</p>
          <p>Next local run: {nextLocalRunLabel(sorted, timezone)}</p>
        </div>}
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="button" type="submit" disabled={Boolean(validation || timezoneError) || saving}>
            {saving ? "Saving Schedule…" : "Save Schedule"}
          </button>
        </div>
      </form>
    </AppModal>
  );
}
