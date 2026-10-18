"use client";

import React, { useState, useEffect } from "react";
import { Play, Pause, Square, CheckCircle, RotateCcw, Coffee, BookOpen } from "lucide-react";
import { ConceptItem, FocusSessionState } from "../types";
import { CURRICULUM_CONCEPTS } from "../curriculum";
import { authStore } from "../../../lib/auth";

interface Props {
  onSessionCompleted: (minutes: number) => void;
}

export function FocusTimerView({ onSessionCompleted }: Props) {
  const [selectedConcept, setSelectedConcept] = useState<ConceptItem>(CURRICULUM_CONCEPTS[4]);
  const [session, setSession] = useState<FocusSessionState>({
    id: "focus_1",
    status: "idle",
    plannedSeconds: 25 * 60,
    elapsedSeconds: 0,
    cycleCount: 0,
  });

  const [isBreak, setIsBreak] = useState(false);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    let timerId: number | null = null;
    if (session.status === "running") {
      interval = setInterval(() => {
        setSession((prev) => {
          const nextElapsed = prev.elapsedSeconds + 1;
          if (nextElapsed >= prev.plannedSeconds) {
            return {
              ...prev,
              status: "completed",
              elapsedSeconds: prev.plannedSeconds,
            };
          }
          return { ...prev, elapsedSeconds: nextElapsed };
        });
      }, 1000);
      timerId = interval as unknown as number;
      authStore.registerActiveTimer(timerId, () => {
        if (interval) clearInterval(interval);
      });
    }

    return () => {
      if (interval) clearInterval(interval);
      if (timerId !== null) authStore.unregisterActiveTimer(timerId);
    };
  }, [session.status]);

  const handleStart = () => {
    setSession({
      id: `focus_${Date.now()}`,
      conceptId: selectedConcept.id,
      conceptTitle: selectedConcept.title,
      status: "running",
      plannedSeconds: isBreak ? 5 * 60 : 25 * 60,
      elapsedSeconds: 0,
      cycleCount: session.cycleCount,
    });
  };

  const handlePause = () => {
    setSession((prev) => ({ ...prev, status: "paused" }));
  };

  const handleResume = () => {
    setSession((prev) => ({ ...prev, status: "running" }));
  };

  const handleComplete = () => {
    const creditedMins = Math.round(session.elapsedSeconds / 60);
    setSession((prev) => ({ ...prev, status: "completed" }));
    if (!isBreak && creditedMins > 0) {
      onSessionCompleted(creditedMins);
    }
  };

  const handleAbandon = () => {
    setSession((prev) => ({ ...prev, status: "idle", elapsedSeconds: 0 }));
  };

  const handleStartBreak = () => {
    setIsBreak(true);
    setSession({
      id: `break_${Date.now()}`,
      status: "running",
      plannedSeconds: 5 * 60,
      elapsedSeconds: 0,
      isBreak: true,
      cycleCount: session.cycleCount + 1,
    });
  };

  const remaining = session.plannedSeconds - session.elapsedSeconds;
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const progressPct = (session.elapsedSeconds / session.plannedSeconds) * 100;

  return (
    <div className="focus-view-container">
      <div className="focus-hero-card">
        <span className="section-kicker">SERVER-AUTHORITATIVE STUDY TIMER</span>
        <h2>{isBreak ? "Recharge & Digest" : "Deep Conceptual Focus"}</h2>
        <p>
          {isBreak
            ? "Take a breath. Learning consolidates when the mind pauses between deliberate practice loops."
            : "Eliminate distractions. Elapsed time is strictly tracked and qualifies for daily streak milestones."}
        </p>
      </div>

      <div className="focus-timer-body">
        {/* Concept Selector if not running */}
        {session.status === "idle" && (
          <div className="focus-concept-select-bar">
            <BookOpen size={16} className="text-olive" />
            <span>Target Concept:</span>
            <select
              className="focus-concept-dropdown"
              value={selectedConcept.id}
              onChange={(e) => {
                const found = CURRICULUM_CONCEPTS.find((c) => c.id === e.target.value);
                if (found) setSelectedConcept(found);
              }}
            >
              {CURRICULUM_CONCEPTS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Circular Display */}
        <div className="timer-circle-container">
          <svg className="timer-svg" viewBox="0 0 240 240">
            <circle className="timer-track" cx="120" cy="120" r="104" />
            <circle
              className="timer-indicator"
              cx="120"
              cy="120"
              r="104"
              strokeDasharray={2 * Math.PI * 104}
              strokeDashoffset={2 * Math.PI * 104 * (1 - progressPct / 100)}
            />
          </svg>

          <div className="timer-clock-digits">
            <span className="digits-main">
              {String(mins).padStart(2, "0")}:{String(secs).padStart(2, "0")}
            </span>
            <span className="digits-label">
              {session.status === "completed"
                ? "Cycle Finished"
                : session.status === "running"
                ? isBreak
                  ? "Break Running"
                  : "Studying"
                : session.status === "paused"
                ? "Paused"
                : isBreak
                ? "5m Break Ready"
                : "25m Sprint Ready"}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="timer-actions-row">
          {session.status === "idle" && (
            <button className="timer-btn-primary" onClick={handleStart}>
              <Play size={18} />
              <span>Start {isBreak ? "Break" : "Focus Session"}</span>
            </button>
          )}

          {session.status === "running" && (
            <>
              <button className="timer-btn-secondary" onClick={handlePause}>
                <Pause size={18} />
                <span>Pause</span>
              </button>
              <button className="timer-btn-primary" onClick={handleComplete}>
                <CheckCircle size={18} />
                <span>Complete</span>
              </button>
              <button className="timer-btn-ghost" onClick={handleAbandon} title="Abandon session">
                <Square size={16} />
              </button>
            </>
          )}

          {session.status === "paused" && (
            <>
              <button className="timer-btn-primary" onClick={handleResume}>
                <Play size={18} />
                <span>Resume</span>
              </button>
              <button className="timer-btn-secondary" onClick={handleComplete}>
                <CheckCircle size={18} />
                <span>Finish Early</span>
              </button>
              <button className="timer-btn-ghost" onClick={handleAbandon}>
                <RotateCcw size={16} />
              </button>
            </>
          )}

          {session.status === "completed" && (
            <div className="completed-prompt-box">
              <CheckCircle size={24} className="text-olive" />
              <div>
                <strong>Focus Session Finished!</strong>
                <p>Credited {Math.round(session.elapsedSeconds / 60)} minutes to daily streak.</p>
              </div>
              <button className="timer-btn-primary" onClick={handleStartBreak}>
                <Coffee size={16} />
                <span>Take 5m Break</span>
              </button>
              <button
                className="timer-btn-ghost"
                onClick={() => {
                  setIsBreak(false);
                  setSession((prev) => ({ ...prev, status: "idle", elapsedSeconds: 0 }));
                }}
              >
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
