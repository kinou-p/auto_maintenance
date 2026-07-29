import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Loader2 } from 'lucide-react';

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isSetupCompleted, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-400 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
        <span className="text-sm">Vérification de la sécurité...</span>
      </div>
    );
  }

  // 1. Si la configuration initiale n'est pas faite, rediriger vers /setup
  if (isSetupCompleted === false) {
    if (location.pathname !== '/setup') {
      return <Navigate to="/setup" replace />;
    }
  }

  // 2. Si le setup est fait mais pas authentifié, rediriger vers /login
  if (isSetupCompleted === true && !isAuthenticated) {
    if (location.pathname !== '/login' && location.pathname !== '/setup') {
      return <Navigate to="/login" replace />;
    }
  }

  // 3. Si l'utilisateur est déjà configuré et authentifié mais essaie d'aller sur /setup ou /login
  if (isAuthenticated && (location.pathname === '/login' || location.pathname === '/setup')) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};
