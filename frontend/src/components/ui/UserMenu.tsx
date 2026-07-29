import React from 'react';
import { useAuth } from '@/context/AuthContext';
import { LogOut, ShieldCheck, Sliders } from 'lucide-react';
import { Link } from 'react-router-dom';


export const UserMenu: React.FC = () => {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <div className="flex items-center gap-3 bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-1.5">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <ShieldCheck className="w-4 h-4" />
        </div>
        <div className="flex flex-col text-left">
          <span className="text-xs font-semibold text-slate-200">{user.username}</span>
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">{user.role}</span>
        </div>
      </div>
      <div className="h-4 w-px bg-slate-800 my-auto ml-1" />
      <Link
        to="/settings"
        title="Paramètres système"
        className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-colors cursor-pointer"
      >
        <Sliders className="w-4 h-4" />
      </Link>
      <button
        onClick={logout}
        title="Se déconnecter"
        className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
};
