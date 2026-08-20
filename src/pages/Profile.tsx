import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { userService } from '../api';

export function Profile() {
  const { profile } = useAuth();
  const [settings, setSettings] = useState<any>(null);

  useEffect(() => {
    async function loadSettings() {
      try {
        const s = await userService.getSettings();
        setSettings(s);
      } catch (err) {
        console.error("Failed to load settings:", err);
      }
    }
    loadSettings();
  }, []);

  const dosha = profile?.dosha_profile?.prakriti || { vata: 0.45, pitta: 0.35, kapha: 0.20 };
  const vataPct = Math.round(dosha.vata * 100);
  const pittaPct = Math.round(dosha.pitta * 100);
  const kaphaPct = Math.round(dosha.kapha * 100);

  return (
    <>
      <header className="flex justify-between items-center px-container-margin py-base w-full bg-surface docked full-width top-0 sticky z-40">
        <div className="md:hidden">
          <h1 className="font-headline-md text-headline-md font-bold text-primary">AiDincharya</h1>
        </div>
        <div className="hidden md:block">
          <h2 className="font-headline-md text-headline-md text-on-surface">Profile</h2>
        </div>
        <div className="flex items-center gap-4">
          <button className="text-on-surface-variant hover:opacity-80 transition-opacity">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="text-on-surface-variant hover:opacity-80 transition-opacity">
            <span className="material-symbols-outlined">settings</span>
          </button>
          <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center font-bold text-primary border border-outline-variant">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
        </div>
      </header>

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
                <span>Earth</span>
              </div>
              <p className="font-body-lg text-body-lg text-tertiary italic max-w-2xl">
                "Cultivating balance through mindful daily rhythms and the wisdom of nature."
              </p>
            </div>
            <div className="mt-4 md:mt-0">
              <button className="px-6 py-2 border-2 border-primary text-primary font-label-md text-label-md rounded-full hover:bg-surface-container-low transition-colors">
                Edit Profile
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
                  <button className="text-primary font-label-md text-label-md flex items-center gap-1 hover:underline">
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
