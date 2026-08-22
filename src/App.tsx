import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Routine } from './pages/Routine';
import { Insights } from './pages/Insights';
import { Progress } from './pages/Progress';
import { Profile } from './pages/Profile';
import { Welcome } from './pages/Welcome';
import { LearnMore } from './pages/LearnMore';
import { Onboarding } from './pages/Onboarding';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, profile } = useAuth();
  
  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-background text-on-background">Loading...</div>;
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/welcome" replace />;
  }

  // Only redirect to onboarding if the profile data explicitly shows it's incomplete
  // and we are not currently loading the profile.
  if (profile && !profile.state?.has_completed_onboarding) {
     return <Navigate to="/onboarding" replace />;
  }
  
  return <Layout>{children}</Layout>;
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/welcome" element={<Welcome />} />
          <Route path="/learn-more" element={<LearnMore />} />
          <Route path="/onboarding" element={<Onboarding />} />
          
          {/* Protected routes wrapped in Layout via ProtectedRoute */}
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/routine" element={<ProtectedRoute><Routine /></ProtectedRoute>} />
          <Route path="/insights" element={<ProtectedRoute><Insights /></ProtectedRoute>} />
          <Route path="/progress" element={<ProtectedRoute><Progress /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
