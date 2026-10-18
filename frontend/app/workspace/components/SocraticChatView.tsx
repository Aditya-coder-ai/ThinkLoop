"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, BookOpen, MessageSquare, ChevronDown } from "lucide-react";
import { ConceptItem, TurnMessage } from "../types";
import { CURRICULUM_CONCEPTS } from "../curriculum";
import { CognitiveDiagnosticPanel } from "./CognitiveDiagnosticPanel";

interface Props {
  activeConcept: ConceptItem;
  onSelectConcept: (concept: ConceptItem) => void;
  onLogDoubtFromChat: (conceptId: string, title: string) => void;
  onTurnCompleted: () => void;
}

export function SocraticChatView({
  activeConcept,
  onSelectConcept,
  onLogDoubtFromChat,
  onTurnCompleted,
}: Props) {
  const [messages, setMessages] = useState<TurnMessage[]>([
    {
      id: "turn_welcome",
      role: "tutor",
      content: `Welcome to our session on **${activeConcept.title}**!\n\n${activeConcept.description}\n\nTo begin: Imagine a hockey puck sliding across a vast sheet of ice. If you give it one quick tap and let go, what keeps it moving forward, and what forces are acting on it as it glides?`,
      createdAt: "Just now",
      strategy: "guided_hint",
      diagnosis: {
        isCorrect: true,
        confidence: 0.95,
        reasoning: "Session initialization prompt",
        verifiedMath: true,
      },
    },
  ]);

  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [masteryPct, setMasteryPct] = useState(0.58);
  const [currentStrategy, setCurrentStrategy] = useState<any>("guided_hint");
  const [detectedMiscId, setDetectedMiscId] = useState<string | undefined>(undefined);
  const [showConceptDropdown, setShowConceptDropdown] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || isTyping) return;

    const userMsg: TurnMessage = {
      id: `learner_${Date.now()}`,
      role: "learner",
      content: text,
      createdAt: "Just now",
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    // Call Socratic turn
    setTimeout(() => {
      // Analyze learner answer
      const lower = text.toLowerCase();
      let reply = "";
      let newStrat: any = "guided_hint";
      let misc: string | undefined = undefined;
      let newMastery = masteryPct;

      if (
        lower.includes("force keeps it moving") ||
        lower.includes("needs force") ||
        lower.includes("stops without a push") ||
        lower.includes("engine force")
      ) {
        misc = "misc_motion_requires_force";
        newStrat = "cognitive_conflict";
        newMastery = Math.max(0.2, newMastery - 0.08);
        reply =
          "That was common sense for centuries! Aristotle thought the exact same thing. But when the puck is gliding across the ice and your hand is no longer touching it, what object is physically applying that forward force?";
      } else if (lower.includes("friction") && (lower.includes("gravity") || lower.includes("normal"))) {
        newStrat = "socratic_challenge";
        newMastery = Math.min(0.95, newMastery + 0.12);
        reply =
          "Excellent observation! Gravity pulls downward, the ice pushes upward with a normal force, and friction opposes the motion horizontally. Now, if the ice were perfectly frictionless with zero air resistance, when would the puck come to a stop?";
      } else if (lower.includes("never") || lower.includes("forever") || lower.includes("constant velocity")) {
        newStrat = "socratic_challenge";
        newMastery = Math.min(0.95, newMastery + 0.15);
        reply =
          "Spot on. That is the essence of Newton's First Law (Inertia): an object in motion stays in motion with constant velocity unless an unbalanced external force acts on it. You've isolated the core principle!";
      } else {
        newStrat = "guided_hint";
        newMastery = Math.min(0.95, newMastery + 0.05);
        reply =
          "You're circling the right physical intuition. Think about contact: once your stick leaves the puck, the only horizontal force is friction from the ice. Does friction cause the motion, or oppose it?";
      }

      setDetectedMiscId(misc);
      setCurrentStrategy(newStrat);
      setMasteryPct(newMastery);

      const tutorMsg: TurnMessage = {
        id: `tutor_${Date.now()}`,
        role: "tutor",
        content: reply,
        createdAt: "Just now",
        strategy: newStrat,
        diagnosis: {
          isCorrect: !misc,
          confidence: 0.91,
          misconceptionId: misc,
          reasoning: misc ? "Identified motion requires force misconception" : "Sound Newton's 1st law logic",
          verifiedMath: true,
        },
      };

      setMessages((prev) => [...prev, tutorMsg]);
      setIsTyping(false);
      onTurnCompleted();
    }, 1100);
  };

  const handleQuickPrompt = (prompt: string) => {
    handleSend(prompt);
  };

  return (
    <div className="socratic-workspace">
      {/* Main Chat Stream Area */}
      <section className="chat-container">
        {/* Concept Top Bar */}
        <div className="chat-concept-bar">
          <div className="concept-selector-container">
            <button
              className="concept-picker-trigger"
              onClick={() => setShowConceptDropdown(!showConceptDropdown)}
              aria-expanded={showConceptDropdown}
            >
              <BookOpen size={16} className="text-olive" />
              <div className="picker-copy">
                <span className="picker-label">ACTIVE CONCEPT</span>
                <strong>{activeConcept.title}</strong>
              </div>
              <ChevronDown size={15} />
            </button>

            {showConceptDropdown && (
              <div className="concept-dropdown-menu">
                {CURRICULUM_CONCEPTS.map((c) => (
                  <button
                    key={c.id}
                    className={`dropdown-item ${c.id === activeConcept.id ? "selected" : ""}`}
                    onClick={() => {
                      onSelectConcept(c);
                      setShowConceptDropdown(false);
                      setMessages([
                        {
                          id: `turn_welcome_${c.id}`,
                          role: "tutor",
                          content: `Switched focus to **${c.title}**.\n\n${c.description}\n\nLet's test our understanding: What key relationship distinguishes this idea?`,
                          createdAt: "Just now",
                          strategy: "guided_hint",
                          diagnosis: { isCorrect: true, confidence: 0.9, verifiedMath: true },
                        },
                      ]);
                    }}
                  >
                    <div>
                      <strong>{c.title}</strong>
                      <p>{c.description.slice(0, 75)}...</p>
                    </div>
                    <span className="difficulty-pill">Lv {c.difficulty}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="concept-meta">
            <span className="domain-pill">Mechanics</span>
            <span className="difficulty-tag">Difficulty {activeConcept.difficulty}/3</span>
          </div>
        </div>

        {/* Message Stream */}
        <div className="chat-messages-scroll" role="log" aria-live="polite">
          {messages.map((msg) => (
            <div key={msg.id} className={`message-bubble-row ${msg.role}`}>
              <div className="bubble-avatar">
                {msg.role === "tutor" ? (
                  <div className="tutor-avatar-mark">
                    <span>TL</span>
                  </div>
                ) : (
                  <div className="user-avatar-mark">
                    <span>YOU</span>
                  </div>
                )}
              </div>

              <div className="bubble-content-card">
                <div className="bubble-header">
                  <span className="speaker-name">
                    {msg.role === "tutor" ? "Thinkloop Socratic Mentor" : "You"}
                  </span>
                  <span className="message-time">{msg.createdAt}</span>
                </div>

                <div className="bubble-body">
                  {msg.content.split("\n\n").map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </div>

                {msg.role === "tutor" && msg.strategy && (
                  <div className="bubble-footer-badge">
                    <Sparkles size={12} className="text-olive" />
                    <span>Strategy: {msg.strategy.replace("_", " ")}</span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="message-bubble-row tutor is-typing">
              <div className="bubble-avatar">
                <div className="tutor-avatar-mark">
                  <span>TL</span>
                </div>
              </div>
              <div className="typing-indicator-card">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-label">Analyzing mental model...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Pills */}
        <div className="quick-suggestions-row">
          <span className="suggestions-label">Explore thinking:</span>
          <button
            className="suggestion-pill"
            onClick={() => handleQuickPrompt("What forces act on it once it starts moving?")}
          >
            &ldquo;What forces act on it once it moves?&rdquo;
          </button>
          <button
            className="suggestion-pill"
            onClick={() => handleQuickPrompt("I think you need a constant force to keep it going.")}
          >
            &ldquo;I think continuous motion needs a force&rdquo;
          </button>
          <button
            className="suggestion-pill"
            onClick={() => handleQuickPrompt("Without friction, it would glide forever at constant speed.")}
          >
            &ldquo;Without friction, it glides forever&rdquo;
          </button>
        </div>

        {/* Message Input Bar */}
        <div className="chat-input-wrapper">
          <form
            className="chat-input-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              type="text"
              className="chat-text-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Share your reasoning or question about ${activeConcept.title}...`}
              disabled={isTyping}
            />
            <button
              type="submit"
              className="chat-send-button"
              disabled={!input.trim() || isTyping}
              aria-label="Send message"
            >
              <Send size={16} />
            </button>
          </form>
        </div>
      </section>

      {/* Right Cognitive Telemetry Sidebar */}
      <CognitiveDiagnosticPanel
        activeConcept={activeConcept}
        masteryPct={masteryPct}
        currentStrategy={currentStrategy}
        detectedMisconceptionId={detectedMiscId}
        verifiedMath={true}
        onSelectConflictPrompt={(prompt) => handleQuickPrompt(prompt)}
        onLogDoubt={() => onLogDoubtFromChat(activeConcept.id, `Doubt on ${activeConcept.title}`)}
      />
    </div>
  );
}
