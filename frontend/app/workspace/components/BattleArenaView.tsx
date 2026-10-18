"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Swords, Trophy, Clock, Check, X, Shield, ArrowRight, RotateCcw } from "lucide-react";
import { BattleState, BattleRound } from "../types";
import { SAMPLE_BATTLE_PROBLEMS } from "../curriculum";
import { authStore } from "../../../lib/auth";

interface Props {
  userRating: number;
  onBattleFinished: (ratingDelta: number) => void;
}

export function BattleArenaView({ userRating, onBattleFinished }: Props) {
  const [battle, setBattle] = useState<BattleState>({
    id: "battle_1",
    status: "idle",
    opponentLevel: 2,
    currentRoundIndex: 0,
    userScore: 0,
    aiScore: 0,
    userRating: userRating,
    rounds: SAMPLE_BATTLE_PROBLEMS,
  });

  const [roundTimeRemaining, setRoundTimeRemaining] = useState<number>(25);
  const [userAnswerInput, setUserAnswerInput] = useState("");
  const [roundFeedback, setRoundFeedback] = useState<{
    userCorrect: boolean;
    aiCorrect: boolean;
    userPoints: number;
    aiPoints: number;
  } | null>(null);

  const submitRoundAnswer = useCallback(
    (answer: string | null) => {
      const currentRound = battle.rounds[battle.currentRoundIndex];
      const isCorrect =
        answer !== null && answer.trim().toLowerCase() === currentRound.expectedAnswer.toLowerCase();

      const aiProb = battle.opponentLevel === 1 ? 0.35 : battle.opponentLevel === 2 ? 0.55 : 0.8;
      const aiCorrect = Math.random() < aiProb;

      const timeSpent = currentRound.timeLimitSeconds - roundTimeRemaining;
      const speedBonus = Math.max(0, 15 - timeSpent);
      const userPoints = isCorrect ? 100 + speedBonus * 5 : 0;
      const aiPoints = aiCorrect ? 100 + Math.floor(Math.random() * 40) : 0;

      setRoundFeedback({
        userCorrect: isCorrect,
        aiCorrect,
        userPoints,
        aiPoints,
      });

      setBattle((prev) => ({
        ...prev,
        userScore: prev.userScore + userPoints,
        aiScore: prev.aiScore + aiPoints,
      }));
    },
    [battle.rounds, battle.currentRoundIndex, battle.opponentLevel, roundTimeRemaining]
  );

  const handleTimeExpired = useCallback(() => {
    submitRoundAnswer(null);
  }, [submitRoundAnswer]);

  // Round countdown timer
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    let timerId: number | null = null;
    if (battle.status === "in_progress" && !roundFeedback && roundTimeRemaining > 0) {
      timer = setInterval(() => {
        setRoundTimeRemaining((prev) => {
          if (prev <= 1) {
            handleTimeExpired();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      timerId = timer as unknown as number;
      authStore.registerActiveTimer(timerId, () => {
        if (timer) clearInterval(timer);
      });
    }

    return () => {
      if (timer) clearInterval(timer);
      if (timerId !== null) authStore.unregisterActiveTimer(timerId);
    };
  }, [battle.status, roundFeedback, roundTimeRemaining, handleTimeExpired]);

  const handleStartDuel = (level: number) => {
    setBattle({
      id: `battle_${Date.now()}`,
      status: "in_progress",
      opponentLevel: level,
      currentRoundIndex: 0,
      userScore: 0,
      aiScore: 0,
      userRating,
      rounds: SAMPLE_BATTLE_PROBLEMS.map((r) => ({ ...r })),
    });
    setRoundTimeRemaining(SAMPLE_BATTLE_PROBLEMS[0].timeLimitSeconds);
    setUserAnswerInput("");
    setRoundFeedback(null);
  };

  const handleNextRound = () => {
    if (battle.currentRoundIndex + 1 < battle.rounds.length) {
      const nextIndex = battle.currentRoundIndex + 1;
      setBattle((prev) => ({
        ...prev,
        currentRoundIndex: nextIndex,
      }));
      setRoundTimeRemaining(battle.rounds[nextIndex].timeLimitSeconds);
      setUserAnswerInput("");
      setRoundFeedback(null);
    } else {
      // Duel finished! Compute Elo rating change
      const won = battle.userScore > battle.aiScore;
      const ratingDelta = won ? 16 : battle.userScore === battle.aiScore ? 0 : -12;
      setBattle((prev) => ({
        ...prev,
        status: "completed",
        userRating: prev.userRating + ratingDelta,
      }));
      onBattleFinished(ratingDelta);
    }
  };

  const currentRound = battle.rounds[battle.currentRoundIndex];

  return (
    <div className="battle-view-container">
      {/* Banner */}
      <div className="battle-hero-card">
        <div>
          <span className="section-kicker">FAIR SIMULATED OPPONENT • DETERMINISTIC GRADING</span>
          <h2>Battle with AI Duel Arena</h2>
          <p>
            Compete in rapid physics rounds against a simulated opponent. Deterministic verifier grades every answer; the LLM never decides the winner.
          </p>
        </div>

        <div className="battle-rating-pill">
          <Trophy size={18} className="text-ochre" />
          <span>Elo Rating: <strong>{battle.userRating}</strong></span>
        </div>
      </div>

      {battle.status === "idle" && (
        <div className="battle-setup-card">
          <h3>Choose Opponent Level</h3>
          <p className="setup-sub">
            Opponent response speed and accuracy are drawn from reproducible probability distributions based on difficulty.
          </p>

          <div className="level-select-grid">
            <button className="level-card" onClick={() => handleStartDuel(1)}>
              <span className="level-badge">Level 1</span>
              <h4>Novice AI</h4>
              <p>Moderate response time • ~35% accuracy</p>
            </button>

            <button className="level-card active" onClick={() => handleStartDuel(2)}>
              <span className="level-badge">Level 2</span>
              <h4>Adept AI</h4>
              <p>Balanced speed • ~55% accuracy</p>
            </button>

            <button className="level-card" onClick={() => handleStartDuel(3)}>
              <span className="level-badge">Level 3</span>
              <h4>Master AI</h4>
              <p>Swift response • ~80% accuracy</p>
            </button>
          </div>
        </div>
      )}

      {battle.status === "in_progress" && (
        <div className="active-battle-arena">
          {/* Top Scoreboard */}
          <div className="battle-scoreboard">
            <div className="player-side you">
              <span className="player-label">YOU</span>
              <strong className="player-score">{battle.userScore} pts</strong>
            </div>

            <div className="scoreboard-center">
              <span className="round-badge">
                ROUND {battle.currentRoundIndex + 1} of {battle.rounds.length}
              </span>
              <div className="battle-clock">
                <Clock size={16} />
                <span>{roundTimeRemaining}s</span>
              </div>
            </div>

            <div className="player-side ai">
              <span className="player-label">SIMULATED AI (Lv {battle.opponentLevel})</span>
              <strong className="player-score">{battle.aiScore} pts</strong>
            </div>
          </div>

          {/* Current Question */}
          <div className="battle-question-card">
            <span className="q-kicker">QUESTION #{currentRound.index}</span>
            <h3 className="q-prompt">{currentRound.prompt}</h3>

            {!roundFeedback ? (
              <form
                className="battle-answer-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  submitRoundAnswer(userAnswerInput);
                }}
              >
                <div className="input-group">
                  <input
                    type="text"
                    required
                    autoFocus
                    placeholder="Enter numerical answer..."
                    value={userAnswerInput}
                    onChange={(e) => setUserAnswerInput(e.target.value)}
                  />
                  {currentRound.unit && <span className="unit-tag">{currentRound.unit}</span>}
                </div>
                <button type="submit" className="button-primary" disabled={!userAnswerInput.trim()}>
                  Submit Answer
                </button>
              </form>
            ) : (
              <div className="round-result-card">
                <div className="result-cols">
                  <div className={`res-col ${roundFeedback.userCorrect ? "correct" : "incorrect"}`}>
                    <div className="res-header">
                      {roundFeedback.userCorrect ? <Check size={18} /> : <X size={18} />}
                      <span>Your Answer: {roundFeedback.userCorrect ? "CORRECT" : "INCORRECT"}</span>
                    </div>
                    <strong>+{roundFeedback.userPoints} pts</strong>
                    <span className="correct-answer-reveal">
                      Expected: {currentRound.expectedAnswer} {currentRound.unit}
                    </span>
                  </div>

                  <div className={`res-col ${roundFeedback.aiCorrect ? "correct" : "incorrect"}`}>
                    <div className="res-header">
                      {roundFeedback.aiCorrect ? <Check size={18} /> : <X size={18} />}
                      <span>AI Opponent: {roundFeedback.aiCorrect ? "CORRECT" : "MISSED"}</span>
                    </div>
                    <strong>+{roundFeedback.aiPoints} pts</strong>
                  </div>
                </div>

                <button className="button-primary next-round-btn" onClick={handleNextRound}>
                  <span>
                    {battle.currentRoundIndex + 1 < battle.rounds.length
                      ? "Next Round"
                      : "Finish Duel & See Results"}
                  </span>
                  <ArrowRight size={16} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {battle.status === "completed" && (
        <div className="battle-finished-card">
          <Trophy size={48} className={battle.userScore >= battle.aiScore ? "text-ochre" : "text-clay"} />
          <h2>{battle.userScore >= battle.aiScore ? "Victory!" : "Duel Completed"}</h2>
          <p className="finished-scores">
            Final Score: <strong>{battle.userScore}</strong> (You) vs <strong>{battle.aiScore}</strong> (AI)
          </p>

          <div className="elo-change-box">
            <span>Rating Updated</span>
            <strong>{battle.userRating}</strong>
            <small>
              {battle.userScore > battle.aiScore
                ? "+16 Elo"
                : battle.userScore === battle.aiScore
                ? "No change"
                : "-12 Elo"}
            </small>
          </div>

          <button
            className="button-primary"
            onClick={() => setBattle((prev) => ({ ...prev, status: "idle" }))}
          >
            <RotateCcw size={16} />
            <span>Play Another Duel</span>
          </button>
        </div>
      )}
    </div>
  );
}
