import type React from 'react';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type ExperienceMode = 'simple' | 'pro';

export const EXPERIENCE_MODE_STORAGE_KEY = 'dsa.experienceMode';

type ExperienceModeContextValue = {
  mode: ExperienceMode;
  isSimple: boolean;
  setMode: (next: ExperienceMode) => void;
  toggleMode: () => void;
};

const fallbackContext: ExperienceModeContextValue = {
  mode: 'pro',
  isSimple: false,
  setMode: () => undefined,
  toggleMode: () => undefined,
};

const ExperienceModeContext = createContext<ExperienceModeContextValue | null>(null);

function readInitialMode(): ExperienceMode {
  if (typeof window === 'undefined') return 'pro';
  try {
    const raw = window.localStorage.getItem(EXPERIENCE_MODE_STORAGE_KEY);
    return raw === 'simple' ? 'simple' : 'pro';
  } catch {
    return 'pro';
  }
}

export const ExperienceModeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ExperienceMode>(readInitialMode);

  const setMode = useCallback((next: ExperienceMode) => {
    const safe: ExperienceMode = next === 'simple' ? 'simple' : 'pro';
    setModeState(safe);
    try {
      window.localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, safe);
    } catch {
      // Ignore storage errors; in-memory mode still updates.
    }
  }, []);

  const toggleMode = useCallback(() => {
    setModeState((prev) => {
      const next: ExperienceMode = prev === 'simple' ? 'pro' : 'simple';
      try {
        window.localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, next);
      } catch {
        // Ignore storage errors.
      }
      return next;
    });
  }, []);

  const value = useMemo<ExperienceModeContextValue>(
    () => ({
      mode,
      isSimple: mode === 'simple',
      setMode,
      toggleMode,
    }),
    [mode, setMode, toggleMode],
  );

  return (
    <ExperienceModeContext.Provider value={value}>
      {children}
    </ExperienceModeContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components -- co-located context hook
export function useExperienceMode(): ExperienceModeContextValue {
  return useContext(ExperienceModeContext) ?? fallbackContext;
}
