import React, { createContext, useContext, useState, useEffect } from 'react';

export interface User {
  id: number;
  username: string;
  email?: string;
  role: string;
}

interface AuthContextType {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isSetupCompleted: boolean | null; // null = verification in progress
  isLoading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  checkSetupStatus: () => Promise<boolean>;
  authFetch: (url: string, options?: RequestInit) => Promise<Response>;
}


const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE = '/api';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('auth_token'));
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem('auth_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [isSetupCompleted, setIsSetupCompleted] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const checkSetupStatus = async (): Promise<boolean> => {
    try {
      const res = await fetch(`${API_BASE}/auth/setup-status`);
      if (res.ok) {
        const data = await res.json();
        setIsSetupCompleted(data.is_setup_completed);
        return data.is_setup_completed;
      }
    } catch (err) {
      console.error('Error checking setup status:', err);
    }
    return false;
  };

  const verifyMe = async (currentToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: {
          Authorization: `Bearer ${currentToken}`,
        },
      });
      if (res.ok) {
        const userData = await res.json();
        setUser(userData);
        localStorage.setItem('auth_user', JSON.stringify(userData));
      } else {
        // Token expiré ou invalide
        logout();
      }
    } catch (err) {
      console.error('Error verifying user:', err);
    }
  };

  useEffect(() => {
    const initAuth = async () => {
      setIsLoading(true);
      const setupDone = await checkSetupStatus();
      if (setupDone && token) {
        await verifyMe(token);
      }
      setIsLoading(false);
    };
    initAuth();
  }, []);

  const login = (newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem('auth_token', newToken);
    localStorage.setItem('auth_user', JSON.stringify(newUser));
    setIsSetupCompleted(true);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
  };

  const authFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
    const headers = new Headers(options.headers || {});
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
      logout();
    }
    return response;
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token && !!user,
        isSetupCompleted,
        isLoading,
        login,
        logout,
        checkSetupStatus,
        authFetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
