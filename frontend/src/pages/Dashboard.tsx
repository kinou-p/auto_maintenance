import { useState, useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/stores/appStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import {
  startWorkflow,
  cancelWorkflow,
  getVRTReport,
  checkHealth,
  getActiveWorkflow,
  resetDDEVGlobal,
  startProject,
  pauseProject,
  stopProject,
  restartProject,
  recreateProject,
  resetProject,
  getProjectStatus,
  getProjects,
  getWorkflowQueue,
  setGlobalErrorHandler,
} from '@/lib/api';
import { ProjectForm } from '@/components/project/ProjectForm';
import { ProjectList } from '@/components/project/ProjectList';
import { LogViewer } from '@/components/dashboard/LogViewer';
import { WorkflowProgress } from '@/components/dashboard/WorkflowProgress';
import { QueueModal } from '@/components/dashboard/QueueModal';
import { ImageComparer } from '@/components/vrt/ImageComparer';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Toaster, useToast } from '@/components/ui/Toaster';
import { cn } from '@/lib/utils';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Play,
  Pause,
  Square,
  Wrench,
  RotateCcw,
  LayoutGrid,
  Heart,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Globe,
  FileText,
  ImageIcon,
  StopCircle,
  Hammer,
  Clock,
  RefreshCw,
  Menu,
  MoreVertical,
  ImageOff,
} from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';

import type { VRTReport } from '@/types';

