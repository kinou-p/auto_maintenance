/**
 * LogViewer - Visualiseur de logs avec auto-scroll.
 */

import { useRef, useEffect } from 'react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  AlertTriangle,
  Bug,
} from 'lucide-react';

const LEVEL_CONFIG: Record<string, { icon: React.ElementType; color: string }> = {
  info: { icon: Info, color: 'text-blue-400' },
  success: { icon: CheckCircle2, color: 'text-green-400' },
  warning: { icon: AlertTriangle, color: 'text-yellow-400' },
  error: { icon: AlertCircle, color: 'text-red-400' },
  debug: { icon: Bug, color: 'text-gray-400' },
};

export function LogViewer() {
  const { logs, clearLogs, wsConnected } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);

  // Auto-scroll quand de nouveaux logs arrivent
  useEffect(() => {
    if (autoScroll.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    // Désactiver l'auto-scroll si l'utilisateur remonte
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

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
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
            {logs.length} entrée{logs.length > 1 ? 's' : ''}
          </span>
        </div>
        <button
          onClick={clearLogs}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Effacer
        </button>
      </div>

      {/* Logs */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-2 font-mono text-xs space-y-0.5"
      >
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            En attente de logs...
          </div>
        ) : (
          logs.map((log, idx) => {
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
