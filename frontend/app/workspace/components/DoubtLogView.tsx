"use client";

import React, { useState } from "react";
import { HelpCircle, CheckCircle2, Plus, MessageSquare, BookOpen, Sparkles, X } from "lucide-react";
import { DoubtItem, ConceptItem } from "../types";
import { CURRICULUM_CONCEPTS } from "../curriculum";

interface Props {
  doubts: DoubtItem[];
  onAddDoubt: (conceptId: string, title: string, body: string) => void;
  onResolveDoubt: (doubtId: string, note: string) => void;
  onAskTutor: (doubt: DoubtItem) => void;
}

export function DoubtLogView({
  doubts,
  onAddDoubt,
  onResolveDoubt,
  onAskTutor,
}: Props) {
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("all");
  const [showCaptureModal, setShowCaptureModal] = useState(false);
  const [resolvingDoubt, setResolvingDoubt] = useState<DoubtItem | null>(null);

  // New doubt form state
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [newConceptId, setNewConceptId] = useState("newtons_first_law");

  // Resolution note state
  const [resolutionNote, setResolutionNote] = useState("");

  const filtered = doubts.filter((d) => {
    if (filter === "all") return true;
    if (filter === "open") return d.status === "open" || d.status === "in_progress";
    return d.status === "resolved";
  });

  const handleCaptureSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    onAddDoubt(newConceptId, newTitle.trim(), newBody.trim());
    setNewTitle("");
    setNewBody("");
    setShowCaptureModal(false);
  };

  const handleResolveSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingDoubt || !resolutionNote.trim()) return;
    onResolveDoubt(resolvingDoubt.id, resolutionNote.trim());
    setResolutionNote("");
    setResolvingDoubt(null);
  };

  return (
    <div className="doubts-view-container">
      {/* Banner */}
      <div className="doubts-hero-card">
        <div>
          <span className="section-kicker">SOCRATIC INQUIRY LOG</span>
          <h2>Doubt Log & Clarity Ledger</h2>
          <p>
            Capture snags the moment confusion strikes. Work through them with the Socratic mentor, then solidify your understanding by writing the resolution in your own words.
          </p>
        </div>

        <button className="button-primary" onClick={() => setShowCaptureModal(true)}>
          <Plus size={16} />
          <span>Capture a Doubt</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="doubts-filter-bar">
        <button
          className={`filter-tab ${filter === "all" ? "active" : ""}`}
          onClick={() => setFilter("all")}
        >
          All ({doubts.length})
        </button>
        <button
          className={`filter-tab ${filter === "open" ? "active" : ""}`}
          onClick={() => setFilter("open")}
        >
          Open & In Progress ({doubts.filter((d) => d.status !== "resolved").length})
        </button>
        <button
          className={`filter-tab ${filter === "resolved" ? "active" : ""}`}
          onClick={() => setFilter("resolved")}
        >
          Resolved ({doubts.filter((d) => d.status === "resolved").length})
        </button>
      </div>

      {/* Doubts List */}
      <div className="doubts-grid">
        {filtered.length === 0 ? (
          <div className="empty-doubts-card">
            <HelpCircle size={32} className="text-olive" />
            <h3>No doubts in this view</h3>
            <p>Whenever you hit friction during study, capture it here to explore with the Socratic mentor.</p>
          </div>
        ) : (
          filtered.map((doubt) => {
            const concept = CURRICULUM_CONCEPTS.find((c) => c.id === doubt.conceptId);

            return (
              <div key={doubt.id} className={`doubt-item-card ${doubt.status}`}>
                <div className="doubt-top-row">
                  <span className={`status-pill ${doubt.status}`}>
                    {doubt.status === "resolved" ? "Resolved" : "Open Doubt"}
                  </span>
                  <span className="doubt-date">{doubt.createdAt}</span>
                </div>

                <h3 className="doubt-title">{doubt.title}</h3>
                {doubt.body && <p className="doubt-body">{doubt.body}</p>}

                <div className="doubt-concept-tag">
                  <BookOpen size={13} className="text-olive" />
                  <span>{concept ? concept.title : doubt.conceptId}</span>
                </div>

                {doubt.status === "resolved" && doubt.resolutionNote && (
                  <div className="doubt-resolution-box">
                    <span className="res-kicker">IN YOUR OWN WORDS:</span>
                    <p className="res-text">&ldquo;{doubt.resolutionNote}&rdquo;</p>
                  </div>
                )}

                <div className="doubt-card-actions">
                  {doubt.status !== "resolved" ? (
                    <>
                      <button className="button-outline-sm" onClick={() => onAskTutor(doubt)}>
                        <MessageSquare size={14} />
                        <span>Work Through with Tutor</span>
                      </button>
                      <button
                        className="button-primary-sm"
                        onClick={() => setResolvingDoubt(doubt)}
                      >
                        <CheckCircle2 size={14} />
                        <span>Mark Resolved</span>
                      </button>
                    </>
                  ) : (
                    <span className="resolved-checkmark">
                      <CheckCircle2 size={16} className="text-olive" />
                      <span>Resolution verified</span>
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Modal: Capture Doubt */}
      {showCaptureModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Capture a Concept Doubt</h3>
              <button className="modal-close-btn" onClick={() => setShowCaptureModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCaptureSubmit}>
              <div className="form-group">
                <label>Question or Confusion Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Why does acceleration remain 9.8 at the top of a throw?"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Related Concept</label>
                <select
                  value={newConceptId}
                  onChange={(e) => setNewConceptId(e.target.value)}
                >
                  {CURRICULUM_CONCEPTS.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Details / What was your line of reasoning?</label>
                <textarea
                  rows={3}
                  placeholder="I thought that if velocity equals zero, there is no push or pull..."
                  value={newBody}
                  onChange={(e) => setNewBody(e.target.value)}
                />
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => setShowCaptureModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="button-primary">
                  Capture Doubt
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Resolve Doubt with Own Words */}
      {resolvingDoubt && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Resolve Doubt: &ldquo;{resolvingDoubt.title}&rdquo;</h3>
              <button className="modal-close-btn" onClick={() => setResolvingDoubt(null)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleResolveSubmit}>
              <div className="form-group">
                <label>
                  Explain the resolution <strong>in your own words</strong> *
                </label>
                <p className="form-hint">
                  The Socratic rule: A doubt is only resolved when you can articulate the underlying physics concept yourself.
                </p>
                <textarea
                  required
                  rows={4}
                  placeholder="e.g. Gravity is a continuous force from Earth that acts regardless of speed. At the peak, velocity is zero only for a split second as direction changes..."
                  value={resolutionNote}
                  onChange={(e) => setResolutionNote(e.target.value)}
                />
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => setResolvingDoubt(null)}
                >
                  Cancel
                </button>
                <button type="submit" className="button-primary">
                  Confirm Resolution
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
