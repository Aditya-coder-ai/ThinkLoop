export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

export interface AuthUser {
  id: string;
  email: string | null;
  name: string;
  authId?: string;
  timezone?: string;
  dailyGoalMinutes?: number;
  voiceEnabled?: boolean;
}

export interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  error: string | null;
  epoch: number;
}

export type RedirectHandler = (url: string) => void;