export function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    projects,
    currentProject,
    setCurrentProject,
    currentWorkflow,
    setCurrentWorkflow,
    clearLogs,
    setProjects,
    sidebarOpen,
    toggleSidebar,
    ddevLoading,
    setDdevLoading,
    workflowLoading,
    setWorkflowLoading,
  } = useAppStore();

  const { confirm, dialog } = useConfirmDialog();
  const { toast, dismiss, toasts } = useToast();

  useEffect(() => {
    setGlobalErrorHandler((message) => {
      toast({ title: 'Erreur', description: message, variant: 'destructive' });
    });
    return () => setGlobalErrorHandler(() => {});
  }, [toast]);

  useEffect(() => {
    const projectIdParam = searchParams.get('project');
    if (projectIdParam && projects.length > 0) {
      const parsedId = parseInt(projectIdParam, 10);
      if (!currentProject || currentProject.id !== parsedId) {
        const found = projects.find(p => p.id === parsedId);
        if (found) {
          setCurrentProject(found);
        }
      }
    }
  }, [projects.length]);

  useEffect(() => {
    if (currentProject) {
      if (searchParams.get('project') !== String(currentProject.id)) {
        setSearchParams({ project: String(currentProject.id) }, { replace: true });
      }
    }
  }, [currentProject?.id]);

  const [vrtReport, setVrtReport] = useState<VRTReport | null>(null);
  const [vrtLoading, setVrtLoading] = useState(false);
  const [health, setHealth] = useState<{ ddev: boolean; docker: boolean } | null>(null);
  const [ddevStatus, setDdevStatus] = useState<string>('unknown');
  const [logPanelHeight, setLogPanelHeight] = useState(256);
  const [showLogs, setShowLogs] = useState(false);
  const [globalViewMode, setGlobalViewMode] = useState<'slider' | 'side-by-side' | 'diff'>(() => {
    const stored = localStorage.getItem('vrt_view_mode');
    return (stored as 'slider' | 'side-by-side' | 'diff') || 'slider';
  });
  const [collapsedItems, setCollapsedItems] = useState<Set<number>>(new Set());
  const isResizing = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem('vrt_view_mode', globalViewMode);
  }, [globalViewMode]);

  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
  }, [currentProject?.id]);

  const logPanelHeightRef = useRef(logPanelHeight);
  logPanelHeightRef.current = logPanelHeight;

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    const startY = e.clientY;
    const startHeight = logPanelHeightRef.current;

    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      const delta = e.clientY - startY;
      const newHeight = Math.min(Math.max(startHeight + delta, 100), window.innerHeight - 200);
      setLogPanelHeight(newHeight);
    };

    const handleMouseUp = () => {
      isResizing.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, []);

  useWebSocket(currentProject?.id);

  useEffect(() => {
    checkHealth()
      .then((h) =>
        setHealth({
          ddev: h.checks.ddev_installed,
          docker: h.checks.docker_running,
        }),
      )
      .catch(() => setHealth(null));
  }, []);

  const fetchVrtReport = useCallback(async () => {
    if (!currentProject) return;
    setVrtLoading(true);
    try {
      const report = await getVRTReport(currentProject.id);
      setVrtReport(report);
    } catch {
      setVrtReport(null);
    } finally {
      setVrtLoading(false);
    }
  }, [currentProject?.id]);

  useEffect(() => {
    fetchVrtReport();
  }, [fetchVrtReport]);

  useEffect(() => {
    const handleVrtRefresh = () => {
      fetchVrtReport();
    };
    window.addEventListener('app:vrt_refresh', handleVrtRefresh);
    return () => window.removeEventListener('app:vrt_refresh', handleVrtRefresh);
  }, [fetchVrtReport]);

  useEffect(() => {
    if (!currentProject) {
      setCurrentWorkflow(null);
      setDdevStatus('unknown');
      return;
    }

    const fetchStatus = async () => {
      try {
        const status = await getProjectStatus(currentProject.id);
        const ddevData = status.ddev.data as Record<string, unknown>;
        const rawStatus = (ddevData?.raw as Record<string, unknown>)?.status as string || (status.ddev.running ? 'running' : 'stopped');
        setDdevStatus(rawStatus);
      } catch {
        setDdevStatus('error');
      }
    };

    fetchStatus();

    const handleStatusUpdate = () => fetchStatus();
    window.addEventListener('app:queue_updated', handleStatusUpdate);

    getActiveWorkflow(currentProject.id)
      .then((workflow) => {
        if (workflow) {
          setCurrentWorkflow(workflow);
        } else {
          setCurrentWorkflow(null);
        }
      })
      .catch(() => {
        setCurrentWorkflow(null);
      });

    return () => window.removeEventListener('app:queue_updated', handleStatusUpdate);
  }, [currentProject?.id, setCurrentWorkflow]);

  const [queueInfo, setQueueInfo] = useState<{ total_active: number; total_pending: number } | null>(null);
  const [showQueueModal, setShowQueueModal] = useState(false);

  const fetchQueueInfo = useCallback(async () => {
    try {
      const q = await getWorkflowQueue();
      setQueueInfo({ total_active: q.total_active, total_pending: q.total_pending });
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchQueueInfo();
    const handleQueueUpdate = () => fetchQueueInfo();
    window.addEventListener('app:queue_updated', handleQueueUpdate);
    return () => window.removeEventListener('app:queue_updated', handleQueueUpdate);
  }, [fetchQueueInfo]);

  const handleStartWorkflow = async () => {
    if (!currentProject) {
      toast({ title: 'Aucun projet sélectionné', variant: 'warning' });
      return;
    }
    setWorkflowLoading(true);
    clearLogs();

    try {
      const workflow = await startWorkflow(currentProject.id);
      setCurrentWorkflow(workflow);
      fetchQueueInfo();

      if (workflow.status === 'pending' && (queueInfo?.total_active ?? 0) > 0) {
        toast({
          title: 'Maintenance en file d\'attente',
          description: `Maintenance ajoutée à la file pour "${currentProject.name}".`,
          variant: 'info',
        });
      } else {
        toast({
          title: 'Maintenance lancée',
          description: `Maintenance démarrée pour "${currentProject.name}".`,
          variant: 'success',
        });
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Impossible de lancer la maintenance.';
      toast({ title: 'Erreur', description: errMsg, variant: 'warning' });
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleStartImportOnlyWorkflow = async () => {
    if (!currentProject) return;

    const confirmed = await confirm({
      title: 'Importer sans maintenance',
      description: `Lancer l'importation (sans maintenance) pour "${currentProject.name}" ?`,
      confirmLabel: 'Importer',
    });
    if (!confirmed) return;

    setWorkflowLoading(true);
    clearLogs();

    try {
      const workflow = await startWorkflow(currentProject.id, undefined, undefined, true);
      setCurrentWorkflow(workflow);
      fetchQueueInfo();

      if (workflow.status === 'pending' && (queueInfo?.total_active ?? 0) > 0) {
        toast({
          title: 'Importation en file d\'attente',
          description: `Importation ajoutée à la file pour "${currentProject.name}".`,
          variant: 'info',
        });
      } else {
        toast({
          title: 'Importation lancée',
          description: `Importation démarrée pour "${currentProject.name}".`,
          variant: 'success',
        });
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Impossible de lancer l\'importation.';
      toast({ title: 'Erreur', description: errMsg, variant: 'warning' });
    } finally {
      setWorkflowLoading(false);
    }
  };

  const refreshProjectState = async () => {
    if (!currentProject) return;
    try {
      const statusRes = await getProjectStatus(currentProject.id);
      const ddevData = statusRes.ddev.data as Record<string, unknown>;
      const rawStatus = (ddevData?.raw as Record<string, unknown>)?.status as string || (statusRes.ddev.status as string) || (statusRes.ddev.running ? 'running' : 'stopped');
      setDdevStatus(rawStatus);
      const allProjects = await getProjects();
      setProjects(allProjects.projects);
    } catch (err) {
      console.error('Error refreshing project status:', err);
    }
  };

  const handleDdevAction = async (
    action: () => Promise<unknown>,
    successMessage: string,
  ) => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await action();
      await refreshProjectState();
      toast({ title: successMessage, variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleStartProject = () => handleDdevAction(
    () => startProject(currentProject!.id),
    'DDEV démarré',
  );

  const handlePauseProject = () => handleDdevAction(
    () => pauseProject(currentProject!.id),
    'DDEV mis en pause',
  );

  const handleStopProject = () => handleDdevAction(
    () => stopProject(currentProject!.id),
    'DDEV arrêté',
  );

  const handleRestartProject = () => handleDdevAction(
    () => restartProject(currentProject!.id),
    'DDEV redémarré',
  );

  const handleRecreateProject = () => handleDdevAction(
    () => recreateProject(currentProject!.id),
    'Projet recréé',
  );

  const handleResetProject = async () => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await resetProject(currentProject.id);
      clearLogs();
      await refreshProjectState();
      toast({ title: 'Projet réinitialisé', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleCancelWorkflow = async () => {
    if (!currentWorkflow) return;
    const confirmed = await confirm({
      title: 'Annuler la maintenance',
      description: 'Interrompre et annuler la maintenance en cours pour le projet ?',
      confirmLabel: 'Annuler la maintenance',
      variant: 'destructive',
    });
    if (!confirmed) return;
    try {
      await cancelWorkflow(currentWorkflow.id);
      toast({ title: 'Maintenance annulée', variant: 'info' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    }
  };

  const handleGlobalReset = async () => {
    const confirmed = await confirm({
      title: 'Réinitialiser DDEV',
      description: 'Voulez-vous vraiment réinitialiser l\'environnement DDEV ? Cela arrêtera TOUS les projets en cours (power-off).',
      confirmLabel: 'Réinitialiser',
      variant: 'destructive',
    });
    if (!confirmed) return;

    setDdevLoading(true);
    try {
      await resetDDEVGlobal();
      toast({ title: 'DDEV réinitialisé avec succès', variant: 'success' });
      const h = await checkHealth();
      setHealth({ ddev: h.checks.ddev_installed, docker: h.checks.docker_running });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const anyLoading = ddevLoading || workflowLoading;

  return (
    <div className="min-h-screen flex flex-col">
      {dialog}
      <Toaster toasts={toasts} dismiss={dismiss} />

      <header className="border-b border-border px-4 md:px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden h-8 w-8"
              onClick={toggleSidebar}
            >
              <Menu className="h-4 w-4" />
            </Button>
            <Wrench className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold hidden sm:block">Auto Maintenance</h1>
            <Badge variant="outline" className="text-xs hidden sm:block">v1.0</Badge>
          </div>

          <div className="flex items-center gap-2 md:gap-4">
            <Button
              variant="outline"
              size="sm"
              asChild
              className="h-8 text-xs px-2"
            >
              <Link to="/containers">
                <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Containers</span>
              </Link>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleGlobalReset}
              disabled={anyLoading}
              title="Réinitialiser l'environnement DDEV (Global Power-off)"
              className="h-8 text-xs px-2"
            >
              <RotateCcw className={cn("mr-1.5 h-3.5 w-3.5", anyLoading && "animate-spin")} />
              <span className="hidden sm:inline">Reset DDEV</span>
            </Button>

            {currentProject && (
              <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-muted/30 rounded-full border border-border/50">
                <div className={cn(
                  "h-2 w-2 rounded-full animate-pulse",
                  ddevStatus === 'running' ? "bg-green-500" :
                    ddevStatus === 'starting' ? "bg-blue-400" :
                      ddevStatus === 'stopped' ? "bg-orange-500" : "bg-muted-foreground/30"
                )} />
                <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
                  DDEV: {ddevStatus}
                </span>
              </div>
            )}

            {health && (
              <div className="hidden md:flex items-center gap-3">
                <div className="flex items-center gap-1 text-xs">
                  {health.docker ? (
                    <Heart className="h-3.5 w-3.5 text-green-400" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                  )}
                  Docker
                </div>
                <div className="flex items-center gap-1 text-xs">
                  {health.ddev ? (
                    <Heart className="h-3.5 w-3.5 text-green-400" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                  )}
                  DDEV
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {sidebarOpen && (
          <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={toggleSidebar} />
        )}
        <aside className={cn(
          "w-80 border-r border-border flex flex-col shrink-0 custom-scrollbar",
          "fixed lg:relative inset-y-0 left-0 z-50 bg-background",
          "transition-transform duration-300",
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}>
          <div className="p-4 border-b border-border shrink-0">
            <ProjectForm onToast={(title, variant) => toast({ title, variant: variant || 'default' })} />
          </div>
          <div className="flex-1 overflow-hidden p-4">
            <ProjectList onToast={(title, variant) => toast({ title, variant: variant || 'default' })} />
          </div>
        </aside>

        <main className="flex-1 flex flex-col overflow-hidden">
          {currentProject ? (
            <>
              <div className="px-4 md:px-6 py-3 border-b border-border space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-lg font-semibold truncate">{currentProject.name}</h2>
                    <a
                      href={`http://${currentProject.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
                    >
                      <Globe className="h-3 w-3 shrink-0" />
                      <span className="truncate">{currentProject.domain}</span>
                    </a>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowLogs(!showLogs)}
                      title={showLogs ? "Masquer les logs" : "Voir les logs"}
                    >
                      <FileText className="h-4 w-4" />
                      <span className="hidden sm:inline ml-1.5">{showLogs ? 'Logs ↑' : 'Logs'}</span>
                    </Button>
                    {currentWorkflow?.status === 'running' ? (
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={handleCancelWorkflow}
                      >
                        <StopCircle className="mr-1.5 h-4 w-4" />
                        Annuler
                      </Button>
                    ) : (
                      <>
                        <div className="hidden md:flex items-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleStartProject}
                            disabled={anyLoading || ddevStatus === 'running'}
                            title="Démarrer DDEV"
                            className="text-green-600 border-green-200 hover:bg-green-50"
                          >
                            <Play className="h-4 w-4" />
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handlePauseProject}
                            disabled={anyLoading || ddevStatus === 'paused' || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                            title="Pause DDEV"
                            className="text-amber-600 border-amber-200 hover:bg-amber-50"
                          >
                            <Pause className="h-4 w-4" />
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleStopProject}
                            disabled={anyLoading || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                            title="Arrêter DDEV"
                            className="text-orange-600 border-orange-200 hover:bg-orange-50"
                          >
                            <Square className="h-4 w-4" />
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRestartProject}
                            disabled={anyLoading}
                            title="Redémarrer DDEV"
                            className="text-blue-600 border-blue-200 hover:bg-blue-50"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRecreateProject}
                            disabled={anyLoading}
                            title="Recréer le projet"
                            className="text-purple-600 border-purple-200 hover:bg-purple-50"
                          >
                            <Hammer className="h-4 w-4" />
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleResetProject}
                            disabled={anyLoading}
                            title="Réinitialiser le projet"
                            className="text-rose-600 border-rose-200 hover:bg-rose-50"
                          >
                            <RefreshCw className="h-4 w-4" />
                            <span className="hidden xl:inline ml-1 text-xs">Reset</span>
                          </Button>
                        </div>

                        <DropdownMenu.Root>
                          <DropdownMenu.Trigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              className="md:hidden"
                              disabled={anyLoading}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenu.Trigger>
                          <DropdownMenu.Portal>
                            <DropdownMenu.Content
                              align="end"
                              className="min-w-[180px] bg-popover rounded-md p-1 shadow-md border border-border z-50"
                            >
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                                disabled={anyLoading || ddevStatus === 'running'}
                                onSelect={handleStartProject}
                              >
                                <Play className="h-4 w-4 text-green-600" />
                                Démarrer
                              </DropdownMenu.Item>
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                                disabled={anyLoading || ddevStatus !== 'running'}
                                onSelect={handlePauseProject}
                              >
                                <Pause className="h-4 w-4 text-amber-600" />
                                Pause
                              </DropdownMenu.Item>
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                                disabled={anyLoading || (ddevStatus !== 'running' && ddevStatus !== 'paused')}
                                onSelect={handleStopProject}
                              >
                                <Square className="h-4 w-4 text-orange-600" />
                                Arrêter
                              </DropdownMenu.Item>
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                                disabled={anyLoading}
                                onSelect={handleRestartProject}
                              >
                                <RotateCcw className="h-4 w-4 text-blue-600" />
                                Redémarrer
                              </DropdownMenu.Item>
                              <DropdownMenu.Separator className="h-px bg-border my-1" />
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                                disabled={anyLoading}
                                onSelect={handleRecreateProject}
                              >
                                <Hammer className="h-4 w-4 text-purple-600" />
                                Recréer
                              </DropdownMenu.Item>
                              <DropdownMenu.Item
                                className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent text-destructive disabled:opacity-50"
                                disabled={anyLoading}
                                onSelect={handleResetProject}
                              >
                                <RefreshCw className="h-4 w-4" />
                                Réinitialiser
                              </DropdownMenu.Item>
                            </DropdownMenu.Content>
                          </DropdownMenu.Portal>
                        </DropdownMenu.Root>
                      </>
                    )}
                  </div>
                </div>

                {currentWorkflow?.status !== 'running' && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowQueueModal(true)}
                      className="text-amber-600 border-amber-500/30 hover:bg-amber-500/10 dark:text-amber-400"
                    >
                      <Clock className="mr-1.5 h-4 w-4" />
                      File d'attente
                      {queueInfo && (queueInfo.total_active > 0 || queueInfo.total_pending > 0) && (
                        <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-[10px] bg-amber-500/20 text-amber-600 dark:text-amber-300">
                          {queueInfo.total_active + queueInfo.total_pending}
                        </Badge>
                      )}
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleStartImportOnlyWorkflow}
                      disabled={workflowLoading}
                      title="Lancer le projet et importer le site .wpress sans faire de maintenance"
                      className="border-primary/30 text-primary hover:bg-primary/10"
                    >
                      <Wrench className="mr-1.5 h-4 w-4" />
                      <span className="hidden sm:inline">Lancer & Importer</span>
                    </Button>

                    <Button
                      size="sm"
                      onClick={handleStartWorkflow}
                      disabled={workflowLoading}
                    >
                      <Play className="mr-1.5 h-4 w-4" />
                      Lancer la maintenance
                    </Button>
                  </div>
                )}
              </div>

              {ddevLoading && (
                <div className="mx-6 mt-4 p-3 rounded-xl flex items-center gap-3 border border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400">
                  <RefreshCw className="h-4 w-4 animate-spin shrink-0" />
                  <span className="text-sm font-medium">Opération en cours...</span>
                </div>
              )}

              <div className="p-4 md:p-6 pb-0 shrink-0">
                <Card>
                  <CardContent className="pt-6">
                    <WorkflowProgress />
                  </CardContent>
                </Card>
              </div>

              {showLogs && (
                <div
                  className="border-b border-border shrink-0 flex flex-col mt-6"
                  style={{ height: logPanelHeight }}
                >
                  <div className="flex-1 overflow-hidden">
                    <LogViewer />
                  </div>
                  <div
                    onMouseDown={handleMouseDown}
                    className="h-1.5 cursor-row-resize bg-transparent hover:bg-primary/20 active:bg-primary/40 transition-colors flex items-center justify-center group shrink-0"
                  >
                    <div className="w-10 h-0.5 rounded-full bg-muted-foreground/30 group-hover:bg-primary/50 transition-colors" />
                  </div>
                </div>
              )}

              <div
                ref={scrollContainerRef}
                className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6"
              >
                {vrtLoading && (
                  <Card>
                    <CardContent className="pt-6 flex items-center justify-center py-12">
                      <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                      <span className="ml-3 text-muted-foreground">Chargement du rapport VRT...</span>
                    </CardContent>
                  </Card>
                )}

                {!vrtLoading && vrtReport && vrtReport.items.length > 0 && (
                  <>
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-lg">
                          <ImageIcon className="h-5 w-5" />
                          Résumé
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          <div className="space-y-1">
                            <div className="text-2xl font-bold">{vrtReport.updates_total || 0}</div>
                            <div className="text-xs text-muted-foreground">Mises à jour</div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-2xl font-bold text-green-500 flex items-center gap-1">
                              <CheckCircle2 className="h-5 w-5" />
                              {vrtReport.updates_success || 0}
                            </div>
                            <div className="text-xs text-muted-foreground">MàJ Réussies</div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-2xl font-bold">{vrtReport.total_pages}</div>
                            <div className="text-xs text-muted-foreground">Pages testées</div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-2xl font-bold">
                              {vrtReport.total_pages > 0
                                ? ((vrtReport.total_passed / vrtReport.total_pages) * 100).toFixed(0)
                                : 0}%
                            </div>
                            <div className="text-xs text-muted-foreground">Succès VRT</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <CardTitle className="flex items-center gap-2 text-lg">
                            <ImageIcon className="h-5 w-5" />
                            Comparaison Visuelle
                            <Badge
                              variant={vrtReport.total_failed === 0 ? 'success' : 'destructive'}
                            >
                              {vrtReport.total_passed}/{vrtReport.total_pages} pass
                            </Badge>
                          </CardTitle>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs text-muted-foreground mr-2">Mode de vue :</span>
                            <div className="flex gap-1">
                              {(['slider', 'side-by-side', 'diff'] as const).map((mode) => (
                                <Button
                                  key={mode}
                                  variant={globalViewMode === mode ? 'default' : 'outline'}
                                  size="sm"
                                  onClick={() => setGlobalViewMode(mode)}
                                >
                                  {mode === 'slider' ? 'Slider' : mode === 'side-by-side' ? 'Côte à côte' : 'Diff'}
                                </Button>
                              ))}
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                if (collapsedItems.size === vrtReport.items.length) {
                                  setCollapsedItems(new Set());
                                } else {
                                  setCollapsedItems(new Set(vrtReport.items.map((_, idx) => idx)));
                                }
                              }}
                            >
                              {collapsedItems.size === vrtReport.items.length ? (
                                <>
                                  <ChevronDown className="mr-2 h-4 w-4" />
                                  Tout déplier
                                </>
                              ) : (
                                <>
                                  <ChevronUp className="mr-2 h-4 w-4" />
                                  Tout replier
                                </>
                              )}
                            </Button>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        {vrtReport.items.map((item, idx) => (
                          <ImageComparer
                            key={idx}
                            beforeSrc={item.before_screenshot || ''}
                            afterSrc={item.after_screenshot || ''}
                            diffSrc={item.diff_image || undefined}
                            diffPercentage={item.diff_percentage || undefined}
                            ssimScore={item.ssim_score || undefined}
                            passed={item.passed || undefined}
                            pageName={item.page_name}
                            pageUrl={item.page_url}
                            device={item.device}
                            defaultViewMode={globalViewMode}
                            isCollapsed={collapsedItems.has(idx)}
                            onToggleCollapse={() => {
                              const newSet = new Set(collapsedItems);
                              if (newSet.has(idx)) {
                                newSet.delete(idx);
                              } else {
                                newSet.add(idx);
                              }
                              setCollapsedItems(newSet);
                            }}
                          />
                        ))}
                      </CardContent>
                    </Card>
                  </>
                )}

                {!vrtLoading && (!vrtReport || vrtReport.items.length === 0) && currentProject && (
                  <Card>
                    <CardContent className="pt-6 flex flex-col items-center justify-center py-12 text-center">
                      <ImageOff className="h-12 w-12 text-muted-foreground/30 mb-4" />
                      <h3 className="text-lg font-semibold text-muted-foreground">
                        Aucun rapport VRT
                      </h3>
                      <p className="text-sm text-muted-foreground mt-2 max-w-md">
                        Lancez une maintenance pour générer des captures d'écran avant/après et comparer visuellement les changements.
                      </p>
                    </CardContent>
                  </Card>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-3">
                <Wrench className="h-16 w-16 mx-auto text-muted-foreground/30" />
                <h2 className="text-xl font-semibold text-muted-foreground">
                  Sélectionnez un projet
                </h2>
                <p className="text-sm text-muted-foreground">
                  Créez ou sélectionnez un projet dans la barre latérale pour commencer.
                </p>
              </div>
            </div>
          )}
        </main>
      </div>
      <QueueModal isOpen={showQueueModal} onClose={() => setShowQueueModal(false)} />
    </div>
  );
}
