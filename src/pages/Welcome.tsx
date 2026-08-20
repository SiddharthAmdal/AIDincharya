import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function Welcome() {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (isRegisterMode) {
        await register(username, password);
      } else {
        await login(username, password);
      }
      navigate('/');
    } catch (err: any) {
      setError(err.data?.detail || 'Authentication failed. Please try again.');
    }
  };

  return (
    <div className="bg-background text-on-background font-body-md antialiased min-h-screen flex flex-col selection:bg-primary-container selection:text-on-primary-container">
      <header className="w-full px-container-margin py-base flex justify-between items-center absolute top-0 z-50">
        <div className="font-headline-md text-headline-md font-bold text-primary">AiDincharya</div>
        <button 
          onClick={() => { setIsLoginModalOpen(true); setIsRegisterMode(false); }} 
          className="font-label-md text-label-md text-primary px-4 py-2 hover:bg-surface-container-high rounded-full transition-colors"
        >
          Sign In
        </button>
      </header>
      
      <main className="flex-grow flex flex-col justify-center relative overflow-hidden hero-pattern">
        <div className="absolute top-0 right-0 -mr-32 -mt-32 w-[600px] h-[600px] bg-primary-fixed opacity-30 rounded-full blur-3xl pointer-events-none"></div>
        <div className="absolute bottom-0 left-0 -ml-32 -mb-32 w-[500px] h-[500px] bg-secondary-fixed opacity-30 rounded-full blur-3xl pointer-events-none"></div>
        
        <div className="max-w-7xl mx-auto px-container-margin md:px-20 lg:px-40 relative z-10 flex flex-col lg:flex-row items-center gap-section-gap-lg py-20">
          <div className="flex-1 flex flex-col gap-section-gap-md max-w-2xl">
            <div>
              <span className="inline-block px-3 py-1 bg-surface-container-high text-on-surface-variant font-label-md text-label-md rounded-full mb-6">Personalized Ayurvedic Wellness</span>
              <h1 className="font-headline-display text-headline-display text-on-background mb-4">Your Intelligent Path to Ayurvedic Harmony.</h1>
              <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">
                Discover your unique Prakriti (mind-body constitution) through our advanced assessment. We craft personalized daily routines, bridging ancient Ayurvedic wisdom with modern intelligence to restore your natural balance.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-4">
              <button 
                onClick={() => { setIsLoginModalOpen(true); setIsRegisterMode(true); }}
                className="bg-primary text-on-primary font-label-md text-label-md px-8 py-4 rounded-full hover:bg-surface-tint transition-colors flex items-center justify-center gap-2 group shadow-[0_4px_20px_rgba(69,85,56,0.15)] hover:shadow-[0_8px_30px_rgba(69,85,56,0.25)]"
              >
                Begin Your Assessment
                <span className="material-symbols-outlined text-[18px] group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </button>
              <Link to="/learn-more" className="border-2 border-tertiary text-tertiary font-label-md text-label-md px-8 py-4 rounded-full hover:bg-surface-container-high transition-colors flex items-center justify-center">
                Learn More
              </Link>
            </div>
            
            <div className="flex items-center gap-4 mt-8 pt-8 border-t border-surface-variant">
              <div className="flex -space-x-3">
                <div className="w-10 h-10 rounded-full bg-surface-container-highest border-2 border-surface flex items-center justify-center overflow-hidden">
                  <img className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBNu3VlWLIskHvqVs69R3JnW0i_hwTuw-z91WG36Z135iuEeLDrDcAKz4DGcQR4MJgEazilH_k6Qn1N5jdltwcaaIy52nfAaCGiPizVqALv1OldvNMV8dAheONHndEDfKKAcDx4311KaITOWkk2Oz78UfqHJGiXS9V2ZKYCv4qvkr7lRyWFHLnJv3Kb6idXUaryHCVtGwaWD5FCJp3o9D9F8ZbqP5BVC-C2cVUpDAmCPrCpTu8BGcHnjg" alt="Avatar" />
                </div>
                <div className="w-10 h-10 rounded-full bg-surface-container-highest border-2 border-surface flex items-center justify-center overflow-hidden">
                  <img className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAyKNGdVFH2f6gTX63jmsYuWFg18QB75eiiiouGA1XiPGxKzS1xu8jFNIyeuHtW5UsLH0ycb3r__25ay2Ni8muDx2TGy0x4F0yLiRu_UxuSsTwYcH7TGTGCsskqkwllSa6rmZOm3hcCTkDzK2UVMFlm-0HdCvef70EIXWje40v1CRO3w4MLN-m1OxZTtYDLiSUbe3aaAomLXH1-zsI366HatsJeh7UyCaOFLdAV6lDerehhOSM55cmp7Q" alt="Avatar" />
                </div>
                <div className="w-10 h-10 rounded-full bg-surface-container-highest border-2 border-surface flex items-center justify-center overflow-hidden">
                  <img className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCHYPTs4odiUey6IO2M1CLSr07Ii1kzWy5-g3Vsi6ugyx6EFAiBVjbdWpX66cvMe5Fn4Uu_kULAdeW1MFjOulIMXZt5Bor76eMhTR86X0aRweFzP01LVgETfUsf8CQUoPYysGg2U0kGYZUxg4l9zsvBYXJocKC6OTwsRfxdR48FAYTckd8a88THwdYzaneGqnj44SKA9S3Uhdec1Dxre8gOoHymDGyumZDZC0k7wy1uX_2AKAy3KwxrhQ" alt="Avatar" />
                </div>
              </div>
              <p className="font-caption text-caption text-on-surface-variant">
                Join thousands finding balance<br/>through personalized routines.
              </p>
            </div>
          </div>
          
          <div className="flex-1 w-full relative">
            <div className="grid grid-cols-2 gap-4 h-[600px]">
              <div className="col-span-1 row-span-2 rounded-[32px] overflow-hidden shadow-[0_8px_30px_rgba(0,0,0,0.04)] relative group">
                <img className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCZLXqW_tNdtmZsyBwIqRuoPVhKhdWeF7uvoqOcmTJBO_PbCafiPs3L0sbjfooGF6uY0w1KcDPQq-IMIqfqhjuzL2YIQMs6nYTowV_dLK6HZpHNhwcyCoL195Zi1oRO4MYnJAE6hdP3Ki15ENXdXo7Hyi8RuN-Mhi91_7ZDVNQuqsU38haA6wbZW2iS0ZhuenuFp1fZoTWiQNLw5i_DBms9XX1D7e-pSLavaKCwebtKWfA3LovnqYdkvg" alt="Bonsai" />
                <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black/50 to-transparent">
                  <span className="text-white font-label-md text-label-md">Discover Prakriti</span>
                </div>
              </div>
              <div className="col-span-1 row-span-1 rounded-[32px] overflow-hidden bg-primary-container shadow-[0_4px_20px_rgba(0,0,0,0.04)] p-8 flex flex-col justify-between">
                <span className="material-symbols-outlined text-on-primary-container text-4xl mb-4">self_improvement</span>
                <h3 className="font-headline-md text-headline-md text-on-primary-container">Daily Routine</h3>
                <p className="font-body-md text-body-md text-on-primary-container opacity-80 mt-2">Tailored to your dosha.</p>
              </div>
              <div className="col-span-1 row-span-1 rounded-[32px] overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.04)] relative group">
                <img className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAex_dc0RmBO2i42Cb5VxxRnYtU1ht2OBF43bhK75WjCs0ighoH4MLds07QSPd7IELVD_T5RElCduCV_w7PBPjVeBsOnLN4RvxXUDkZm_-6i_HONg4vuZ2lx0Qp8AImJd80L-RoJlavze9M8sPAF31GFQJbLJ-1ppbw9dnBd6ee7NjyjZPexjhxGhRRJC8sNMJ34EMTVDoo8BmSrZuQ77Wfsr2WwoDKRQQzBc1GNsmGXXhzTcMCiw7FLA" alt="Dunes" />
              </div>
            </div>
            <div className="absolute top-1/2 -left-12 transform -translate-y-1/2 bg-surface p-4 rounded-2xl shadow-[0_8px_30px_rgba(0,0,0,0.08)] flex items-center gap-4 animate-[bounce_3s_ease-in-out_infinite]">
              <div className="w-12 h-12 rounded-full bg-primary-container flex items-center justify-center">
                <span className="material-symbols-outlined text-on-primary-container">spa</span>
              </div>
              <div>
                <p className="font-label-md text-label-md text-on-surface">Dosha Balanced</p>
                <p className="font-caption text-caption text-on-surface-variant">Vata, Pitta, Kapha</p>
              </div>
            </div>
          </div>
        </div>
      </main>
      <footer className="w-full bg-surface-container-lowest flex flex-col md:flex-row justify-between items-center px-container-margin py-base z-10 border-t border-surface-variant mt-auto">
        <div className="font-label-md text-label-md text-primary">AiDincharya</div>
        <p className="font-caption text-caption text-on-surface-variant mt-2 md:mt-0">© 2024 AiDincharya. Personalized Ayurvedic Wellness.</p>
        <div className="flex gap-4 mt-2 md:mt-0">
          <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a>
          <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a>
          <a className="font-caption text-caption text-on-surface-variant hover:text-primary transition-colors" href="#">Safety Guidelines</a>
        </div>
      </footer>

      {/* Login / Register Modal */}
      {isLoginModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-surface rounded-3xl p-8 max-w-md w-full shadow-2xl relative">
            <button 
              onClick={() => setIsLoginModalOpen(false)}
              className="absolute top-4 right-4 text-on-surface-variant hover:bg-surface-container rounded-full p-2"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
            <h2 className="font-headline-md text-headline-md mb-2 text-on-surface">
              {isRegisterMode ? 'Create Account' : 'Welcome Back'}
            </h2>
            <p className="font-body-md text-body-md text-on-surface-variant mb-6">
              {isRegisterMode ? 'Begin your journey to balance.' : 'Sign in to access your routine.'}
            </p>
            
            {error && (
              <div className="bg-error-container text-on-error-container p-3 rounded-lg text-sm mb-4">
                {error}
              </div>
            )}
            
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block font-label-md text-label-md text-on-surface mb-1">Username</label>
                <input 
                  type="text" 
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-surface-container rounded-xl px-4 py-3 font-body-md border border-outline-variant focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block font-label-md text-label-md text-on-surface mb-1">Password</label>
                <input 
                  type="password" 
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-surface-container rounded-xl px-4 py-3 font-body-md border border-outline-variant focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>
              <button 
                type="submit"
                className="w-full bg-primary text-on-primary font-label-md text-label-md py-3 rounded-full hover:bg-surface-tint transition-colors mt-2"
              >
                {isRegisterMode ? 'Sign Up' : 'Sign In'}
              </button>
            </form>
            
            <div className="mt-6 text-center font-body-md text-body-md">
              <span className="text-on-surface-variant">
                {isRegisterMode ? 'Already have an account? ' : "Don't have an account? "}
              </span>
              <button 
                onClick={() => setIsRegisterMode(!isRegisterMode)}
                className="text-primary font-medium hover:underline"
              >
                {isRegisterMode ? 'Sign In' : 'Sign Up'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
