import React, { useState, useEffect } from 'react';
import { userService } from '../api';

interface SettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsDrawer({ isOpen, onClose }: SettingsDrawerProps) {
  const [notifications, setNotifications] = useState(true);
  const [theme, setTheme] = useState('system');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  const loadSettings = async () => {
    try {
      const res = await userService.getSettings();
      if (res.settings) {
        if (res.settings.notifications !== undefined) setNotifications(res.settings.notifications);
        if (res.settings.theme) setTheme(res.settings.theme);
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await userService.updateSettings({ notifications, theme });
      onClose();
    } catch (err) {
      console.error("Failed to save settings:", err);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-background/50 backdrop-blur-sm z-40 transition-opacity" onClick={onClose}></div>
      <div className="fixed top-0 right-0 h-full w-full max-w-sm bg-surface shadow-2xl z-50 transform transition-transform border-l border-surface-variant flex flex-col">
        
        <div className="p-6 border-b border-surface-variant flex justify-between items-center bg-surface-container-lowest">
          <h2 className="font-headline-md text-[22px] font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">settings</span> Settings
          </h2>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 space-y-8 flex-1 overflow-y-auto">
          
          <section>
            <h3 className="font-label-lg text-label-lg text-primary uppercase tracking-wide mb-4">Preferences</h3>
            
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <div>
                  <h4 className="font-body-lg text-body-lg text-on-surface font-medium">Push Notifications</h4>
                  <p className="font-caption text-caption text-on-surface-variant">Receive daily routine reminders</p>
                </div>
                <button 
                  onClick={() => setNotifications(!notifications)}
                  className={`w-12 h-6 rounded-full transition-colors relative ${notifications ? 'bg-primary' : 'bg-surface-variant'}`}
                >
                  <div className={`absolute top-1 w-4 h-4 rounded-full bg-on-primary transition-transform ${notifications ? 'right-1' : 'left-1'}`}></div>
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <h4 className="font-body-lg text-body-lg text-on-surface font-medium">Theme Style</h4>
                  <p className="font-caption text-caption text-on-surface-variant">Choose your visual aesthetic</p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <button onClick={() => setTheme('light')} className={`py-2 rounded-xl border text-sm font-medium transition-colors ${theme === 'light' ? 'bg-primary-container border-primary text-on-primary-container' : 'border-surface-variant text-on-surface hover:bg-surface-container'}`}>Light</button>
                  <button onClick={() => setTheme('dark')} className={`py-2 rounded-xl border text-sm font-medium transition-colors ${theme === 'dark' ? 'bg-primary-container border-primary text-on-primary-container' : 'border-surface-variant text-on-surface hover:bg-surface-container'}`}>Dark</button>
                  <button onClick={() => setTheme('system')} className={`py-2 rounded-xl border text-sm font-medium transition-colors ${theme === 'system' ? 'bg-primary-container border-primary text-on-primary-container' : 'border-surface-variant text-on-surface hover:bg-surface-container'}`}>System</button>
                </div>
              </div>
            </div>
          </section>
          
          <section className="pt-6 border-t border-surface-variant/50">
            <h3 className="font-label-lg text-label-lg text-primary uppercase tracking-wide mb-4">Account</h3>
            <button className="text-error hover:bg-error-container/20 w-full text-left p-4 rounded-xl transition-colors font-medium flex items-center gap-3">
              <span className="material-symbols-outlined">delete</span> Delete Data History
            </button>
          </section>

        </div>

        <div className="p-6 border-t border-surface-variant bg-surface-container-lowest">
          <button 
            onClick={handleSave} 
            disabled={isSaving}
            className="w-full py-4 rounded-full bg-primary text-on-primary font-label-lg hover:bg-primary-container hover:shadow-md transition-all disabled:opacity-50"
          >
            {isSaving ? 'Applying...' : 'Save Settings'}
          </button>
        </div>

      </div>
    </>
  );
}
