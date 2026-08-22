import { Link, useLocation, useNavigate } from 'react-router-dom';
import React from 'react';
import { useAuth } from '../context/AuthContext';

const NAV_ITEMS = [
  { path: '/', icon: 'dashboard', label: 'Dashboard' },
  { path: '/routine', icon: 'calendar_today', label: 'My Routine' },
  { path: '/insights', icon: 'insights', label: 'Insights' },
  { path: '/progress', icon: 'show_chart', label: 'Progress' },
  { path: '/profile', icon: 'person', label: 'Profile' },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { profile, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/welcome');
  };

  return (
    <div className="antialiased min-h-screen flex bg-background">
      {/* SideNavBar */}
      <nav className="hidden md:flex flex-col h-screen w-64 fixed left-0 top-0 bg-surface-container-low py-base border-r border-surface-variant z-40">
        <div className="px-container-margin py-base flex items-center gap-3 mb-8 cursor-pointer group" onClick={() => navigate('/profile')}>
          <div className="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-lg overflow-hidden shrink-0 group-hover:ring-2 ring-primary/50 transition-all">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="overflow-hidden">
            <h1 className="font-headline-md text-headline-md font-bold text-primary truncate">AiDincharya</h1>
            <p className="font-caption text-caption text-on-surface-variant truncate">
              {profile?.user?.username || 'Ayurvedic Wellness'}
            </p>
          </div>
        </div>
        
        <div className="flex-1 px-4 space-y-2">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
            return (
              <Link 
                key={item.path} 
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-full font-medium transition-colors ${
                  isActive 
                    ? 'text-primary font-bold bg-surface-container-high' 
                    : 'text-on-surface-variant hover:bg-surface-container-highest'
                }`}
              >
                <span className={`material-symbols-outlined ${isActive ? 'fill' : ''}`}>{item.icon}</span>
                <span className="font-label-md text-label-md">{item.label}</span>
              </Link>
            );
          })}
        </div>

        <div className="p-4 mt-auto space-y-2">
          <button className="w-full py-3 px-4 bg-primary text-on-primary rounded-full font-label-md text-label-md hover:opacity-90 transition-opacity flex items-center justify-center gap-2">
            <span className="material-symbols-outlined">play_arrow</span>
            Start Routine
          </button>
          <button 
            onClick={handleLogout}
            className="w-full py-2 px-4 text-on-surface-variant hover:bg-surface-container-highest rounded-full font-label-md text-label-md flex items-center justify-center gap-2 transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">logout</span>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <div className="flex-1 md:ml-64 flex flex-col min-h-screen w-full relative">
        {children}
      </div>

      {/* Bottom Nav for Mobile */}
      <nav className="md:hidden fixed bottom-0 left-0 w-full bg-surface border-t border-surface-variant flex justify-around py-3 pb-safe z-40 shadow-[0_-4px_20px_rgba(0,0,0,0.05)]">
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link 
              key={item.path} 
              to={item.path}
              className={`flex flex-col items-center gap-1 ${
                isActive ? 'text-primary' : 'text-on-surface-variant hover:text-primary transition-colors'
              }`}
            >
              <div className={isActive ? 'bg-primary-container/30 px-4 py-1 rounded-full' : 'px-4 py-1'}>
                <span className={`material-symbols-outlined ${isActive ? 'fill text-primary' : ''}`}>
                  {item.icon}
                </span>
              </div>
              <span className={`font-caption text-[10px] ${isActive ? 'font-bold' : ''}`}>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
