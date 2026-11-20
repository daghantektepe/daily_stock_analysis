import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { formatUiText, UI_TEXT, type UiLanguage, type UiTextKey, type UiTextParams } from '../i18n/uiText';
import { getRuntimeInitialLanguage, getUiLanguageStorage, persistUiLanguage } from '../utils/uiLanguage';

type UiLanguageContextValue = {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  t: (key: UiTextKey, params?: UiTextParams) => string;
};

const fallbackContext: UiLanguageContextValue = {
  language: 'tr',
  setLanguage: () => undefined,
  t: (key, params) => formatUiText(UI_TEXT.tr[key], params),
};

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null);

export const UiLanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<UiLanguage>(getRuntimeInitialLanguage);

  const setLanguage = useCallback((nextLanguage: UiLanguage) => {
    const safeLang: UiLanguage = nextLanguage === 'en' ? 'en' : 'tr';
    setLanguageState(safeLang);
    persistUiLanguage(getUiLanguageStorage(), safeLang);
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = language === 'en' ? 'en' : 'tr';
    }
  }, [language]);

  const value = useMemo<UiLanguageContextValue>(() => ({
    language: language === 'en' ? 'en' : 'tr',
    setLanguage,
    t: (key, params) => formatUiText(UI_TEXT[language === 'en' ? 'en' : 'tr'][key], params),
  }), [language, setLanguage]);

  return (
    <UiLanguageContext.Provider value={value}>
      {children}
    </UiLanguageContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components -- useUiLanguage is a hook, co-located for context access
export function useUiLanguage(): UiLanguageContextValue {
  return useContext(UiLanguageContext) ?? fallbackContext;
}
