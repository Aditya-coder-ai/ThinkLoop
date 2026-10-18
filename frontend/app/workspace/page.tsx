"use client";

import React, { useState, useEffect } from "react";
import {
  MessageSquare,
  Layers,
  Flame,
  Clock,
  HelpCircle,
  Swords,
  Settings,
  ChevronRight,
  BookOpen,
} from "lucide-react";
import {
  WorkspaceTab,
  UserProfile,
  StreakState,
  CalendarHeatmapDay,
  ConceptMastery,
  DoubtItem,
  ConceptItem,
} from "./types";
import { CURRICULUM_CONCEPTS } from "./curriculum";
import { useUser, useClerk } from "@clerk/nextjs";
import {
  getStoredUser,
  setStoredUser,
  setStoredToken,
  clearStoredAuth,
  fetchUserProfile,
  fetchStreak,
  fetchCalendar,
  fetchConceptMastery,
} from "./api";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { SocraticChatView } from "./components/SocraticChatView";
import { MasteryGraphView } from "./components/MasteryGraphView";
import { StreakCalendarView } from "./components/StreakCalendarView";
import { FocusTimerView } from "./components/FocusTimerView";
import { DoubtLogView } from "./components/DoubtLogView";
import { BattleArenaView } from "./components/BattleArenaView";
import { PreferencesModal } from "./components/PreferencesModal";

