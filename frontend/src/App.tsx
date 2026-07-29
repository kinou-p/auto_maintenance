import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ScrollToTop } from '@/components/ui/ScrollToTop';

const SetupAdmin = lazy(() => import('@/pages/SetupAdmin').then(m => ({ default: m.SetupAdmin })));
const Login = lazy(() => import('@/pages/Login').then(m => ({ default: m.Login })));
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Containers = lazy(() => import('@/pages/Containers').then(m => ({ default: m.Containers })));
const Projects = lazy(() => import('@/pages/Projects').then(m => ({ default: m.Projects })));

function PageLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-slate-950 text-slate-400">
      <div className="flex items-center space-x-3">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"></div>
        <span className="text-sm font-medium">Chargement...</span>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollToTop />
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/setup" element={<ProtectedRoute><SetupAdmin /></ProtectedRoute>} />
            <Route path="/login" element={<ProtectedRoute><Login /></ProtectedRoute>} />
            
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/projects" element={<ProtectedRoute><Projects /></ProtectedRoute>} />
            <Route path="/containers" element={<ProtectedRoute><Containers /></ProtectedRoute>} />
            
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

