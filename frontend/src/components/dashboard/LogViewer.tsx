import { useRef, useEffect, useState } from 'react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  AlertTriangle,
  Bug,
  Search,
  X,
  Filter,
  Trash2,
  Terminal,
} from 'lucide-react';

const LEVEL_CONFIG: Record<string, { icon: React.ElementType; color: string; label: string; badgeBg: string }> = {
  info: { icon: Info, color: 'text-sky-400', label: 'Info', badgeBg: 'bg-sky-500/10 border-sky-500/20 text-sky-400' },
  success: { icon: CheckCircle2, color: 'text-emerald-400', label: 'Succès', badgeBg: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' },
  warning: { icon: AlertTriangle, color: 'text-amber-400', label: 'Warning', badgeBg: 'bg-amber-500/10 border-amber-500/20 text-amber-400' },
  error: { icon: AlertCircle, color: 'text-rose-400', label: 'Erreur', badgeBg: 'bg-rose-500/10 border-rose-500/20 text-rose-400' },
  debug: { icon: Bug, color: 'text-slate-400', label: 'Debug', badgeBg: 'bg-slate-500/10 border-slate-500/20 text-slate-400' },
};

const LEVELS = ['all', 'info', 'success', 'warning', 'error', 'debug'] as const;

export function LogViewer() {
  const { logs, clearLogs, wsConnected } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLevel, setSelectedLevel] = useState<string>('all');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    if (autoScroll.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    autoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  const formatTime = (timestamp: string) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return '';
    }
  };

  const filteredLogs = logs.filter((log) => {
    const matchesLevel = selectedLevel === 'all' || log.level === selectedLevel;
    const matchesSearch = !searchTerm || 
      log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (log.step && log.step.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchesLevel && matchesSearch;
  });

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 font-mono rounded-lg overflow-hidden border border-slate-800 shadow-xl">
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-900/90 border-b border-slate-800/80 gap-2 flex-wrap select-none">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 mr-2">
            <span className="h-3 w-3 rounded-full bg-rose-500/80 inline-block" />
            <span className="h-3 w-3 rounded-full bg-amber-500/80 inline-block" />
            <span className="h-3 w-3 rounded-full bg-emerald-500/80 inline-block" />
          </div>
          <Terminal className="h-4 w-4 text-sky-400" />
          <span className="text-xs font-semibold text-slate-200 tracking-wide">Terminal Output</span>
          <span
            className={cn(
              'inline-block h-2 w-2 rounded-full ring-2 ring-slate-950',
              wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500',
            )}
            title={wsConnected ? 'WebSocket connecté' : 'WebSocket déconnecté'}
          />
          <span className="text-[11px] text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded-full border border-slate-700/50">
            {filteredLogs.length}/{logs.length}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="h-3.5 w-3.5 mr-1 text-sky-400" />
            Filtres
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clearLogs}
            className="h-7 px-2 text-xs text-slate-400 hover:text-rose-400 hover:bg-rose-500/10"
            title="Effacer la console"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Filters Bar */}
      {showFilters && (
        <div className="px-3 py-2 border-b border-slate-800 bg-slate-900/60 space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <Input
              placeholder="Filtrer les messages du terminal..."
              className="h-7 pl-8 text-xs bg-slate-950 border-slate-700 text-slate-200 focus-visible:ring-sky-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="flex gap-1 flex-wrap">
            {LEVELS.map((level) => (
              <button
                key={level}
                onClick={() => setSelectedLevel(level)}
                className={cn(
                  'px-2.5 py-0.5 text-[11px] font-sans font-medium rounded-md transition-all',
                  selectedLevel === level
                    ? 'bg-sky-500 text-white shadow-xs'
                    : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
                )}
              >
                {level === 'all' ? 'Tous' : LEVEL_CONFIG[level]?.label || level}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Log Output Stream */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 font-mono text-[12px] leading-relaxed space-y-1 custom-scrollbar"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-xs italic">
            {logs.length === 0 ? '$ En attente des flux d\'exécution...' : '$ Aucun log ne correspond aux critères de filtre'}
          </div>
        ) : (
          filteredLogs.map((log, idx) => {
            const config = LEVEL_CONFIG[log.level] ?? LEVEL_CONFIG['info']!;
            const Icon = config.icon;

            return (
              <div
                key={idx}
                className={cn(
                  'log-entry flex items-start gap-2.5 px-2 py-1 rounded-md transition-colors',
                  'hover:bg-slate-900/80 group/log',
                )}
              >
                <span className="text-slate-500 shrink-0 text-[11px] select-none pt-0.5">
                  {formatTime(log.timestamp)}
                </span>
                <span className={cn('inline-flex items-center gap-1 text-[10px] font-sans px-1.5 py-0.2 rounded border shrink-0', config.badgeBg)}>
                  <Icon className="h-3 w-3" />
                  {config.label}
                </span>
                {log.step && (
                  <span className="text-sky-400 font-semibold shrink-0">[{log.step}]</span>
                )}
                <span className={cn('break-all tracking-tight', config.color)}>
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

