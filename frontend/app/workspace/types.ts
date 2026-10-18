export type WorkspaceTab =
  | "tutor"
  | "mastery"
  | "streak"
  | "focus"
  | "doubts"
  | "battle"
  | "preferences";

export type StrategyKind =
  | "guided_hint"
  | "cognitive_conflict"
  | "worked_example"
  | "socratic_challenge"
  | "prerequisite_review";

export interface ConceptItem {
  id: string;
  title: string;
  domain: string;
  topic: string;
  description: string;
  difficulty: number;
  prerequisites: string[];
}

export interface MisconceptionItem {
  id: string;
  conceptId: string;
  statement: string;
  correctIdea: string;
  conflictPrompt: string;
}

export interface TurnMessage {
  id: string;
  role: "learner" | "tutor";
  content: string;
  createdAt: string;
  diagnosis?: {
    isCorrect?: boolean;
    confidence?: number;
    misconceptionId?: string;
    reasoning?: string;
    verifiedMath?: boolean;
  };
  strategy?: StrategyKind;
}

export interface ConceptMastery {
  conceptId: string;
  title: string;
  pKnown: number;
  attempts: number;
  state: "unseen" | "learning" | "mastered";
  prerequisites: string[];
}

export interface StreakState {
  current: number;
  longest: number;
  atRisk: boolean;
  freezesAvailable: number;
  todayActive: boolean;
  lastActiveDate: string | null;
}

export interface CalendarHeatmapDay {
  date: string;
  minutes: number;
  level: number; // 0 to 4
  freezeUsed: boolean;
  isQualifying: boolean;
  activityCounts: Record<string, number>;
}

export interface FocusSessionState {
  id: string;
  conceptId?: string;
  conceptTitle?: string;
  status: "idle" | "running" | "paused" | "completed" | "abandoned";
  plannedSeconds: number;
  elapsedSeconds: number;
  startedAt?: string;
  completedAt?: string;
  isBreak?: boolean;
  cycleCount: number;
}

export interface DoubtItem {
  id: string;
  conceptId: string;
  title: string;
  body: string;
  status: "open" | "in_progress" | "resolved" | "parked";
  resolutionNote?: string;
  createdAt: string;
  resolvedAt?: string;
}

export interface BattleRound {
  index: number;
  problemId: string;
  prompt: string;
  options?: string[];
  expectedAnswer: string;
  unit?: string;
  timeLimitSeconds: number;
  userAnswer?: string;
  userCorrect?: boolean;
  userTimeMs?: number;
  aiCorrect?: boolean;
  aiTimeMs?: number;
}

export interface BattleState {
  id: string;
  status: "idle" | "in_progress" | "completed" | "forfeited";
  opponentLevel: number;
  currentRoundIndex: number;
  userScore: number;
  aiScore: number;
  userRating: number;
  rounds: BattleRound[];
}

export interface UserProfile {
  id: string;
  authId: string;
  name: string;
  email: string;
  timezone: string;
  dailyGoalMinutes: number;
  voiceEnabled: boolean;
}
