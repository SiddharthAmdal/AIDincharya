import React from 'react';
import { Link } from 'react-router-dom';

export function LearnMore() {
  return (
    <div className="bg-background text-on-background font-body-md antialiased min-h-screen flex flex-col">
      <header className="w-full px-container-margin py-base flex justify-between items-center sticky top-0 z-50 bg-background/80 backdrop-blur-md border-b border-surface-variant/30">
        <div className="font-headline-md text-headline-md font-bold text-primary">AiDincharya</div>
        <div className="flex gap-4">
          <Link to="/welcome" className="font-label-md text-label-md text-on-surface-variant px-4 py-2 hover:bg-surface-container-high rounded-full transition-colors">Back to Home</Link>
          <Link to="/welcome" className="font-label-md text-label-md text-primary border border-primary px-4 py-2 hover:bg-primary-container rounded-full transition-colors">Sign In</Link>
        </div>
      </header>

      <main className="flex-grow">
        {/* Hero Section */}
        <section className="px-container-margin py-section-gap-lg text-center max-w-4xl mx-auto">
          <h1 className="font-headline-display text-[40px] md:text-headline-display text-on-surface mb-6">The Science of Life</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mx-auto leading-relaxed">
            Ayurveda, literally translating to "The Science of Life," is an ancient holistic healing system. 
            At its core is the understanding that we are all made of the same five elements found in nature—Space, Air, Fire, Water, and Earth.
          </p>
        </section>

        {/* What are Doshas */}
        <section className="bg-surface-container-low px-container-margin py-section-gap-lg">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="font-headline-lg text-headline-lg text-on-surface mb-4">Understanding Doshas</h2>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-2xl mx-auto">
                The five elements pair up to form three primary energies known as Doshas: Vata, Pitta, and Kapha. 
                Everyone has a unique combination of all three, known as your <strong>Prakriti</strong> (natural constitution).
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {/* Vata Card */}
              <div className="bg-surface-container-lowest p-8 rounded-3xl border border-primary/20 shadow-sm relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 bg-primary-fixed/20 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
                <div className="w-16 h-16 rounded-full bg-primary-container flex items-center justify-center mb-6">
                  <span className="material-symbols-outlined text-3xl text-on-primary-container">air</span>
                </div>
                <h3 className="font-headline-md text-headline-md text-primary mb-2">Vata</h3>
                <p className="font-label-md text-label-md text-on-surface-variant mb-4 uppercase tracking-wider">Air & Space</p>
                <p className="font-body-md text-body-md text-on-surface mb-6">
                  The energy of movement. Vata governs all bodily functions related to motion, including blood circulation, breathing, and the nervous system.
                </p>
                <ul className="space-y-3 font-body-md text-body-md text-on-surface-variant">
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-primary text-[20px]">check_circle</span>
                    <span><strong>When balanced:</strong> Creative, energetic, flexible, and lively.</span>
                  </li>
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-error text-[20px]">warning</span>
                    <span><strong>When imbalanced:</strong> Anxious, restless, dry skin, and irregular digestion.</span>
                  </li>
                </ul>
              </div>

              {/* Pitta Card */}
              <div className="bg-surface-container-lowest p-8 rounded-3xl border border-secondary/20 shadow-sm relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 bg-secondary-fixed/20 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
                <div className="w-16 h-16 rounded-full bg-secondary-container flex items-center justify-center mb-6">
                  <span className="material-symbols-outlined text-3xl text-on-secondary-container">local_fire_department</span>
                </div>
                <h3 className="font-headline-md text-headline-md text-secondary mb-2">Pitta</h3>
                <p className="font-label-md text-label-md text-on-surface-variant mb-4 uppercase tracking-wider">Fire & Water</p>
                <p className="font-body-md text-body-md text-on-surface mb-6">
                  The energy of transformation. Pitta governs digestion, metabolism, energy production, and intelligence.
                </p>
                <ul className="space-y-3 font-body-md text-body-md text-on-surface-variant">
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-secondary text-[20px]">check_circle</span>
                    <span><strong>When balanced:</strong> Intelligent, decisive, warm, and highly focused.</span>
                  </li>
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-error text-[20px]">warning</span>
                    <span><strong>When imbalanced:</strong> Irritable, inflammatory conditions, and acid reflux.</span>
                  </li>
                </ul>
              </div>

              {/* Kapha Card */}
              <div className="bg-surface-container-lowest p-8 rounded-3xl border border-tertiary/20 shadow-sm relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 bg-tertiary-fixed/20 rounded-bl-full -z-10 group-hover:scale-110 transition-transform"></div>
                <div className="w-16 h-16 rounded-full bg-tertiary-container flex items-center justify-center mb-6">
                  <span className="material-symbols-outlined text-3xl text-on-tertiary-container">water_drop</span>
                </div>
                <h3 className="font-headline-md text-headline-md text-tertiary mb-2">Kapha</h3>
                <p className="font-label-md text-label-md text-on-surface-variant mb-4 uppercase tracking-wider">Earth & Water</p>
                <p className="font-body-md text-body-md text-on-surface mb-6">
                  The energy of structure. Kapha supplies water to all body parts, moisturizes the skin, and maintains the immune system.
                </p>
                <ul className="space-y-3 font-body-md text-body-md text-on-surface-variant">
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-tertiary text-[20px]">check_circle</span>
                    <span><strong>When balanced:</strong> Calm, loving, forgiving, and physically strong.</span>
                  </li>
                  <li className="flex gap-2 items-start">
                    <span className="material-symbols-outlined text-error text-[20px]">warning</span>
                    <span><strong>When imbalanced:</strong> Lethargic, prone to weight gain, and resistant to change.</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Body Type Analysis */}
        <section className="px-container-margin py-section-gap-lg">
          <div className="max-w-5xl mx-auto flex flex-col lg:flex-row items-center gap-12">
            <div className="flex-1 space-y-6">
              <h2 className="font-headline-lg text-headline-lg text-on-surface">Prakriti vs. Vikriti</h2>
              <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
                Your <strong>Prakriti</strong> is your unique blueprint—the exact ratio of Vata, Pitta, and Kapha you were born with. This never changes. It determines your physical characteristics, natural inclinations, and how you react to stress.
              </p>
              <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
                Your <strong>Vikriti</strong> is your current state of balance. Diet, seasons, stress, and lifestyle can push your doshas out of their natural equilibrium. When your Vikriti deviates significantly from your Prakriti, illness and discomfort arise.
              </p>
              <div className="bg-primary-container/20 border-l-4 border-primary p-6 rounded-r-2xl mt-4">
                <h4 className="font-label-md text-label-md text-on-surface mb-2">How AiDincharya Helps</h4>
                <p className="font-caption text-caption text-on-surface-variant">
                  Through intelligent questionnaires and wearable telemetry, we identify both your baseline (Prakriti) and your daily deviations (Vikriti). We then generate a personalized "Dinacharya" (daily routine) to pull you back into natural harmony.
                </p>
              </div>
            </div>
            <div className="flex-1 w-full relative">
              <div className="aspect-square bg-surface-container-high rounded-full overflow-hidden relative shadow-2xl p-8 flex items-center justify-center">
                <div className="absolute inset-0 bg-gradient-to-tr from-primary-container via-secondary-container to-tertiary-container opacity-30 animate-pulse"></div>
                <img 
                  className="relative z-10 w-full h-full object-cover rounded-full shadow-inner" 
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuAex_dc0RmBO2i42Cb5VxxRnYtU1ht2OBF43bhK75WjCs0ighoH4MLds07QSPd7IELVD_T5RElCduCV_w7PBPjVeBsOnLN4RvxXUDkZm_-6i_HONg4vuZ2lx0Qp8AImJd80L-RoJlavze9M8sPAF31GFQJbLJ-1ppbw9dnBd6ee7NjyjZPexjhxGhRRJC8sNMJ34EMTVDoo8BmSrZuQ77Wfsr2WwoDKRQQzBc1GNsmGXXhzTcMCiw7FLA" 
                  alt="Balance" 
                />
              </div>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="bg-primary text-on-primary py-section-gap-lg px-container-margin text-center">
          <h2 className="font-headline-md text-[32px] font-bold mb-4">Ready to discover your unique constitution?</h2>
          <p className="font-body-md text-primary-fixed mb-8 max-w-xl mx-auto">
            Take our assessment to map your Prakriti and receive a tailored routine that synchronizes your body with nature.
          </p>
          <Link to="/welcome" className="inline-block bg-primary-container text-on-primary-container font-label-md text-label-md px-8 py-4 rounded-full hover:bg-surface-tint hover:text-on-primary transition-colors shadow-lg">
            Start Your Journey
          </Link>
        </section>
      </main>
      
      <footer className="w-full bg-surface-container-lowest flex flex-col md:flex-row justify-between items-center px-container-margin py-base z-10 border-t border-surface-variant">
        <div className="font-label-md text-label-md text-primary">AiDincharya</div>
        <p className="font-caption text-caption text-on-surface-variant mt-2 md:mt-0">© 2024 AiDincharya. Personalized Ayurvedic Wellness.</p>
        <div className="flex gap-4 mt-2 md:mt-0">
          <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a>
          <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a>
        </div>
      </footer>
    </div>
  );
}
