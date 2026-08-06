import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { ChatMessage, MatchResult, Profile } from "@/services/types";

/**
 * What Streamlit kept in `st.session_state`, held here instead.
 *
 * React Router gives us real pages, so this has to survive navigation, and it
 * is persisted to sessionStorage so a refresh does not throw away a parsed CV.
 * sessionStorage rather than localStorage on purpose: a CV is personal, and it
 * should not outlive the tab on a shared machine.
 */
interface SessionState {
  profile: Profile | null;
  matches: MatchResult[] | null;
  chat: ChatMessage[];
}

interface SessionValue extends SessionState {
  setProfile: (profile: Profile | null) => void;
  setMatches: (matches: MatchResult[] | null) => void;
  appendChat: (message: ChatMessage) => void;
  reset: () => void;
}

const EMPTY: SessionState = { profile: null, matches: null, chat: [] };
const STORAGE_KEY = "career-coach-session";

const SessionContext = createContext<SessionValue | null>(null);

function load(): SessionState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY;
    return { ...EMPTY, ...(JSON.parse(raw) as Partial<SessionState>) };
  } catch {
    // Corrupt or unavailable storage must not take the app down with it.
    return EMPTY;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(load);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Private mode, or quota. Losing persistence is survivable; crashing is not.
    }
  }, [state]);

  const setProfile = useCallback((profile: Profile | null) => {
    // Matches go stale the moment the profile changes: they were ranked
    // against the old one, and showing them next to new inputs is a lie.
    setState((prev) => ({ ...prev, profile, matches: null }));
  }, []);

  const setMatches = useCallback((matches: MatchResult[] | null) => {
    setState((prev) => ({ ...prev, matches }));
  }, []);

  const appendChat = useCallback((message: ChatMessage) => {
    setState((prev) => ({ ...prev, chat: [...prev.chat, message] }));
  }, []);

  const reset = useCallback(() => {
    setState(EMPTY);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* nothing to do */
    }
  }, []);

  const value = useMemo(
    () => ({ ...state, setProfile, setMatches, appendChat, reset }),
    [state, setProfile, setMatches, appendChat, reset],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside a SessionProvider");
  return value;
}
