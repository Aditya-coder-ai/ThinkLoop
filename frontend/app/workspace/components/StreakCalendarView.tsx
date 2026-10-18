"use client";

import React, { useState } from "react";
import { Flame, Shield, Calendar as CalendarIcon, Info, Check, AlertCircle } from "lucide-react";
import { StreakState, CalendarHeatmapDay } from "../types";

interface Props {
  streak: StreakState;
  calendarDays: CalendarHeatmapDay[];
}

export function StreakCalendarView({ streak, calendarDays }: Props) {
  const [hoveredDay, setHoveredDay] = useState<CalendarHeatmapDay | null>(null);

  return (
    <div className="streak-view-container">
      {/* Top Banner Stats */}
      <div className="streak-hero-card">
        <div className="streak-hero-left">
          <span className="section-kicker">DAILY CONSISTENCY</span>
          <div className="streak-headline">
            <Flame size={32} className="flame-big text-clay" />
            <h2>
              {streak.current} <span>Day Streak</span>
            </h2>
          </div>
          <p className="streak-subtitle">
            {streak.todayActive
              ? "Qualifying activity logged today! Your streak is secured."
              : streak.atRisk
              ? "No qualifying activity logged yet today. Complete 15 min focus or 1 tutor turn to keep your streak!"
              : "Keep showing your thinking daily to build lasting conceptual memory."}
          </p>
        </div>

        <div className="streak-stat-pills">
          <div className="streak-stat-pill">
            <span className="stat-label">Longest Streak</span>
            <strong className="stat-num">{streak.longest} days</strong>
          </div>

          <div className="streak-stat-pill">
            <span className="stat-label">Streak Freezes</span>
            <strong className="stat-num">
              <Shield size={16} className="text-olive" />
              {streak.freezesAvailable} Banked
            </strong>
          </div>

          <div className={`streak-stat-pill ${streak.todayActive ? "active-green" : "pending"}`}>
            <span className="stat-label">Today&apos;s Status</span>
            <strong className="stat-num">
              {streak.todayActive ? "Secured" : "At Risk"}
            </strong>
          </div>
        </div>
      </div>

      {/* Heatmap Section */}
      <div className="heatmap-section-card">
        <div className="heatmap-header">
          <div className="heatmap-title">
            <CalendarIcon size={18} className="text-olive" />
            <h3>Monthly Activity Heatmap</h3>
          </div>
          <div className="heatmap-legend">
            <span className="legend-text">Less</span>
            <span className="legend-square level-0" />
            <span className="legend-square level-1" />
            <span className="legend-square level-2" />
            <span className="legend-square level-3" />
            <span className="legend-square level-4" />
            <span className="legend-text">More</span>
          </div>
        </div>

        {/* Heatmap Grid */}
        <div className="calendar-grid">
          {calendarDays.map((d) => (
            <div
              key={d.date}
              className={`calendar-cell level-${d.level} ${d.freezeUsed ? "freeze-used" : ""} ${
                d.date === new Date().toISOString().split("T")[0] ? "is-today" : ""
              }`}
              onMouseEnter={() => setHoveredDay(d)}
              onMouseLeave={() => setHoveredDay(null)}
            >
              <span className="cell-date-num">{parseInt(d.date.split("-")[2], 10)}</span>
              {d.freezeUsed && <Shield size={10} className="cell-freeze-icon" />}
            </div>
          ))}
        </div>

        {/* Tooltip on Hover */}
        {hoveredDay && (
          <div className="heatmap-hover-tooltip">
            <strong>{hoveredDay.date}</strong>
            <p>
              {hoveredDay.minutes} study minutes logged •{" "}
              {hoveredDay.freezeUsed
                ? "Protected by Streak Freeze"
                : hoveredDay.isQualifying
                ? "Qualifying Day"
                : "Rest / Inactive"}
            </p>
          </div>
        )}
      </div>

      {/* Streak Protection Rules */}
      <div className="streak-rules-grid">
        <div className="rule-card">
          <div className="rule-top">
            <Shield size={16} className="text-olive" />
            <h4>Auto-Freeze Protection</h4>
          </div>
          <p>
            You earn 1 Streak Freeze for every 7 days of consecutive study (max 2). A freeze automatically covers 1 missed day without breaking your streak.
          </p>
        </div>

        <div className="rule-card">
          <div className="rule-top">
            <Check size={16} className="text-olive" />
            <h4>Qualifying Activity Invariant</h4>
          </div>
          <p>
            A day counts as active when you complete at least 15 minutes of Pomodoro focus, or submit 1 gradable Socratic dialogue response.
          </p>
        </div>

        <div className="rule-card">
          <div className="rule-top">
            <AlertCircle size={16} className="text-clay" />
            <h4>Server-Authoritative Clock</h4>
          </div>
          <p>
            Streak dates and times are evaluated strictly in your selected timezone using our backend server clock, never client device timestamps.
          </p>
        </div>
      </div>
    </div>
  );
}
