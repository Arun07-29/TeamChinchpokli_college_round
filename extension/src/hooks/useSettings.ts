import { useState, useEffect, useCallback } from 'react';
import {
  loadSettings, saveSettings, clearSettings,
  validateSettings, DEFAULT_SETTINGS,
  type IntentLockSettings,
} from '../shared/settings';

export function useSettings() {
  const [settings, setSettingsState] = useState<IntentLockSettings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);

  // Load from storage on mount
  useEffect(() => {
    loadSettings().then(s => {
      setSettingsState(s);
      setLoaded(true);
    });
  }, []);

  // Save whenever settings change (after initial load)
  useEffect(() => {
    if (!loaded) return;
    saveSettings(settings);
  }, [settings, loaded]);

  const updateSettings = useCallback((patch: Partial<IntentLockSettings>) => {
    setSettingsState(prev => validateSettings({ ...prev, ...patch }));
  }, []);

  const resetSettings = useCallback(async () => {
    await clearSettings();
    setSettingsState({ ...DEFAULT_SETTINGS });
  }, []);

  return { settings, updateSettings, resetSettings, loaded };
}
