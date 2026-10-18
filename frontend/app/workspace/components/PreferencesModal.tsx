"use client";

import React, { useState } from "react";
import { X, Globe, Clock, Mic, Check } from "lucide-react";
import { UserProfile } from "../types";

interface Props {
  user: UserProfile;
  onSave: (updated: UserProfile) => void;
  onClose: () => void;
}

const COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Los_Angeles",
  "America/Chicago",
  "Europe/London",
  "Europe/Paris",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Australia/Sydney",
];

export function PreferencesModal({ user, onSave, onClose }: Props) {
  const [name, setName] = useState(user.name);
  const [timezone, setTimezone] = useState(user.timezone);
  const [dailyGoal, setDailyGoal] = useState(user.dailyGoalMinutes);
  const [voiceEnabled, setVoiceEnabled] = useState(user.voiceEnabled);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      ...user,
      name: name.trim() || user.name,
      timezone,
      dailyGoalMinutes: dailyGoal,
      voiceEnabled,
    });
    onClose();
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div className="modal-header">
          <h3>User Preferences & Clock</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Learner Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />
          </div>

          <div className="form-group">
            <label>
              <Globe size={14} className="inline mr-1 text-olive" />
              IANA Timezone (Authoritative Streak Clock)
            </label>
            <p className="form-hint">
              All streaks and activity days are strictly evaluated relative to this timezone.
            </p>
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>
              <Clock size={14} className="inline mr-1 text-olive" />
              Daily Study Goal: <strong>{dailyGoal} minutes</strong>
            </label>
            <input
              type="range"
              min={10}
              max={120}
              step={5}
              value={dailyGoal}
              onChange={(e) => setDailyGoal(Number(e.target.value))}
            />
            <div className="range-marks">
              <span>15m (Qualifying)</span>
              <span>30m (Target)</span>
              <span>60m (Intensive)</span>
            </div>
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={voiceEnabled}
                onChange={(e) => setVoiceEnabled(e.target.checked)}
              />
              <Mic size={15} className="text-olive" />
              <span>Enable Voice Mode audio streaming</span>
            </label>
          </div>

          <div className="modal-footer">
            <button type="button" className="button-ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button-primary">
              <Check size={16} />
              <span>Save Preferences</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
