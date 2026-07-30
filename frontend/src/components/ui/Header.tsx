import React from 'react';
import { Link } from 'react-router-dom';
import { Wrench, LayoutGrid, FolderOpen, Layers, Sliders } from 'lucide-react';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { UserMenu } from '@/components/ui/UserMenu';

export type ActivePage = 'dashboard' | 'projects' | 'containers' | 'settings';

interface HeaderProps {
  activePage: ActivePage;
  rightActions?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({ activePage, rightActions }) => {
  const navItems: { id: ActivePage; label: string; to: string; icon: React.FC<{ className?: string }> }[] = [
    { id: 'dashboard', label: 'Dashboard', to: '/', icon: LayoutGrid },
    { id: 'projects', label: 'Projets', to: '/projects', icon: FolderOpen },
    { id: 'containers', label: 'Conteneurs', to: '/containers', icon: Layers },
    { id: 'settings', label: 'Paramètres', to: '/settings', icon: Sliders },
  ];

  return (
    <header className="sticky top-0 z-40 bg-slate-900/80 backdrop-blur-xl border-b border-slate-800 px-4 md:px-6 py-3.5 flex items-center justify-between shadow-xl">
      {/* Brand & Logo */}
      <div className="flex items-center space-x-6">
        <Link
          to="/"
          className="flex items-center space-x-3 text-slate-300 hover:text-white transition-all group"
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20 group-hover:scale-105 transition-transform">
            <Wrench className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="font-extrabold text-base md:text-lg text-slate-100 block leading-tight tracking-tight">
              Auto Maintenance
            </span>
            <span className="text-[11px] text-slate-400 font-medium">WP Automation Engine</span>
          </div>
        </Link>

        {/* Navigation Links */}
        <nav className="hidden md:flex items-center space-x-1.5 bg-slate-950/60 p-1 rounded-xl border border-slate-800/80">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activePage === item.id;
            return (
              <Link
                key={item.id}
                to={item.to}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all ${
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-sm shadow-emerald-500/10'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-3">
        {rightActions}
        <div className="hidden sm:block h-4 w-px bg-slate-800 mx-1" />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
};
