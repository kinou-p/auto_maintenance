import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAppStore } from '@/stores/appStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import {
  startWorkflow,
  cancelWorkflow,
  getVRTReport,
  getActiveWorkflow,
  getProjectWorkflows,
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
import { NotificationModal } from '@/components/dashboard/NotificationModal';
import { ProjectToolbar } from '@/components/dashboard/ProjectToolbar';
import { VRTReportViewer } from '@/components/dashboard/VRTReportViewer';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Toaster, useToast } from '@/components/ui/Toaster';
import { Header } from '@/components/ui/Header';
import { cn } from '@/lib/utils';
import {
  Wrench,
  RotateCcw,
  Clock,
  RefreshCw,
  Bell,
} from 'lucide-react';
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
    notifications,
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
  }, [searchParams, projects, currentProject, setCurrentProject]);

  useEffect(() => {
    if (currentProject) {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev);
        next.set('project', currentProject.id.toString());
        return next;
      }, { replace: true });
    }
  }, [currentProject, setSearchParams]);

  const [vrtReport, setVrtReport] = useState<VRTReport | null>(null);
  const [vrtLoading, setVrtLoading] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [logPanelHeight, setLogPanelHeight] = useState(250);
  const [showQueueModal, setShowQueueModal] = useState(false);
  const [showNotificationModal, setShowNotificationModal] = useState(false);
  const [queueInfo, setQueueInfo] = useState<{ total_active: number; total_pending: number } | null>(null);
  const [ddevStatus, setDdevStatus] = useState<string>('unknown');
  const [globalViewMode, setGlobalViewMode] = useState<'slider' | 'side-by-side' | 'diff'>('slider');
  const [collapsedItems, setCollapsedItems] = useState<Set<number>>(new Set());

  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(250);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const fetchQueueInfo = useCallback(async () => {
    try {
      const data = await getWorkflowQueue();
      setQueueInfo({
        total_active: data.total_active ?? 0,
        total_pending: data.total_pending ?? 0,
      });
    } catch {
      // Ignorer silencieusement
    }
  }, []);

  useEffect(() => {
    fetchQueueInfo();
    const interval = setInterval(fetchQueueInfo, 10000);
    const handleQueueUpdated = () => fetchQueueInfo();
    window.addEventListener('app:queue_updated', handleQueueUpdated);

    return () => {
      clearInterval(interval);
      window.removeEventListener('app:queue_updated', handleQueueUpdated);
    };
  }, [fetchQueueInfo]);

  useWebSocket(currentProject?.id);

  const fetchDdevStatus = useCallback(async () => {
    if (!currentProject) return;
    try {
      const statusData = await getProjectStatus(currentProject.id);
      const ddevInfo = statusData.ddev as { status?: string } | undefined;
      setDdevStatus(ddevInfo?.status || statusData.project?.status || 'unknown');
    } catch {
      setDdevStatus('unknown');
    }
  }, [currentProject]);

  useEffect(() => {
    fetchDdevStatus();
    const interval = setInterval(fetchDdevStatus, 8000);
    return () => clearInterval(interval);
  }, [fetchDdevStatus]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    isDraggingRef.current = true;
    startYRef.current = e.clientY;
    startHeightRef.current = logPanelHeight;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = moveEvent.clientY - startYRef.current;
      setLogPanelHeight(Math.max(120, Math.min(600, startHeightRef.current + delta)));
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, [logPanelHeight]);

  const fetchVRT = useCallback(async () => {
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
  }, [currentProject]);

  useEffect(() => {
    if (!currentProject) {
      setVrtReport(null);
      setCurrentWorkflow(null);
      return;
    }

    fetchVRT();

    getActiveWorkflow(currentProject.id)
      .then(wf => setCurrentWorkflow(wf))
      .catch(async () => {
        try {
          const wfs = await getProjectWorkflows(currentProject.id);
          if (wfs.length > 0 && wfs[0]) {
            setCurrentWorkflow(wfs[0]);
          } else {
            setCurrentWorkflow(null);
          }
        } catch {
          setCurrentWorkflow(null);
        }
      });
  }, [currentProject, fetchVRT, setCurrentWorkflow]);

  useEffect(() => {
    if (currentWorkflow?.status === 'completed') {
      fetchVRT();
    }
  }, [currentWorkflow?.status, fetchVRT]);

  const handleStartWorkflow = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    clearLogs();
    try {
      const wf = await startWorkflow(currentProject.id);
      setCurrentWorkflow(wf);
      setShowLogs(true);
      toast({ title: 'Maintenance démarrée', description: 'Le workflow a été lancé.', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleStartImportOnlyWorkflow = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    clearLogs();
    try {
      const wf = await startWorkflow(
        currentProject.id,
        ['ddev_create', 'dns_setup', 'wp_install', 'plugin_install', 'wpress_import'],
        undefined,
        true,
      );
      setCurrentWorkflow(wf);
      setShowLogs(true);
      toast({ title: 'Lancement du site démarré', description: 'Création DDEV et importation .wpress...', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleStartProject = async () => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await startProject(currentProject.id);
      await fetchDdevStatus();
      toast({ title: 'Projet démarré', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handlePauseProject = async () => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await pauseProject(currentProject.id);
      await fetchDdevStatus();
      toast({ title: 'Projet mis en pause', variant: 'info' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleStopProject = async () => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await stopProject(currentProject.id);
      await fetchDdevStatus();
      toast({ title: 'Projet arrêté', variant: 'info' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleRestartProject = async () => {
    if (!currentProject) return;
    setDdevLoading(true);
    try {
      await restartProject(currentProject.id);
      await fetchDdevStatus();
      toast({ title: 'Projet redémarré', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleRecreateProject = async () => {
    if (!currentProject) return;
    const confirmed = await confirm({
      title: 'Recréer le projet',
      description: 'Cela va détruire et reconstruire les conteneurs DDEV de ce projet. Les données sont conservées.',
      confirmLabel: 'Recréer',
      variant: 'destructive',
    });
    if (!confirmed) return;
    setDdevLoading(true);
    try {
      await recreateProject(currentProject.id);
      await fetchDdevStatus();
      toast({ title: 'Projet recréé avec succès', variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const handleResetProject = async () => {
    if (!currentProject) return;
    const confirmed = await confirm({
      title: 'Réinitialiser le projet',
      description: `Supprimer et recréer complètement l'environnement DDEV de "${currentProject.name}" ? Toutes les modifications locales non sauvegardées seront perdues.`,
      confirmLabel: 'Réinitialiser',
      variant: 'destructive',
    });
    if (!confirmed) return;
    setDdevLoading(true);
    try {
      await resetProject(currentProject.id);
      const data = await getProjects();
      setProjects(data.projects);
      const updated = data.projects.find(p => p.id === currentProject.id);
      if (updated) setCurrentProject(updated);
      await fetchDdevStatus();
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
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;
  const anyLoading = ddevLoading || workflowLoading;

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      {dialog}
      <Toaster toasts={toasts} dismiss={dismiss} />

      <Header
        activePage="dashboard"
        rightActions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowQueueModal(true)}
              className="h-8 text-xs px-2.5 bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/20"
              title="Voir la file d'attente"
            >
              <Clock className="mr-1.5 h-3.5 w-3.5" />
              <span className="hidden sm:inline">File d'attente</span>
              {queueInfo && (queueInfo.total_active > 0 || queueInfo.total_pending > 0) && (
                <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-[10px] bg-amber-500/20 text-amber-300">
                  {queueInfo.total_active + queueInfo.total_pending}
                </Badge>
              )}
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleGlobalReset}
              disabled={anyLoading}
              title="Réinitialiser l'environnement DDEV (Global Power-off)"
              className="h-8 text-xs px-2.5 bg-slate-900 border-slate-800 hover:border-slate-700 text-slate-300"
            >
              <RotateCcw className={cn("mr-1.5 h-3.5 w-3.5 text-cyan-400", anyLoading && "animate-spin")} />
              <span className="hidden sm:inline">Reset DDEV</span>
            </Button>

            {currentProject && (
              <div className="hidden lg:flex items-center gap-2 px-3 py-1 bg-slate-900/60 rounded-xl border border-slate-800">
                <div className={cn(
                  "h-2 w-2 rounded-full animate-pulse",
                  ddevStatus === 'running' ? "bg-emerald-500" :
                    ddevStatus === 'starting' ? "bg-cyan-400" :
                      ddevStatus === 'stopped' ? "bg-amber-500" : "bg-slate-600"
                )} />
                <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
                  DDEV: {ddevStatus}
                </span>
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowNotificationModal(true)}
              className="h-8 w-8 relative bg-slate-900 border-slate-800 text-slate-300 hover:text-white"
              title="Notifications"
            >
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-xs animate-pulse">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </Button>
          </div>
        }
      />

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
              <ProjectToolbar
                currentProject={currentProject}
                currentWorkflow={currentWorkflow}
                ddevStatus={ddevStatus}
                anyLoading={anyLoading}
                workflowLoading={workflowLoading}
                showLogs={showLogs}
                onToggleLogs={() => setShowLogs(!showLogs)}
                onCancelWorkflow={handleCancelWorkflow}
                onStartProject={handleStartProject}
                onPauseProject={handlePauseProject}
                onStopProject={handleStopProject}
                onRestartProject={handleRestartProject}
                onRecreateProject={handleRecreateProject}
                onResetProject={handleResetProject}
                onStartWorkflow={handleStartWorkflow}
                onStartImportOnlyWorkflow={handleStartImportOnlyWorkflow}
              />

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
                <VRTReportViewer
                  vrtReport={vrtReport}
                  vrtLoading={vrtLoading}
                  globalViewMode={globalViewMode}
                  setGlobalViewMode={setGlobalViewMode}
                  collapsedItems={collapsedItems}
                  setCollapsedItems={setCollapsedItems}
                  hasCurrentProject={Boolean(currentProject)}
                />
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
      <NotificationModal isOpen={showNotificationModal} onClose={() => setShowNotificationModal(false)} />
    </div>
  );
}
