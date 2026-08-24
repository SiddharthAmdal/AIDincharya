import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { userService } from '../api';
import { NotificationsDrawer } from '../components/NotificationsDrawer';
import { SettingsDrawer } from '../components/SettingsDrawer';

export function Profile() {
  const { profile, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [settings, setSettings] = useState<any>(null);

  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Edit Profile Modal state
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [location, setLocation] = useState('Earth');
  const [bio, setBio] = useState('Cultivating balance through mindful daily rhythms and the wisdom of nature.');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await userService.getSettings();
        const sData = s?.settings || s || {};
        setSettings(sData);
        if (sData.location) setLocation(sData.location);
        if (sData.bio) setBio(sData.bio);
      } catch (err) {
        console.error("Failed to load settings:", err);
      }
    }
    loadSettings();
  }, []);

  const handleSaveProfile = async () => {
    setIsSaving(true);
    try {
      const updatedSettings = {
        ...(settings || {}),
        location,
        bio
      };
      await userService.updateSettings(updatedSettings);
      setSettings(updatedSettings);
      await refreshProfile();
      setIsEditProfileOpen(false);
    } catch (err) {
      console.error("Failed to save profile changes:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const dosha = profile?.dosha_profile?.prakriti || { vata: 0.45, pitta: 0.35, kapha: 0.20 };
  const vataPct = Math.round(dosha.vata * 100);
  const pittaPct = Math.round(dosha.pitta * 100);
  const kaphaPct = Math.round(dosha.kapha * 100);

  return (
    <>
      <header className="flex justify-between items-center px-container-margin py-base w-full sticky top-0 z-30 bg-surface/80 backdrop-blur-md">
        <div className="md:hidden flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold overflow-hidden">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <h1 className="font-headline-md text-headline-md font-bold text-primary">Profile</h1>
        </div>
        <div className="hidden md:block">
          <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">Your Profile</h1>
        </div>
        <div className="flex items-center gap-4 ml-auto">
          <button
            onClick={() => setIsNotificationsOpen(true)}
            className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors"
          >
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors"
          >
            <span className="material-symbols-outlined">settings</span>
          </button>
        </div>
      </header>

      <NotificationsDrawer isOpen={isNotificationsOpen} onClose={() => setIsNotificationsOpen(false)} />
      <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />

      {/* Edit Profile Modal */}
      {isEditProfileOpen && (
        <div className="fixed inset-0 bg-background/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-surface border border-surface-variant rounded-3xl p-6 md:p-8 max-w-lg w-full shadow-2xl relative animate-in fade-in zoom-in duration-200">
            <div className="flex justify-between items-center mb-6">
              <h2 className="font-headline-md text-headline-md font-bold text-on-surface flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">edit</span> Edit Profile
              </h2>
              <button
                onClick={() => setIsEditProfileOpen(false)}
                className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block font-label-md text-label-md text-on-surface-variant mb-2">Location / Environment</label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. New York, Earth"
                  className="w-full px-4 py-3 rounded-2xl bg-surface-container-low border border-surface-variant text-on-surface focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div>
                <label className="block font-label-md text-label-md text-on-surface-variant mb-2">Personal Philosophy / Bio</label>
                <textarea
                  rows={3}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Write your daily wellness intention..."
                  className="w-full px-4 py-3 rounded-2xl bg-surface-container-low border border-surface-variant text-on-surface focus:outline-none focus:border-primary transition-colors resize-none"
                />
              </div>

              <div className="pt-2 border-t border-surface-variant/60">
                <div className="flex justify-between items-center p-4 bg-surface-container-lowest rounded-2xl border border-surface-variant/40">
                  <div>
                    <h4 className="font-body-md font-semibold text-on-surface">Ayurvedic Assessment</h4>
                    <p className="font-caption text-caption text-on-surface-variant">Retake questionnaire to update your Prakriti & Dosha balance</p>
                  </div>
                  <button
                    onClick={() => {
                      setIsEditProfileOpen(false);
                      navigate('/onboarding');
                    }}
                    className="px-4 py-2 bg-secondary/15 text-secondary border border-secondary/30 rounded-xl font-label-md hover:bg-secondary hover:text-on-secondary transition-all flex items-center gap-1 flex-shrink-0"
                  >
                    <span className="material-symbols-outlined text-[18px]">quiz</span> Retake
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-8 flex justify-end gap-3">
              <button
                onClick={() => setIsEditProfileOpen(false)}
                className="px-6 py-2.5 rounded-full border border-surface-variant text-on-surface-variant hover:bg-surface-container font-label-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveProfile}
                disabled={isSaving}
                className="px-8 py-2.5 rounded-full bg-primary text-on-primary font-label-md hover:bg-primary-container transition-all disabled:opacity-50 flex items-center gap-2"
              >
                {isSaving ? 'Saving...' : 'Save Profile'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-container-margin py-8 pb-32">
        <div className="max-w-7xl mx-auto space-y-section-gap-md">
          <div className="flex flex-col md:flex-row items-center md:items-start gap-8 bg-surface-container-lowest p-8 rounded-2xl border border-surface-variant shadow-sm">
            <div className="w-32 h-32 rounded-full overflow-hidden border-4 border-surface-container-highest relative flex-shrink-0 bg-primary-container flex items-center justify-center text-4xl text-on-primary-container">
              {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="text-center md:text-left flex-1">
              <h1 className="font-headline-display text-headline-display text-on-surface mb-2">
                {profile?.user?.username || 'Seeker'}
              </h1>
              <div className="flex items-center justify-center md:justify-start gap-2 text-on-surface-variant font-body-md mb-4">
                <span className="material-symbols-outlined text-[20px]">location_on</span>
                <span>{location}</span>
              </div>
              <p className="font-body-lg text-body-lg text-tertiary italic max-w-2xl">
                "{bio}"
              </p>
            </div>
            <div className="mt-4 md:mt-0">
              <button
                onClick={() => setIsEditProfileOpen(true)}
                className="px-6 py-2 border-2 border-primary text-primary font-label-md text-label-md rounded-full hover:bg-primary hover:text-on-primary transition-all flex items-center gap-2 shadow-sm"
              >
                <span className="material-symbols-outlined text-[18px]">edit</span> Edit Profile
              </button>
            </div>
          </div>

          <div className="bento-grid">
            <div className="bento-item col-span-12 md:col-span-8 lg:col-span-5 flex flex-col h-full relative overflow-hidden">
              <div className="absolute inset-0 opacity-5 pointer-events-none" style={{ backgroundImage: "radial-gradient(circle at top right, #455538, transparent 70%)" }}></div>
              <h3 className="font-headline-md text-headline-md text-on-surface mb-6 relative z-10">Prakriti Composition</h3>
              <div className="flex-1 flex flex-col justify-center gap-6 relative z-10">
                <div>
                  <div className="flex justify-between font-label-md text-label-md mb-2">
                    <span className="text-on-surface flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full bg-primary inline-block"></span> Vata
                    </span>
                    <span className="text-on-surface-variant">{vataPct}%</span>
                  </div>
                  <div className="h-3 bg-surface-container-high rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: `${vataPct}%` }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between font-label-md text-label-md mb-2">
                    <span className="text-on-surface flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full bg-secondary inline-block"></span> Pitta
                    </span>
                    <span className="text-on-surface-variant">{pittaPct}%</span>
                  </div>
                  <div className="h-3 bg-surface-container-high rounded-full overflow-hidden">
                    <div className="h-full bg-secondary rounded-full" style={{ width: `${pittaPct}%` }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between font-label-md text-label-md mb-2">
                    <span className="text-on-surface flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full bg-tertiary inline-block"></span> Kapha
                    </span>
                    <span className="text-on-surface-variant">{kaphaPct}%</span>
                  </div>
                  <div className="h-3 bg-surface-container-high rounded-full overflow-hidden">
                    <div className="h-full bg-tertiary rounded-full" style={{ width: `${kaphaPct}%` }}></div>
                  </div>
                </div>
              </div>
            </div>

            <div className="bento-item col-span-12 md:col-span-4 lg:col-span-7 flex flex-col h-full bg-surface-container-low">
              <h3 className="font-headline-md text-headline-md text-on-surface mb-4">Baseline Assessment</h3>
              <div className="flex-1 flex flex-col justify-between">
                <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
                  Your dominant {vataPct >= Math.max(pittaPct, kaphaPct) ? 'Vata' : pittaPct >= Math.max(vataPct, kaphaPct) ? 'Pitta' : 'Kapha'} constitution suggests a naturally unique rhythm.
                  <br /><br />
                  Incorporating aligned foods and a consistent daily schedule will help anchor your energy and maintain optimal balance.
                </p>
                <div className="mt-6">
                  <button
                    onClick={() => navigate('/reasoning')}
                    className="text-primary font-label-md text-label-md flex items-center gap-1 hover:underline cursor-pointer"
                  >
                    Read Full Report <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

