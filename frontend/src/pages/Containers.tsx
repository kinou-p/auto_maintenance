import React, { useEffect, useState } from 'react';
import {
  Box,
  RefreshCcw,
  Play,
  Pause,
  Square,
  RotateCcw,
  Trash2,
  ExternalLink,
  HardDrive,
  Cpu,
  Database,
  Search,
  Loader2,
  AlertTriangle,
  Layers,
  Server,
  Activity,
} from 'lucide-react';
import {
  listContainers,
  startContainer,
  pauseContainer,
  stopContainer,
  restartContainer,
  deleteContainer,
} from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { DDEVContainer } from '@/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Card, CardContent } from '@/components/ui/Card';
import { useConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Toaster, useToast } from '@/components/ui/Toaster';
import { Header } from '@/components/ui/Header';
import { cn } from '@/lib/utils';

export const Containers: React.FC = () => {
  const [containers, setContainers] = useState<DDEVContainer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedContainers, setSelectedContainers] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);
  const { confirm, dialog } = useConfirmDialog();
  const { toast, dismiss, toasts } = useToast();

  useWebSocket();

  const fetchContainers = async () => {
    setLoading(true);
    try {
      const data = await listContainers();
      setContainers(data);
      setError(null);
    } catch (err: unknown) {
      console.error('Fetch containers error:', err);
      setError('Impossible de récupérer la liste des containers DDEV.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContainers();
    const handleRefresh = () => fetchContainers();
    window.addEventListener('app:queue_updated', handleRefresh);
    return () => window.removeEventListener('app:queue_updated', handleRefresh);
  }, []);

  const handleAction = async (name: string, action: 'start' | 'pause' | 'stop' | 'restart' | 'delete') => {
    const actionLabels: Record<string, string> = {
      start: 'Démarrer',
      pause: 'Mettre en pause',
      stop: 'Arrêter',
      restart: 'Redémarrer',
      delete: 'Supprimer',
    };

    const confirmed = await confirm({
      title: `${actionLabels[action]} le conteneur`,
      description: `${actionLabels[action]} le conteneur "${name}" ?`,
      confirmLabel: actionLabels[action],
      variant: action === 'delete' ? 'destructive' : 'default',
    });

    if (!confirmed) return;

    setActionLoading(`${name}-${action}`);
    try {
      if (action === 'start') await startContainer(name);
      else if (action === 'pause') await pauseContainer(name);
      else if (action === 'stop') await stopContainer(name);
      else if (action === 'restart') await restartContainer(name);
      else if (action === 'delete') await deleteContainer(name);

      await fetchContainers();
      const actionLabel = actionLabels[action] || action;
      toast({ title: `${actionLabel} réussi`, description: `Le conteneur "${name}" a été traité.`, variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const toggleSelectAll = () => {
    if (selectedContainers.size === filteredContainers.length) {
      setSelectedContainers(new Set());
    } else {
      setSelectedContainers(new Set(filteredContainers.map((c) => c.name)));
    }
  };

  const toggleSelect = (name: string) => {
    const next = new Set(selectedContainers);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    setSelectedContainers(next);
  };

  const handleBulkDelete = async () => {
    if (selectedContainers.size === 0) return;

    const confirmed = await confirm({
      title: 'Suppression groupée',
      description: `Supprimer définitivement ces ${selectedContainers.size} conteneur(s) sélectionné(s) ?`,
      confirmLabel: 'Supprimer',
      variant: 'destructive',
    });

    if (!confirmed) return;

    setBatchLoading(true);
    try {
      for (const name of Array.from(selectedContainers)) {
        await deleteContainer(name);
      }
      setSelectedContainers(new Set());
      await fetchContainers();
      toast({ title: `${selectedContainers.size} conteneur(s) supprimé(s)`, variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setBatchLoading(false);
    }
  };

  const filteredContainers = containers.filter(
    (c) =>
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.url?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Metrics
  const runningCount = containers.filter((c) => c.status === 'running').length;
  const pausedCount = containers.filter((c) => c.status === 'paused').length;
  const stoppedCount = containers.filter((c) => c.status === 'stopped' || c.status === 'exited').length;
  const totalStorage = containers.reduce((acc, c) => acc + (c.storage_bytes || 0), 0);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {dialog}
      <Toaster toasts={toasts} dismiss={dismiss} />
      <Header activePage="containers" />

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
        {/* Title & Toolbar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-100 tracking-tight flex items-center gap-3">
              <Layers className="w-8 h-8 text-emerald-400" />
              Gestionnaire de Conteneurs DDEV
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Supervision temps réel et contrôle du cycle de vie des environnements isolés.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative w-64 md:w-80">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Rechercher un conteneur..."
                className="pl-10 bg-slate-900/80 border-slate-800 focus:border-emerald-500 text-sm rounded-xl text-slate-100 placeholder:text-slate-500"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            {selectedContainers.size > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleBulkDelete}
                disabled={batchLoading}
                className="gap-2 text-xs px-3.5 py-2.5 rounded-xl shadow-lg shadow-rose-600/20"
              >
                {batchLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Supprimer ({selectedContainers.size})
              </Button>
            )}

            <Button
              variant="outline"
              onClick={fetchContainers}
              disabled={loading}
              className="bg-slate-900/80 border-slate-800 hover:border-slate-700 text-slate-300 rounded-xl px-3.5 py-2.5"
            >
              <RefreshCcw className={cn('h-4 w-4 text-emerald-400', loading && 'animate-spin')} />
            </Button>
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Total Conteneurs</span>
                <span className="text-2xl font-black text-slate-100 mt-1 block font-mono">{containers.length}</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-slate-800/80 border border-slate-700/50 flex items-center justify-center text-slate-300">
                <Server className="w-6 h-6 text-emerald-400" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">En Cours (Running)</span>
                <span className="text-2xl font-black text-emerald-400 mt-1 block font-mono">{runningCount}</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <Activity className="w-6 h-6" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">En Pause / Arrêtés</span>
                <span className="text-2xl font-black text-amber-400 mt-1 block font-mono">{pausedCount + stoppedCount}</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Pause className="w-6 h-6" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Stockage Occupé</span>
                <span className="text-2xl font-black text-cyan-400 mt-1 block font-mono">{formatSize(totalStorage)}</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <HardDrive className="w-6 h-6" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Errors */}
        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-300 p-4 rounded-xl flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
        )}

        {/* Containers List */}
        {loading && containers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <Loader2 className="h-10 w-10 text-emerald-400 animate-spin" />
            <p className="text-sm text-slate-400 animate-pulse">Scan des conteneurs DDEV en cours...</p>
          </div>
        ) : filteredContainers.length === 0 ? (
          <Card className="bg-slate-900/40 border-slate-800/80 p-12 text-center">
            <Box className="h-12 w-12 text-slate-600 mx-auto mb-4" />
            <p className="text-lg font-bold text-slate-200">Aucun conteneur DDEV trouvé</p>
            <p className="text-sm text-slate-400 mt-1">
              {searchTerm ? 'Aucun résultat pour cette recherche.' : 'Aucun environnement DDEV n’a encore été créé.'}
            </p>
          </Card>
        ) : (
          <div className="space-y-4">
            {/* Table Selection Header */}
            <div className="flex items-center justify-between px-4 py-2 text-xs font-semibold text-slate-400 bg-slate-900/40 rounded-xl border border-slate-800/60">
              <label className="flex items-center gap-3 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={filteredContainers.length > 0 && selectedContainers.size === filteredContainers.length}
                  onChange={toggleSelectAll}
                  className="rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-500 h-4 w-4"
                />
                <span>Sélectionner tout ({filteredContainers.length})</span>
              </label>

              <span className="font-mono">{selectedContainers.size} sélectionné(s)</span>
            </div>

            {/* Containers Cards Grid */}
            <div className="grid grid-cols-1 gap-4">
              {filteredContainers.map((container) => {
                const isSelected = selectedContainers.has(container.name);
                const isRunning = container.status === 'running';
                const isPaused = container.status === 'paused';

                return (
                  <Card
                    key={container.name}
                    className={`transition-all duration-200 bg-slate-900/60 backdrop-blur-xl border-slate-800 hover:border-slate-700 ${
                      isSelected ? 'border-emerald-500/50 bg-emerald-500/5 shadow-lg shadow-emerald-500/5' : ''
                    }`}
                  >
                    <CardContent className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                      {/* Left: Info */}
                      <div className="flex items-center gap-4 min-w-0">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(container.name)}
                          className="rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-500 h-4 w-4 shrink-0"
                        />

                        <div className="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/50 flex items-center justify-center text-slate-300 shrink-0">
                          <Box className="w-5 h-5 text-emerald-400" />
                        </div>

                        <div className="min-w-0">
                          <div className="flex items-center gap-3 flex-wrap">
                            <h3 className="font-bold text-base text-slate-100 truncate">{container.name}</h3>
                            <Badge
                              className={`px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${
                                isRunning
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                                  : isPaused
                                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                                  : 'bg-slate-800 text-slate-400 border-slate-700'
                              }`}
                            >
                              {container.status}
                            </Badge>
                          </div>

                          <div className="flex items-center gap-4 text-xs text-slate-400 mt-1 flex-wrap">
                            {container.url && (
                              <a
                                href={container.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-cyan-400 hover:underline font-mono truncate"
                              >
                                {container.url}
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                            <span className="flex items-center gap-1 font-mono">
                              <Cpu className="w-3.5 h-3.5 text-slate-500" />
                              PHP {container.php_version}
                            </span>
                            <span className="flex items-center gap-1 font-mono">
                              <Database className="w-3.5 h-3.5 text-slate-500" />
                              {container.db_type}:{container.db_version}
                            </span>
                            <span className="flex items-center gap-1 font-mono">
                              <HardDrive className="w-3.5 h-3.5 text-slate-500" />
                              {formatSize(container.storage_bytes || 0)}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Actions */}
                      <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                        {isRunning ? (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={!!actionLoading}
                              onClick={() => handleAction(container.name, 'pause')}
                              className="text-xs bg-slate-900 border-slate-800 hover:bg-amber-500/10 hover:text-amber-300 hover:border-amber-500/30"
                            >
                              {actionLoading === `${container.name}-pause` ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Pause className="w-3.5 h-3.5 text-amber-400 mr-1.5" />
                              )}
                              Pause
                            </Button>

                            <Button
                              variant="outline"
                              size="sm"
                              disabled={!!actionLoading}
                              onClick={() => handleAction(container.name, 'stop')}
                              className="text-xs bg-slate-900 border-slate-800 hover:bg-rose-500/10 hover:text-rose-300 hover:border-rose-500/30"
                            >
                              {actionLoading === `${container.name}-stop` ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Square className="w-3.5 h-3.5 text-rose-400 mr-1.5" />
                              )}
                              Arrêter
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!!actionLoading}
                            onClick={() => handleAction(container.name, 'start')}
                            className="text-xs bg-slate-900 border-slate-800 hover:bg-emerald-500/10 hover:text-emerald-300 hover:border-emerald-500/30"
                          >
                            {actionLoading === `${container.name}-start` ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Play className="w-3.5 h-3.5 text-emerald-400 mr-1.5" />
                            )}
                            Démarrer
                          </Button>
                        )}

                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!!actionLoading}
                          onClick={() => handleAction(container.name, 'restart')}
                          className="text-xs bg-slate-900 border-slate-800 hover:border-slate-700 text-slate-300"
                        >
                          {actionLoading === `${container.name}-restart` ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <RotateCcw className="w-3.5 h-3.5 text-cyan-400 mr-1.5" />
                          )}
                          Redémarrer
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!!actionLoading}
                          onClick={() => handleAction(container.name, 'delete')}
                          className="text-xs bg-slate-900 border-slate-800 hover:bg-rose-500/10 hover:text-rose-400 hover:border-rose-500/30 p-2"
                        >
                          {actionLoading === `${container.name}-delete` ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5 text-rose-400" />
                          )}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
