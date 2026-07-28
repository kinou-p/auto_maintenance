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
} from 'lucide-react';

const LEVEL_CONFIG: Record<string, { icon: React.ElementType; color: string; label: string }> = {
  info: { icon: Info, color: 'text-blue-400', label: 'Info' },
  success: { icon: CheckCircle2, color: 'text-green-400', label: 'Succès' },
  warning: { icon: AlertTriangle, color: 'text-yellow-400', label: 'Warning' },
  error: { icon: AlertCircle, color: 'text-red-400', label: 'Erreur' },
  debug: { icon: Bug, color: 'text-gray-400', label: 'Debug' },
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
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">Logs</h3>
          <span
            className={cn(
              'inline-block h-2 w-2 rounded-full',
              wsConnected ? 'bg-green-400' : 'bg-red-400',
            )}
            title={wsConnected ? 'WebSocket connecté' : 'WebSocket déconnecté'}
          />
          <span className="text-xs text-muted-foreground">
            {filteredLogs.length}/{logs.length} entrée{logs.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="h-3.5 w-3.5 mr-1" />
            Filtres
          </Button>
          <button
            onClick={clearLogs}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Effacer
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="px-4 py-2 border-b border-border space-y-2 bg-muted/20">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
            <Input
              placeholder="Rechercher dans les logs..."
              className="h-7 pl-8 text-xs bg-background"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
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
                  'px-2 py-0.5 text-xs rounded transition-colors',
                  selectedLevel === level
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                )}
              >
                {level === 'all' ? 'Tous' : LEVEL_CONFIG[level]?.label || level}
              </button>
            ))}
          </div>
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-2 font-mono text-xs space-y-0.5"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            {logs.length === 0 ? 'En attente de logs...' : 'Aucun log ne correspond aux filtres'}
          </div>
        ) : (
          filteredLogs.map((log, idx) => {
            const config = LEVEL_CONFIG[log.level] ?? LEVEL_CONFIG['info']!;
            const Icon = config.icon;

            return (
              <div
                key={idx}
                className={cn(
                  'log-entry flex items-start gap-2 px-2 py-1 rounded',
                  'hover:bg-muted/50 transition-colors',
                )}
              >
                <Icon className={cn('h-3.5 w-3.5 mt-0.5 shrink-0', config.color)} />
                <span className="text-muted-foreground shrink-0">
                  {formatTime(log.timestamp)}
                </span>
                {log.step && (
                  <span className="text-primary/70 shrink-0">[{log.step}]</span>
                )}
                <span className={cn('break-all', config.color)}>
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
