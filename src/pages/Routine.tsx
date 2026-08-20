import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { scheduleService } from '../api';
import type { ScheduleResponse, RoutineTask } from '../api';

export function Routine() {
  const { profile } = useAuth();
  const [scheduleData, setScheduleData] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [completedTasks, setCompletedTasks] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function loadSchedule() {
      try {
        const data = await scheduleService.getToday();
        setScheduleData(data);
      } catch (err) {
        console.error("Failed to load schedule:", err);
      } finally {
        setLoading(false);
      }
    }
    loadSchedule();
  }, []);

  const toggleTask = async (taskName: string) => {
    const newCompleted = new Set(completedTasks);
    if (newCompleted.has(taskName)) {
      newCompleted.delete(taskName);
    } else {
      newCompleted.add(taskName);
    }
    setCompletedTasks(newCompleted);

    // Log adherence to backend
    if (profile?.user?.id) {
      try {
        const allTasks = scheduleData ? [
          ...scheduleData.schedule.morning_block,
          ...scheduleData.schedule.midday_block,
          ...scheduleData.schedule.evening_block
        ].map(t => t.name) : [];

        await scheduleService.logAdherence({
          user_id: profile.user.id.toString(),
          completed_practices: Array.from(newCompleted),
          recommended_practices: allTasks
        });
      } catch (err) {
        console.error("Failed to log adherence:", err);
      }
    }
  };

  const renderBlock = (title: string, icon: string, timeRange: string, tasks: RoutineTask[], themeClass: string) => {
    if (!tasks || tasks.length === 0) return null;
    
    return (
      <section className="relative transition-opacity duration-300">
        <div className={`absolute -left-[21px] md:-left-[37px] top-1 w-10 h-10 rounded-full bg-surface-bright border-4 border-surface flex items-center justify-center shadow-sm ${themeClass}`}>
          <span className="material-symbols-outlined text-[20px]">{icon}</span>
        </div>
        <h3 className="font-headline-lg text-headline-lg text-on-surface mb-6 flex items-center gap-3">
          {title}
          <span className="font-label-md text-label-md font-normal text-outline bg-surface-container px-3 py-1 rounded-full">{timeRange}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
          {tasks.map((task, idx) => {
            const isCompleted = completedTasks.has(task.name);
            return (
              <div key={idx} className={`bg-surface-container-lowest rounded-xl p-container-margin shadow-[0_4px_20px_rgba(0,0,0,0.02)] border border-outline-variant hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] transition-all duration-300 flex items-start gap-4 ${isCompleted ? 'opacity-75' : ''}`}>
                <button 
                  onClick={() => toggleTask(task.name)}
                  className={`mt-1 w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors cursor-pointer ${
                    isCompleted ? 'bg-primary border-primary text-on-primary' : 'border-2 border-outline hover:border-primary text-transparent hover:text-primary bg-surface-container-lowest'
                  }`}
                >
                  <span className={`material-symbols-outlined text-[18px] ${isCompleted ? 'opacity-100' : 'opacity-0 hover:opacity-100'} transition-opacity`}>check</span>
                </button>
                <div className="flex-grow">
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-label-md text-label-md text-outline">{task.time_slot}</span>
                    <span className="font-caption text-caption text-on-surface-variant bg-surface-container px-2 py-0.5 rounded flex items-center gap-1">
                      <span className="material-symbols-outlined text-[14px]">timer</span> {task.duration_minutes} min
                    </span>
                  </div>
                  <h4 className={`font-body-lg text-body-lg font-medium text-on-surface mb-2 ${isCompleted ? 'line-through decoration-outline/50' : ''}`}>{task.name}</h4>
                  <p className="font-caption text-caption text-on-surface-variant mb-4">{task.description}</p>
                  <div className="flex items-center gap-2">
                    <button className="inline-flex items-center gap-1 font-caption text-caption text-primary hover:text-primary-container transition-colors bg-primary-fixed/30 px-2 py-1 rounded-full">
                      <span className="material-symbols-outlined text-[14px]">help</span>
                      Why this?
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <>
      <header className="flex justify-between items-center px-container-margin py-base bg-surface top-0 sticky z-30 transition-opacity hover:opacity-80 md:w-full w-full">
        <div className="flex items-center md:hidden">
          <h1 className="font-headline-md text-headline-md font-bold text-primary tracking-tight">AiDincharya</h1>
        </div>
        <div className="hidden md:block"></div>
        <div className="flex items-center gap-gutter ml-auto">
          <span className="font-label-md text-label-md text-secondary border border-secondary/30 px-3 py-1 rounded-full bg-secondary-container/10 hidden sm:block">Test Mode</span>
          <button className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container transition-colors">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="w-10 h-10 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container transition-colors hidden md:flex">
            <span className="material-symbols-outlined">settings</span>
          </button>
          <div className="w-8 h-8 rounded-full bg-surface-variant overflow-hidden md:hidden flex items-center justify-center font-bold text-primary">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
        </div>
      </header>

      <main className="flex-grow px-4 md:px-container-margin py-section-gap-md max-w-5xl mx-auto w-full">
        {loading ? (
          <div className="flex justify-center py-20 text-on-surface-variant font-body-md">Loading routine...</div>
        ) : (
          <>
            {scheduleData?.behavioral_nudge && (
              <div className="mb-section-gap-md bg-tertiary-container/30 border border-tertiary-container rounded-xl p-4 flex items-start gap-4 shadow-sm backdrop-blur-sm">
                <div className="w-8 h-8 rounded-full bg-tertiary-container flex items-center justify-center text-on-tertiary-container shrink-0 mt-0.5">
                  <span className="material-symbols-outlined text-[18px]">info</span>
                </div>
                <div>
                  <h3 className="font-label-md text-label-md text-on-surface font-semibold mb-1">{scheduleData.behavioral_nudge.title}</h3>
                  <p className="font-body-md text-body-md text-on-surface-variant">{scheduleData.behavioral_nudge.message}</p>
                </div>
              </div>
            )}

            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10">
              <div>
                <h2 className="font-headline-display text-headline-display text-on-surface mb-2 hidden md:block">My Routine</h2>
                <h2 className="font-headline-lg-mobile text-headline-lg-mobile text-on-surface mb-2 md:hidden">My Routine</h2>
                <p className="font-body-lg text-body-lg text-outline">Today • {scheduleData?.schedule?.routine_complexity || 'Adaptive'} Plan</p>
              </div>
              <button className="flex items-center justify-center gap-2 px-6 py-3 rounded-full border-[1.5px] border-tertiary text-tertiary font-label-md text-label-md hover:bg-tertiary/5 transition-colors self-start md:self-auto bg-surface-container-lowest shadow-sm">
                <span className="material-symbols-outlined text-[18px]">forum</span>
                Ask Vaidya to adjust schedule
              </button>
            </div>

            <div className="relative pl-4 md:pl-8 border-l-2 border-surface-container-highest space-y-section-gap-lg">
              {renderBlock("Morning", "routine", "6:00 AM - 10:00 AM", scheduleData?.schedule?.morning_block || [], "text-primary")}
              {renderBlock("Midday", "light_mode", "10:00 AM - 4:00 PM", scheduleData?.schedule?.midday_block || [], "text-secondary")}
              {renderBlock("Evening", "dark_mode", "4:00 PM - 10:00 PM", scheduleData?.schedule?.evening_block || [], "text-tertiary")}
              
              {!scheduleData?.schedule && (
                <div className="text-on-surface-variant font-body-md">No schedule available.</div>
              )}
            </div>
          </>
        )}
      </main>
    </>
  );
}