export default function WorkspacePage() {
  const { isLoaded, isSignedIn, user: clerkUser } = useUser();
  const { signOut, session } = useClerk();

  const [activeTab, setActiveTab] = useState<WorkspaceTab>("tutor");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [user, setUser] = useState<UserProfile>(getStoredUser());
  const [showPreferences, setShowPreferences] = useState(false);

  useEffect(() => {
    if (isLoaded && clerkUser) {
      const email = clerkUser.primaryEmailAddress?.emailAddress || "";
      const name =
        clerkUser.fullName ||
        clerkUser.firstName ||
        clerkUser.username ||
        "Learner";
      setUser((prev) => {
        const profile: UserProfile = {
          id: clerkUser.id,
          authId: clerkUser.id,
          name,
          email,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          dailyGoalMinutes: prev.dailyGoalMinutes || 30,
          voiceEnabled: prev.voiceEnabled ?? true,
        };
        setStoredUser(profile);
        return profile;
      });

      if (session) {
        session.getToken().then((token) => {
          if (token) {
            setStoredToken(`Bearer ${token}`);
          }
        });
      }
    }
  }, [isLoaded, clerkUser, session]);

  // Core state
  const [activeConcept, setActiveConcept] = useState<ConceptItem>(CURRICULUM_CONCEPTS[4]); // Newton's 1st Law
  const [masteryList, setMasteryList] = useState<ConceptMastery[]>([]);
  const [streak, setStreak] = useState<StreakState>({
    current: 4,
    longest: 11,
    atRisk: false,
    freezesAvailable: 1,
    todayActive: true,
    lastActiveDate: new Date().toISOString().split("T")[0],
  });
  const [calendarDays, setCalendarDays] = useState<CalendarHeatmapDay[]>([]);
  const [todayFocusMinutes, setTodayFocusMinutes] = useState(25);
  const [userRating, setUserRating] = useState(1050);

  // Doubts State
  const [doubts, setDoubts] = useState<DoubtItem[]>([
    {
      id: "doubt_1",
      conceptId: "newtons_first_law",
      title: "Why does an object slide to a stop if there are no external forces?",
      body: "If inertia says motion continues indefinitely, why do objects on a table stop moving?",
      status: "resolved",
      resolutionNote:
        "Friction between the surface and the object is a real external contact force that opposes the motion.",
      createdAt: "Yesterday",
      resolvedAt: "Yesterday",
    },
    {
      id: "doubt_2",
      conceptId: "acceleration",
      title: "Can acceleration be positive while velocity is negative?",
      body: "If a car is moving backwards (negative x) and slows down, what sign is its acceleration?",
      status: "open",
      createdAt: "Today",
    },
  ]);

  // Load theme and telemetry on mount
  useEffect(() => {
    const savedTheme = window.localStorage.getItem("thinkloop-theme") as "light" | "dark" | null;
    const defaultTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const currentTheme = savedTheme || defaultTheme;
    setTheme(currentTheme);
    document.documentElement.dataset.theme = currentTheme;

    // Sync authenticated user profile from backend /me
    fetchUserProfile().then((synced) => {
      if (synced) setUser(synced);
    });

    // Load streak and mastery
    fetchStreak().then(setStreak);
    fetchCalendar().then(setCalendarDays);
    fetchConceptMastery().then(setMasteryList);
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("thinkloop-theme", nextTheme);
  };

  const handleSavePreferences = (updated: UserProfile) => {
    setUser(updated);
    setStoredUser(updated);
  };

  const handleSignOut = async () => {
    clearStoredAuth();
    try {
      await signOut({ redirectUrl: "/" });
    } catch {
      window.location.href = "/";
    }
  };

  const handleTurnCompleted = () => {
    // Each Socratic turn marks streak active and boosts mastery
    setStreak((prev) => ({
      ...prev,
      todayActive: true,
      atRisk: false,
    }));
  };

  const handleFocusCompleted = (minutes: number) => {
    setTodayFocusMinutes((prev) => prev + minutes);
    if (minutes >= 15) {
      setStreak((prev) => ({
        ...prev,
        todayActive: true,
        atRisk: false,
      }));
    }
  };

  const handleAddDoubt = (conceptId: string, title: string, body: string) => {
    const newDoubt: DoubtItem = {
      id: `doubt_${Date.now()}`,
      conceptId,
      title,
      body,
      status: "open",
      createdAt: "Just now",
    };
    setDoubts((prev) => [newDoubt, ...prev]);
  };

  const handleResolveDoubt = (doubtId: string, note: string) => {
    setDoubts((prev) =>
      prev.map((d) =>
        d.id === doubtId
          ? {
              ...d,
              status: "resolved",
              resolutionNote: note,
              resolvedAt: "Just now",
            }
          : d
      )
    );
  };

  const handleAskTutorFromDoubt = (doubt: DoubtItem) => {
    const concept = CURRICULUM_CONCEPTS.find((c) => c.id === doubt.conceptId);
    if (concept) {
      setActiveConcept(concept);
    }
    setActiveTab("tutor");
  };

  const handleStartPracticeConcept = (concept: ConceptItem) => {
    setActiveConcept(concept);
    setActiveTab("tutor");
  };

  return (
    <div className="workspace-shell">
      {/* Top Header */}
      <WorkspaceHeader
        user={user}
        streak={streak}
        focusMinutes={todayFocusMinutes}
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenPreferences={() => setShowPreferences(true)}
        onSignOut={handleSignOut}
      />

      <div className="workspace-main-layout">
        {/* Left Navigation Rail */}
        <nav className="workspace-rail" aria-label="Workspace views">
          <button
            className={`rail-tab ${activeTab === "tutor" ? "active" : ""}`}
            onClick={() => setActiveTab("tutor")}
            title="Socratic Dialogue & Cognitive Diagnosis"
          >
            <MessageSquare size={18} />
            <span>Socratic Tutor</span>
          </button>

          <button
            className={`rail-tab ${activeTab === "mastery" ? "active" : ""}`}
            onClick={() => setActiveTab("mastery")}
            title="Concept Mastery Graph"
          >
            <Layers size={18} />
            <span>Knowledge Graph</span>
          </button>

          <button
            className={`rail-tab ${activeTab === "streak" ? "active" : ""}`}
            onClick={() => setActiveTab("streak")}
            title="Streak Calendar & Heatmap"
          >
            <Flame size={18} />
            <span>Streak Calendar</span>
          </button>

          <button
            className={`rail-tab ${activeTab === "focus" ? "active" : ""}`}
            onClick={() => setActiveTab("focus")}
            title="Server-Authoritative Focus Timer"
          >
            <Clock size={18} />
            <span>Focus Timer</span>
          </button>

          <button
            className={`rail-tab ${activeTab === "doubts" ? "active" : ""}`}
            onClick={() => setActiveTab("doubts")}
            title="Doubt Log & Clarity Ledger"
          >
            <HelpCircle size={18} />
            <span>Doubt Log</span>
            {doubts.filter((d) => d.status !== "resolved").length > 0 && (
              <span className="rail-badge">
                {doubts.filter((d) => d.status !== "resolved").length}
              </span>
            )}
          </button>

          <button
            className={`rail-tab ${activeTab === "battle" ? "active" : ""}`}
            onClick={() => setActiveTab("battle")}
            title="Battle with AI Duel Arena"
          >
            <Swords size={18} />
            <span>AI Battle</span>
          </button>

          <div className="rail-spacer" />

          <button
            className="rail-tab settings-tab"
            onClick={() => setShowPreferences(true)}
            title="Preferences & Settings"
          >
            <Settings size={18} />
            <span>Settings</span>
          </button>
        </nav>

        {/* View Content Body */}
        <main className="workspace-view-content">
          {activeTab === "tutor" && (
            <SocraticChatView
              activeConcept={activeConcept}
              onSelectConcept={setActiveConcept}
              onLogDoubtFromChat={(conceptId, title) => {
                handleAddDoubt(conceptId, title, "");
                setActiveTab("doubts");
              }}
              onTurnCompleted={handleTurnCompleted}
            />
          )}

          {activeTab === "mastery" && (
            <MasteryGraphView
              masteryList={masteryList}
              onStartSession={handleStartPracticeConcept}
            />
          )}

          {activeTab === "streak" && (
            <StreakCalendarView streak={streak} calendarDays={calendarDays} />
          )}

          {activeTab === "focus" && (
            <FocusTimerView onSessionCompleted={handleFocusCompleted} />
          )}

          {activeTab === "doubts" && (
            <DoubtLogView
              doubts={doubts}
              onAddDoubt={handleAddDoubt}
              onResolveDoubt={handleResolveDoubt}
              onAskTutor={handleAskTutorFromDoubt}
            />
          )}

          {activeTab === "battle" && (
            <BattleArenaView
              userRating={userRating}
              onBattleFinished={(delta) => setUserRating((prev) => prev + delta)}
            />
          )}
        </main>
      </div>

      {/* Preferences Modal */}
      {showPreferences && (
        <PreferencesModal
          user={user}
          onSave={handleSavePreferences}
          onClose={() => setShowPreferences(false)}
        />
      )}
    </div>
  );
}
