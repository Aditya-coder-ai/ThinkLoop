"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Send, Sparkles, BookOpen, ChevronDown, RotateCcw } from "lucide-react";
import { ConceptItem, TurnMessage, StrategyKind } from "../types";
import { CURRICULUM_CONCEPTS, CURRICULUM_MISCONCEPTIONS } from "../curriculum";
import {
  createSession,
  getSession,
  streamTurnMessage,
  sendTurnMessage,
} from "../api";
import { CognitiveDiagnosticPanel } from "./CognitiveDiagnosticPanel";

interface Props {
  activeConcept: ConceptItem;
  onSelectConcept: (concept: ConceptItem) => void;
  onLogDoubtFromChat: (conceptId: string, title: string) => void;
  onTurnCompleted: () => void;
}

function getConceptOpener(concept: ConceptItem): string {
  switch (concept.id) {
    case "newtons_first_law":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: Imagine a spacecraft gliding through deep interstellar space where there is no air, friction, or gravity. If its engines have been turned off for years, what keeps it moving forward, and what forces are acting on it?`;
    case "universal_gravitation":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: The Earth pulls down on an apple with gravitational force. According to gravitational law, does the apple pull upward on the Earth with any force, and how do their magnitudes compare?`;
    case "work_and_kinetic_energy":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: If you push with all your strength against a solid stone wall for an hour without it moving a millimeter, have you done physical work on the wall? Why or why not?`;
    case "acceleration":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: When you throw a ball straight up into the air, it reaches a peak where its velocity is momentarily zero. What is its acceleration at that exact moment?`;
    case "newtons_third_law":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: When a massive truck and a compact car collide head-on, does the truck exert a greater force on the car, or does the car exert an equal force on the truck?`;
    case "free_body_diagrams":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: Consider a heavy textbook resting quietly on a flat wooden desk. What are all the forces acting directly ON the book, and how do they balance?`;
    case "friction_static_and_kinetic":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: Why does it require significantly more force to start sliding a heavy wardrobe from rest than to keep it sliding across the floor?`;
    case "linear_momentum_and_impulse":
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin: Why do modern cars have crumple zones and airbags instead of completely rigid steel frames? How does extending collision duration protect passengers?`;
    default:
      return `Welcome to our session on **${concept.title}**!\n\n${concept.description}\n\nTo begin our exploration: In your own words, what key physical relationship or principle governs ${concept.title}?`;
  }
}

function getExplorePrompts(concept: ConceptItem): string[] {
  switch (concept.id) {
    case "newtons_first_law":
      return [
        "What forces act on it once it starts moving?",
        "I think continuous motion requires a continuous force.",
        "Without friction, it glides forever at constant speed.",
      ];
    case "universal_gravitation":
      return [
        "Does Earth pull harder on the Moon than the Moon on Earth?",
        "Why do astronauts on the space station feel weightless?",
        "How does gravitational pull change if distance doubles?",
      ];
    case "work_and_kinetic_energy":
      return [
        "Is work done if an object does not displace?",
        "Why does stopping distance quadruple when speed doubles?",
        "Can work done by a force be negative?",
      ];
    case "acceleration":
      return [
        "Is acceleration zero at the peak of flight?",
        "Can velocity be negative while acceleration is positive?",
        "What is the difference between speed and acceleration?",
      ];
    case "newtons_third_law":
      return [
        "Why don't action and reaction forces cancel out?",
        "If forces are equal, why does the smaller object accelerate more?",
        "How does a rocket accelerate in the vacuum of space?",
      ];
    case "friction_static_and_kinetic":
      return [
        "Why is static friction greater than kinetic friction?",
        "Does friction always oppose motion or can it cause it?",
        "How does the normal force affect friction?",
      ];
    default:
      return [
        `What are the external forces in ${concept.title}?`,
        `How does mass affect this relationship?`,
        `What happens in an idealized, frictionless scenario?`,
      ];
  }
}

