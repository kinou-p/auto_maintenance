import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { SetupAdmin } from '@/pages/SetupAdmin';
import { Login } from '@/pages/Login';
import { Dashboard } from '@/pages/Dashboard';
import { Containers } from '@/pages/Containers';
import { Projects } from '@/pages/Projects';
import { ScrollToTop } from '@/components/ui/ScrollToTop';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollToTop />
        <Routes>
          <Route path="/setup" element={<ProtectedRoute><SetupAdmin /></ProtectedRoute>} />
          <Route path="/login" element={<ProtectedRoute><Login /></ProtectedRoute>} />
          
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/projects" element={<ProtectedRoute><Projects /></ProtectedRoute>} />
          <Route path="/containers" element={<ProtectedRoute><Containers /></ProtectedRoute>} />
          
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

