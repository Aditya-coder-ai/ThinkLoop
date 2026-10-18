"use client";

import React, { useState } from "react";
import { CheckCircle2, Compass, ArrowRight, Layers, Sparkles, Filter } from "lucide-react";
import { ConceptMastery, ConceptItem } from "../types";
import { CURRICULUM_CONCEPTS } from "../curriculum";

interface Props {
  masteryList: ConceptMastery[];
  onStartSession: (concept: ConceptItem) => void;
}

export function MasteryGraphView({ masteryList, onStartSession }: Props) {
  const [filter, setFilter] = useState<"all" | "mastered" | "learning" | "unseen">("all");

  const filtered = masteryList.filter((m) => {
    if (filter === "all") return true;
    return m.state === filter;
  });

  const masteredCount = masteryList.filter((m) => m.state === "mastered").length;
  const learningCount = masteryList.filter((m) => m.state === "learning").length;

  return (
    <div className="mastery-view-container">
      {/* Top Banner Stats */}
      <div className="mastery-banner">
        <div>
          <span className="section-kicker">BAYESIAN KNOWLEDGE TRACING</span>
          <h2>Concept Knowledge Graph</h2>
          <p>
            Your mastery score reflects evidence from Socratic dialogue and verification — not just multiple-choice test scores.
          </p>
        </div>

        <div className="mastery-stats-row">
          <div className="stat-box">
            <span className="stat-number">{masteredCount}</span>
            <span className="stat-label">Mastered</span>
          </div>
          <div className="stat-box">
            <span className="stat-number">{learningCount}</span>
            <span className="stat-label">In Progress</span>
          </div>
          <div className="stat-box">
            <span className="stat-number">{masteryList.length}</span>
            <span className="stat-label">Total Concepts</span>
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="mastery-filter-bar">
        <div className="filter-buttons">
          <button
            className={`filter-tab ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All Concepts ({masteryList.length})
          </button>
          <button
            className={`filter-tab ${filter === "mastered" ? "active" : ""}`}
            onClick={() => setFilter("mastered")}
          >
            Mastered ({masteredCount})
          </button>
          <button
            className={`filter-tab ${filter === "learning" ? "active" : ""}`}
            onClick={() => setFilter("learning")}
          >
            In Progress ({learningCount})
          </button>
          <button
            className={`filter-tab ${filter === "unseen" ? "active" : ""}`}
            onClick={() => setFilter("unseen")}
          >
            Unseen ({masteryList.length - masteredCount - learningCount})
          </button>
        </div>
      </div>

      {/* Concept Cards Grid */}
      <div className="mastery-cards-grid">
        {filtered.map((item) => {
          const concept = CURRICULUM_CONCEPTS.find((c) => c.id === item.conceptId);
          const pct = Math.round(item.pKnown * 100);

          return (
            <div key={item.conceptId} className={`mastery-concept-card ${item.state}`}>
              <div className="card-header">
                <span className={`state-tag ${item.state}`}>
                  {item.state === "mastered" ? "Mastered" : item.state === "learning" ? "In Progress" : "Unseen"}
                </span>
                <span className="attempts-count">{item.attempts} turns logged</span>
              </div>

              <h3 className="concept-title">{item.title}</h3>
              <p className="concept-desc">{concept?.description}</p>

              {/* Progress bar */}
              <div className="concept-progress-section">
                <div className="progress-labels">
                  <span>BKT Mastery Probability</span>
                  <strong>{pct}%</strong>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${Math.max(pct, 5)}%` }} />
                </div>
              </div>

              {/* Prerequisites */}
              {item.prerequisites.length > 0 && (
                <div className="prerequisites-list">
                  <span className="prereq-label">Requires:</span>
                  {item.prerequisites.map((p) => {
                    const prereq = CURRICULUM_CONCEPTS.find((c) => c.id === p);
                    return (
                      <span key={p} className="prereq-pill">
                        {prereq ? prereq.title : p}
                      </span>
                    );
                  })}
                </div>
              )}

              {/* Action Button */}
              <button
                className="start-session-button"
                onClick={() => concept && onStartSession(concept)}
              >
                <span>Practice in Socratic Tutor</span>
                <ArrowRight size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
