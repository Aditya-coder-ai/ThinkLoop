"use client";

import React from "react";
import { Flame, Shield, Clock, Moon, Sun, User as UserIcon, LogOut, Settings as SettingsIcon } from "lucide-react";
import { StreakState, UserProfile } from "../types";

interface Props {
  user: UserProfile;
  streak: StreakState;
  focusMinutes: number;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenPreferences: () => void;
  onSignOut: () => void;
}

export function WorkspaceHeader({
  user,
  streak,
  focusMinutes,
  theme,
  onToggleTheme,
  onOpenPreferences,
  onSignOut,
}: Props) {
  return (
    <header className="workspace-header">
      <div className="header-left">
        <a href="/" className="wordmark" title="Back to Thinkloop Home">
          <span className="wordmark-symbol" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>thinkloop</span>
        </a>

        <div className="topic-badge">
          <span className="badge-dot" />
          <span className="badge-text">Physics: Newtonian Mechanics</span>
        </div>
      </div>

      <div className="header-right">
        {/* Streak Pill */}
        <div className={`metric-pill streak-pill ${streak.atRisk ? "at-risk" : ""}`} title={`Current Streak: ${streak.current} days`}>
          <Flame size={16} className="pill-icon flame-icon" />
          <span className="pill-val">{streak.current}d</span>
          {streak.freezesAvailable > 0 && (
            <span className="freeze-tag" title={`${streak.freezesAvailable} Streak Freeze available`}>
              <Shield size={12} />
              <span>{streak.freezesAvailable}</span>
            </span>
          )}
        </div>

        {/* Focus Study Minutes Today */}
        <div className="metric-pill focus-pill" title="Today's focused study minutes">
          <Clock size={15} className="pill-icon" />
          <span className="pill-val">{focusMinutes}m</span>
          <span className="pill-sub">/ {user.dailyGoalMinutes}m</span>
        </div>

        {/* Theme Toggle */}
        <button
          className="theme-icon-button"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
        >
          {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
        </button>

        {/* Preferences */}
        <button
          className="theme-icon-button"
          onClick={onOpenPreferences}
          title="User Preferences & Settings"
          aria-label="Settings"
        >
          <SettingsIcon size={16} />
        </button>

        {/* Profile Pill */}
        <div className="profile-pill">
          <div className="profile-avatar">
            <UserIcon size={14} />
          </div>
          <span className="profile-name">{user.name}</span>
          <button
            onClick={onSignOut}
            className="logout-button"
            title="Sign out / Switch account"
            aria-label="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </header>
  );
}
