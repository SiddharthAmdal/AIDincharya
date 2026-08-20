import React from 'react';

export function Progress() {
  return (
    <>
      <header className="bg-surface docked full-width top-0 sticky z-30 flex justify-between items-center px-container-margin py-base w-full shadow-sm">
        <h2 className="font-headline-md text-headline-md font-bold text-primary md:hidden">AiDincharya</h2>
        <div className="hidden md:block">
        </div>
        <div className="flex items-center space-x-4 ml-auto">
          <button className="text-on-surface-variant hover:opacity-80 transition-opacity">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="text-on-surface-variant hover:opacity-80 transition-opacity">
            <span className="material-symbols-outlined">settings</span>
          </button>
          <button className="hidden md:block font-label-md text-label-md text-on-surface-variant border border-outline px-4 py-1.5 rounded-full hover:bg-surface-variant transition-colors">
            Test Mode
          </button>
          <div className="w-8 h-8 rounded-full overflow-hidden hidden md:block">
            <img alt="User avatar" className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAaWmOKk0TwStOEFTgcB2p0sW3nFXZiHC4p-C-VBvk9TYLct7JSkatpqPrBjKIfAlQpmrPufLpCrLqLF1D08JhwlMbN8OYbR1AAjpQkatq4YwtNBFAghNYZu79oDa7WKB1k7aQ1MD1RF3c6ORa5tEutSTJQFD2uBt538HkISYVT_J_KPnoqJynqeVXzMLlzi7DE3kBq09KF1ui72jSM08cffQzK2rxFlAxYQSkVm251wEibSRQxD3mniQ" />
          </div>
        </div>
      </header>

      <div className="w-full min-h-screen px-container-margin py-section-gap-md flex flex-col gap-section-gap-md pb-32">
        <header className="mb-4">
          <h2 className="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-background mb-2">Your Progress</h2>
          <p className="font-body-md text-body-md text-on-surface-variant">Review your daily adherence and habit consistency.</p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
          <div className="md:col-span-8 bg-surface-container-lowest rounded-xl p-6 shadow-sm border border-surface-variant flex flex-col">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="font-headline-md text-headline-md text-on-background">This week: <span className="text-primary font-bold">76%</span></h3>
                <p className="font-caption text-caption text-on-surface-variant">Overall routine adherence</p>
              </div>
              <button className="text-on-surface-variant hover:text-primary transition-colors">
                <span className="material-symbols-outlined">more_horiz</span>
              </button>
            </div>
            <div className="flex-1 min-h-[200px] flex items-end justify-between gap-2 mt-4 relative">
              <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-caption text-on-surface-variant opacity-50 pr-2 pointer-events-none">
                <span>100%</span>
                <span>50%</span>
                <span>0%</span>
              </div>
              <div className="absolute left-8 right-0 top-0 bottom-0 flex flex-col justify-between pointer-events-none">
                <div className="w-full border-t border-dashed border-surface-variant h-0"></div>
                <div className="w-full border-t border-dashed border-surface-variant h-0"></div>
                <div className="w-full border-t border-solid border-surface-variant h-0"></div>
              </div>
              <div className="ml-8 w-full flex justify-between items-end h-full z-10 px-2 pb-1">
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[60%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-primary rounded-t-lg h-[80%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Mon</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[85%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-primary rounded-t-lg h-[100%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Tue</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[40%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-secondary rounded-t-lg h-[50%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Wed</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[90%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-primary rounded-t-lg h-[95%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Thu</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[70%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-primary rounded-t-lg h-[85%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Fri</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[50%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-secondary rounded-t-lg h-[60%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Sat</span>
                </div>
                <div className="flex flex-col items-center gap-2 group w-[10%] h-full justify-end">
                  <div className="w-full bg-surface-variant rounded-t-lg h-[20%] relative group-hover:bg-primary-container transition-colors">
                    <div className="absolute bottom-0 left-0 right-0 bg-surface-dim rounded-t-lg h-[30%]"></div>
                  </div>
                  <span className="font-caption text-caption text-on-surface-variant">Sun</span>
                </div>
              </div>
            </div>
          </div>

          <div className="md:col-span-4 flex flex-col gap-gutter">
            <div className="bg-primary-container text-on-primary-container rounded-xl p-6 shadow-sm flex flex-col justify-center items-center relative overflow-hidden group">
              <div className="absolute -right-8 -top-8 w-32 h-32 bg-primary opacity-10 rounded-full group-hover:scale-110 transition-transform duration-500"></div>
              <span className="material-symbols-outlined text-4xl mb-2 filled-icon">local_fire_department</span>
              <h3 className="font-headline-display text-headline-display font-bold">4</h3>
              <p className="font-label-md text-label-md mt-1">Day Streak</p>
              <p className="font-caption text-caption opacity-80 mt-2 text-center">Consistent anchor habits</p>
            </div>
            <div className="bg-surface-container-lowest rounded-xl p-6 shadow-sm border border-surface-variant flex-1 flex flex-col justify-center">
              <h4 className="font-label-md text-label-md text-on-surface-variant mb-4">Weekly Breakdown</h4>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                      <span className="material-symbols-outlined text-sm">check</span>
                    </div>
                    <span className="font-body-md text-body-md text-on-background">Completed</span>
                  </div>
                  <span className="font-label-md text-label-md">24</span>
                </div>
                <div className="w-full h-[1px] bg-surface-variant"></div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-secondary/10 flex items-center justify-center text-secondary">
                      <span className="material-symbols-outlined text-sm">close</span>
                    </div>
                    <span className="font-body-md text-body-md text-on-background">Missed</span>
                  </div>
                  <span className="font-label-md text-label-md">8</span>
                </div>
              </div>
            </div>
          </div>

          <div className="md:col-span-12 bg-surface-container-low rounded-xl p-8 shadow-sm border border-surface-variant relative overflow-hidden flex flex-col md:flex-row items-center gap-8">
            <div className="absolute left-0 bottom-0 w-64 h-64 bg-primary-fixed-dim opacity-20 blur-3xl rounded-full pointer-events-none"></div>
            <div className="flex-shrink-0 w-24 h-24 rounded-full bg-primary-container flex items-center justify-center shadow-inner relative z-10">
              <span className="material-symbols-outlined text-4xl text-on-primary-container filled-icon">spa</span>
            </div>
            <div className="flex-1 relative z-10 text-center md:text-left">
              <h3 className="font-headline-md text-headline-md text-on-background mb-2">Adaptation Insight</h3>
              <p className="font-body-lg text-body-lg text-on-surface-variant mb-4">
                  Your routine is currently <strong className="text-primary font-semibold">Balanced</strong>. Maintain anchor habits for continued progress.
              </p>
              <button className="font-label-md text-label-md text-primary border-b border-primary pb-1 hover:text-primary-container transition-colors">
                  Read full analysis
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
