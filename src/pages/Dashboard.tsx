import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { scheduleService, userService } from '../api';
import type { ScheduleResponse, UserState } from '../api';

export function Dashboard() {
  const { profile } = useAuth();
  const [scheduleData, setScheduleData] = useState<ScheduleResponse | null>(null);
  const [userState, setUserState] = useState<UserState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [schedRes, stateRes] = await Promise.all([
          scheduleService.getToday(),
          userService.getState()
        ]);
        setScheduleData(schedRes);
        setUserState(stateRes);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  // Compute tasks for display
  const allTasks = scheduleData ? [
    ...scheduleData.schedule.morning_block,
    ...scheduleData.schedule.midday_block,
    ...scheduleData.schedule.evening_block
  ] : [];

  return (
    <>
      <header className="flex justify-between items-center px-container-margin py-base w-full sticky top-0 z-30 bg-surface/80 backdrop-blur-md">
        <div className="md:hidden flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold overflow-hidden">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <h1 className="font-headline-md text-headline-md font-bold text-primary">AiDincharya</h1>
        </div>
        <div className="hidden md:block"></div>
        <div className="flex items-center gap-4 ml-auto">
          <span className="font-caption text-caption text-primary-container bg-primary-fixed-dim/20 px-2 py-1 rounded-md hidden sm:block border border-primary-fixed">Test Mode</span>
          <button className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-highest transition-colors">
            <span className="material-symbols-outlined">settings</span>
          </button>
        </div>
      </header>

      <div className="p-container-margin md:p-section-gap-md flex-1 space-y-section-gap-md pb-24 md:pb-8">
        {loading ? (
          <div className="flex justify-center py-20 text-on-surface-variant font-body-md">Loading dashboard...</div>
        ) : (
          <>
            <section>
              <h2 className="font-headline-display text-headline-lg-mobile md:text-headline-display text-on-background mb-2 tracking-tight">
                Good morning, {profile?.user?.username || 'Seeker'}.
              </h2>
              <p className="font-body-lg text-body-lg text-on-surface-variant flex items-center gap-2">
                <span className="material-symbols-outlined text-primary">psychiatry</span>
                Your routine is balanced today.
              </p>
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter md:gap-container-margin">
              <div className="lg:col-span-5 bg-surface-container-lowest rounded-3xl p-6 md:p-8 border border-surface-variant shadow-sm relative overflow-hidden flex flex-col h-full">
                <div className="absolute top-0 right-0 w-32 h-32 bg-primary-fixed-dim/10 rounded-bl-full -z-10"></div>
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <h3 className="font-headline-md text-headline-md text-on-background">Wellness State</h3>
                    <p className="font-body-md text-body-md text-on-surface-variant">Dosha Balance</p>
                  </div>
                  <button className="text-primary hover:bg-primary-container/10 p-2 rounded-full transition-colors">
                    <span className="material-symbols-outlined">info</span>
                  </button>
                </div>
                <div className="flex-1 flex flex-col items-center justify-center min-h-[240px]">
                  <div className="relative flex items-center justify-center">
                    <div className="dosha-chart-container"></div>
                    <div className="vikriti-overlay"></div>
                    <div className="absolute inset-0 flex flex-col items-center justify-center z-10 pointer-events-none">
                      <span className="font-headline-lg text-headline-lg text-on-background">Vata</span>
                      <span className="font-label-md text-label-md text-on-surface-variant">Dominant</span>
                    </div>
                  </div>
                </div>
                <div className="mt-6 space-y-4">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-primary"></div>
                      <span className="font-body-md text-body-md text-on-surface">
                        Vata {scheduleData?.dosha_profile?.prakriti?.vata ? Math.round(scheduleData.dosha_profile.prakriti.vata * 100) : 45}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-secondary"></div>
                      <span className="font-body-md text-body-md text-on-surface">
                        Pitta {scheduleData?.dosha_profile?.prakriti?.pitta ? Math.round(scheduleData.dosha_profile.prakriti.pitta * 100) : 35}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-tertiary"></div>
                      <span className="font-body-md text-body-md text-on-surface">
                        Kapha {scheduleData?.dosha_profile?.prakriti?.kapha ? Math.round(scheduleData.dosha_profile.prakriti.kapha * 100) : 20}%
                      </span>
                    </div>
                  </div>
                  {scheduleData?.behavioral_nudge && (
                    <div className="bg-error-container/30 border border-error/20 rounded-xl p-4 flex items-start gap-3">
                      <span className="material-symbols-outlined text-error mt-0.5">warning</span>
                      <div>
                        <h4 className="font-label-md text-label-md text-on-background">{scheduleData.behavioral_nudge.title}</h4>
                        <p className="font-caption text-caption text-on-surface-variant mt-1">{scheduleData.behavioral_nudge.message}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="lg:col-span-7 space-y-6 flex flex-col h-full">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="font-headline-md text-headline-md text-on-background">Today's Dinacharya</h3>
                  <div className="flex gap-2">
                    <span className="px-3 py-1 bg-primary-container text-on-primary-container rounded-full font-caption text-caption flex items-center gap-1">
                      <span className="material-symbols-outlined text-[16px]">schedule</span> {allTasks.length} Tasks
                    </span>
                  </div>
                </div>
                <div className="flex-1 bg-surface-container-lowest rounded-3xl border border-surface-variant shadow-sm p-2 relative overflow-hidden">
                  <div className="absolute left-[2.25rem] top-8 bottom-8 w-[2px] bg-surface-variant z-0"></div>
                  <div className="space-y-6 p-4 relative z-10 overflow-y-auto max-h-[600px] pr-2 no-scrollbar">
                    
                    {/* Morning Block */}
                    {scheduleData?.schedule?.morning_block && scheduleData.schedule.morning_block.length > 0 && (
                      <div className="relative">
                        <div className="flex items-center gap-4 mb-4">
                          <div className="w-10 h-10 rounded-full bg-surface-container-highest border-4 border-surface-container-lowest flex items-center justify-center text-on-surface-variant shadow-sm z-10">
                            <span className="material-symbols-outlined">wb_twilight</span>
                          </div>
                          <h4 className="font-label-md text-label-md text-on-background bg-surface-container-lowest px-2">Morning Focus</h4>
                        </div>
                        <div className="ml-14 space-y-3">
                          {scheduleData.schedule.morning_block.map((task, idx) => (
                            <div key={idx} className="group bg-surface rounded-2xl p-4 border border-surface-variant hover:border-primary/30 shadow-sm transition-all cursor-pointer flex items-center gap-4 relative overflow-hidden">
                              <div className="w-6 h-6 rounded-full border-2 border-outline flex items-center justify-center group-hover:border-primary transition-colors"></div>
                              <div className="flex-1">
                                <h5 className="font-body-md text-body-md text-on-background font-medium">{task.name}</h5>
                                <p className="font-caption text-caption text-on-surface-variant">{task.time_slot} • {task.duration_minutes}m</p>
                              </div>
                              <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">chevron_right</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Midday Block */}
                    {scheduleData?.schedule?.midday_block && scheduleData.schedule.midday_block.length > 0 && (
                      <div className="relative mt-8">
                        <div className="flex items-center gap-4 mb-4">
                          <div className="w-10 h-10 rounded-full bg-surface-container-highest border-4 border-surface-container-lowest flex items-center justify-center text-on-surface-variant shadow-sm z-10">
                            <span className="material-symbols-outlined">light_mode</span>
                          </div>
                          <h4 className="font-label-md text-label-md text-on-background bg-surface-container-lowest px-2">Midday Sustenance</h4>
                        </div>
                        <div className="ml-14 space-y-3">
                          {scheduleData.schedule.midday_block.map((task, idx) => (
                            <div key={idx} className="group bg-surface rounded-2xl p-4 border border-surface-variant hover:border-primary/30 transition-all cursor-pointer flex items-center gap-4">
                              <div className="w-6 h-6 rounded-full border-2 border-outline flex items-center justify-center group-hover:border-primary transition-colors"></div>
                              <div className="flex-1">
                                <h5 className="font-body-md text-body-md text-on-background">{task.name}</h5>
                                <p className="font-caption text-caption text-on-surface-variant">{task.time_slot}</p>
                              </div>
                              <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors">restaurant</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {/* Fallback if no tasks */}
                    {allTasks.length === 0 && (
                      <div className="text-center text-on-surface-variant py-10 font-body-md">
                        No tasks scheduled for today.
                      </div>
                    )}

                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
      <footer className="mt-auto w-full border-t border-surface-variant bg-surface-container-lowest pb-20 md:pb-0">
        <div className="flex flex-col md:flex-row justify-between items-center px-container-margin py-base gap-4 text-center md:text-left">
          <span className="font-caption text-caption text-on-surface-variant">© 2024 AiDincharya. Personalized Ayurvedic Wellness.</span>
          <div className="flex gap-6">
            <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a>
            <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a>
            <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Safety Guidelines</a>
          </div>
        </div>
      </footer>
    </>
  );
}