export function SocraticChatView({
  activeConcept,
  onSelectConcept,
  onLogDoubtFromChat,
  onTurnCompleted,
}: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<TurnMessage[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [masteryPct, setMasteryPct] = useState(0.45);
  const [currentStrategy, setCurrentStrategy] = useState<StrategyKind>("guided_hint");
  const [detectedMiscId, setDetectedMiscId] = useState<string | undefined>(undefined);
  const [showConceptDropdown, setShowConceptDropdown] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // Initialize or resume session whenever activeConcept changes
  const initSession = useCallback(async (concept: ConceptItem) => {
    setMessages([
      {
        id: `welcome_${concept.id}`,
        role: "tutor",
        content: getConceptOpener(concept),
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
    setCurrentStrategy("guided_hint");
    setDetectedMiscId(undefined);

    try {
      const newSessionId = await createSession(concept.id);
      setSessionId(newSessionId);
    } catch (err) {
      console.warn("Failed to create session on backend:", err);
      setSessionId(`session_local_${Date.now()}`);
    }
  }, []);

  useEffect(() => {
    initSession(activeConcept);
  }, [activeConcept, initSession]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || isTyping) return;

    const userMsg: TurnMessage = {
      id: `learner_${Date.now()}`,
      role: "learner",
      content: text,
      createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    const tutorMsgId = `tutor_${Date.now()}`;
    let streamedContent = "";
    let hasAddedTutorMessage = false;

    const activeSession = sessionId || (await createSession(activeConcept.id));
    if (!sessionId) {
      setSessionId(activeSession);
    }

    try {
      let receivedAnyToken = false;

      await streamTurnMessage(activeSession, text, {
        onToken: (token) => {
          receivedAnyToken = true;
          streamedContent += token;
          if (!hasAddedTutorMessage) {
            hasAddedTutorMessage = true;
            setIsTyping(false);
            setMessages((prev) => [
              ...prev,
              {
                id: tutorMsgId,
                role: "tutor",
                content: streamedContent,
                createdAt: "Just now",
                strategy: currentStrategy,
              },
            ]);
          } else {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === tutorMsgId ? { ...m, content: streamedContent } : m
              )
            );
          }
        },
        onStrategy: (strategy) => {
          const kind = strategy as StrategyKind;
          setCurrentStrategy(kind);
          setMessages((prev) =>
            prev.map((m) => (m.id === tutorMsgId ? { ...m, strategy: kind } : m))
          );
        },
        onMastery: (update) => {
          if (typeof update.new === "number") {
            setMasteryPct(update.new);
          }
        },
        onDone: (data) => {
          setIsTyping(false);
          if (data.strategy) {
            setCurrentStrategy(data.strategy as StrategyKind);
          }
          onTurnCompleted();
        },
        onError: (err) => {
          console.warn("SSE stream reported error:", err);
        },
      });

      // If stream completed but delivered empty text (e.g. test environment or blank stream)
      if (!receivedAnyToken || !streamedContent.trim()) {
        const fallback = await sendTurnMessage(activeSession, activeConcept.id, text);
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === tutorMsgId);
          if (exists) {
            return prev.map((m) =>
              m.id === tutorMsgId
                ? {
                    ...m,
                    content: fallback.content,
                    strategy: fallback.strategy,
                    diagnosis: fallback.diagnosis,
                  }
                : m
            );
          }
          return [
            ...prev,
            {
              id: tutorMsgId,
              role: "tutor",
              content: fallback.content,
              createdAt: "Just now",
              strategy: fallback.strategy,
              diagnosis: fallback.diagnosis,
            },
          ];
        });
        if (fallback.strategy) {
          setCurrentStrategy(fallback.strategy);
        }
        if (fallback.diagnosis?.misconceptionId) {
          setDetectedMiscId(fallback.diagnosis.misconceptionId);
        }
        setIsTyping(false);
        onTurnCompleted();
      }
    } catch (streamErr) {
      console.warn("Backend stream failed, using resilient fallback:", streamErr);
      try {
        const fallback = await sendTurnMessage(activeSession, activeConcept.id, text);
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === tutorMsgId);
          if (exists) {
            return prev.map((m) =>
              m.id === tutorMsgId
                ? {
                    ...m,
                    content: fallback.content,
                    strategy: fallback.strategy,
                    diagnosis: fallback.diagnosis,
                  }
                : m
            );
          }
          return [
            ...prev,
            {
              id: tutorMsgId,
              role: "tutor",
              content: fallback.content,
              createdAt: "Just now",
              strategy: fallback.strategy,
              diagnosis: fallback.diagnosis,
            },
          ];
        });
        if (fallback.strategy) {
          setCurrentStrategy(fallback.strategy);
        }
        if (fallback.diagnosis?.misconceptionId) {
          setDetectedMiscId(fallback.diagnosis.misconceptionId);
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: tutorMsgId,
            role: "tutor",
            content:
              "Let's reflect on that. What forces are acting upon the object in this scenario?",
            createdAt: "Just now",
          },
        ]);
      } finally {
        setIsTyping(false);
        onTurnCompleted();
      }
    }
  };

  const handleQuickPrompt = (prompt: string) => {
    handleSend(prompt);
  };

  const explorePrompts = getExplorePrompts(activeConcept);

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
            <button
              className="button-ghost icon-button"
              onClick={() => initSession(activeConcept)}
              title="Reset conversation for this concept"
              aria-label="Reset session"
            >
              <RotateCcw size={14} />
            </button>
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
                  {msg.content ? (
                    msg.content.split("\n\n").map((para, i) => (
                      <p key={i}>{para}</p>
                    ))
                  ) : (
                    <span className="typing-dot-stream">Thinking...</span>
                  )}
                </div>

                {msg.role === "tutor" && msg.strategy && (
                  <div className="bubble-footer-badge">
                    <Sparkles size={12} className="text-olive" />
                    <span>Strategy: {msg.strategy.replace(/_/g, " ")}</span>
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
          {explorePrompts.map((prompt, idx) => (
            <button
              key={idx}
              className="suggestion-pill"
              onClick={() => handleQuickPrompt(prompt)}
            >
              &ldquo;{prompt}&rdquo;
            </button>
          ))}
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
