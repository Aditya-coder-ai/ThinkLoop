"use client";

import React from "react";
import { Brain, CheckCircle2, AlertTriangle, ShieldCheck, HelpCircle, Compass, Sparkles } from "lucide-react";
import { ConceptItem, StrategyKind } from "../types";
import { STRATEGY_EXPLANATIONS, CURRICULUM_MISCONCEPTIONS } from "../curriculum";

interface Props {
  activeConcept: ConceptItem;
  masteryPct: number;
  currentStrategy?: StrategyKind;
  detectedMisconceptionId?: string;
  verifiedMath?: boolean;
  onSelectConflictPrompt?: (prompt: string) => void;
  onLogDoubt?: () => void;
}

export function CognitiveDiagnosticPanel({
  activeConcept,
  masteryPct,
  currentStrategy = "guided_hint",
  detectedMisconceptionId,
  verifiedMath = true,
  onSelectConflictPrompt,
  onLogDoubt,
}: Props) {
  const strategyInfo = STRATEGY_EXPLANATIONS[currentStrategy] || STRATEGY_EXPLANATIONS.guided_hint;
  const detectedMisc = detectedMisconceptionId
    ? CURRICULUM_MISCONCEPTIONS.find((m) => m.id === detectedMisconceptionId)
    : null;

  return (
    <aside className="diagnostic-panel" aria-label="Cognitive Diagnostic Panel">
      <div className="panel-header">
        <div className="panel-title-row">
          <Brain size={18} className="panel-icon text-olive" />
          <h3>Cognitive Diagnosis</h3>
        </div>
        <span className="live-pulse" title="Live telemetry active">
          <span className="pulse-dot" /> Live
        </span>
      </div>

      {/* 1. Concept Mastery Meter */}
      <div className="diagnostic-card mastery-card">
        <div className="card-top">
          <span className="card-kicker">Concept Mastery</span>
          <span className="mastery-val">{Math.round(masteryPct * 100)}%</span>
        </div>
        <div className="progress-bar-bg">
          <div
            className="progress-bar-fill"
            style={{ width: `${Math.min(Math.max(masteryPct * 100, 5), 100)}%` }}
          />
        </div>
        <p className="card-subtext">
          {masteryPct >= 0.7
            ? "Mastered • Moving to Socratic challenge phase"
            : masteryPct >= 0.4
            ? "Practicing • Refining foundational model"
            : "Novice • Guided hints & worked examples active"}
        </p>
      </div>

      {/* 2. Active Strategy Rule */}
      <div className="diagnostic-card strategy-card">
        <div className="card-top">
          <span className="card-kicker">Pedagogical Strategy</span>
          <span className={`strategy-pill ${currentStrategy}`}>
            <Compass size={13} />
            <span>{strategyInfo.label}</span>
          </span>
        </div>
        <p className="strategy-desc">{strategyInfo.explanation}</p>
        <div className="card-footer-note">
          <ShieldCheck size={13} className="text-olive" />
          <span>Strategy chosen by Python rule engine, not the LLM.</span>
        </div>
      </div>

      {/* 3. Misconception Alert if Present */}
      {detectedMisc ? (
        <div className="diagnostic-card misconception-card alert">
          <div className="card-top">
            <span className="card-kicker text-clay">Misconception Detected</span>
            <AlertTriangle size={15} className="text-clay" />
          </div>
          <strong className="misc-statement">&ldquo;{detectedMisc.statement}&rdquo;</strong>
          <p className="misc-correct">
            <strong>Key Insight:</strong> {detectedMisc.correctIdea}
          </p>
          {onSelectConflictPrompt && (
            <button
              className="conflict-action-button"
              onClick={() => onSelectConflictPrompt(detectedMisc.conflictPrompt)}
            >
              <Sparkles size={14} />
              <span>Explore Conflict Question</span>
            </button>
          )}
        </div>
      ) : (
        <div className="diagnostic-card misconception-card clean">
          <div className="card-top">
            <span className="card-kicker">Mental Model Health</span>
            <CheckCircle2 size={15} className="text-olive" />
          </div>
          <p className="clean-desc">
            No active misconception detected. Reasoning aligns with Newton&apos;s laws.
          </p>
        </div>
      )}

      {/* 4. Deterministic Math Verifier */}
      <div className="diagnostic-card verifier-card">
        <div className="card-top">
          <span className="card-kicker">Mathematical Verifier</span>
          <span className="verifier-status">
            {verifiedMath ? "Exact • Symbolic" : "Unverified"}
          </span>
        </div>
        <p className="verifier-sub">
          Formulas and numeric bounds are evaluated deterministically in Python. The LLM never decides mathematical correctness.
        </p>
      </div>

      {/* 5. Quick Actions */}
      <div className="diagnostic-actions">
        {onLogDoubt && (
          <button className="button-outline-sm" onClick={onLogDoubt}>
            <HelpCircle size={14} />
            <span>Capture this as a Doubt</span>
          </button>
        )}
      </div>
    </aside>
  );
}
