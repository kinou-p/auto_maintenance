/**
 * Dashboard - Page principale de l'application.
 */

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
  getProjectStatus,
  getProjects,
  getWorkflowQueue,
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
  } = useAppStore();

  // Restaurer le projet depuis l'URL (ex: ?project=3) au chargement
  useEffect(() => {
    const projectIdParam = searchParams.get('project');
    if (projectIdParam && projects.length > 0 && (!currentProject || currentProject.id !== parseInt(projectIdParam, 10))) {
      const found = projects.find(p => p.id === parseInt(projectIdParam, 10));
      if (found) {
        setCurrentProject(found);
      }
    }
  }, [projects, searchParams]);

  // Mettre à jour l'URL lorsque le projet courant change
  useEffect(() => {
    if (currentProject) {
      if (searchParams.get('project') !== String(currentProject.id)) {
        setSearchParams({ project: String(currentProject.id) }, { replace: true });
      }
    }
  }, [currentProject?.id]);

  const [vrtReport, setVrtReport] = useState<VRTReport | null>(null);
  const [health, setHealth] = useState<{ ddev: boolean; docker: boolean } | null>(null);
  const [ddevStatus, setDdevStatus] = useState<string>('unknown');
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [logPanelHeight, setLogPanelHeight] = useState(256);
  const [showLogs, setShowLogs] = useState(false); // Logs hidden by default or toggleable
  const [globalViewMode, setGlobalViewMode] = useState<'slider' | 'side-by-side' | 'diff'>('slider');
  const [collapsedItems, setCollapsedItems] = useState<Set<number>>(new Set());
  const isResizing = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Scroll to top when project changes
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
  }, [currentProject?.id]);

  // Resize handlers for log panel
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    const startY = e.clientY;
    const startHeight = logPanelHeight;

    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      // Panel is at top, dragging down (increasing Y) should increase height
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
  }, [logPanelHeight]);

  // WebSocket global
  useWebSocket(currentProject?.id);

  // Vérification santé au montage
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

  // Charger le rapport VRT du projet courant
  useEffect(() => {
    if (currentProject) {
      getVRTReport(currentProject.id)
        .then(setVrtReport)
        .catch(() => setVrtReport(null));
    }
  }, [currentProject]);

  // Vérifier et restaurer le workflow actif au chargement
  useEffect(() => {
    if (!currentProject) {
      setCurrentWorkflow(null);
      setDdevStatus('unknown');
      return;
    }

    // Charger le statut DDEV initial
    const fetchStatus = async () => {
      try {
        const status = await getProjectStatus(currentProject.id);
        const ddevData = status.ddev.data as any;
        const rawStatus = ddevData?.raw?.status || (status.ddev.running ? 'running' : 'stopped');
        setDdevStatus(rawStatus);
      } catch (err) {
        setDdevStatus('error');
      }
    };

    fetchStatus();

    // Polling du statut (toutes les 10s)
    const interval = setInterval(fetchStatus, 10000);

    // Vérifier s'il y a un workflow actif pour ce projet
    getActiveWorkflow(currentProject.id)
      .then((workflow) => {
        if (workflow) {
          console.log('[Dashboard] Workflow actif détecté, reconnexion:', workflow.id);
          setCurrentWorkflow(workflow);
        } else {
          // Pas de workflow actif, réinitialiser
          setCurrentWorkflow(null);
        }
      })
      .catch((err) => {
        console.error('[Dashboard] Erreur lors de la vérification du workflow actif:', err);
        setCurrentWorkflow(null);
      });

    return () => clearInterval(interval);
  }, [currentProject, setCurrentWorkflow]);

  const [queueInfo, setQueueInfo] = useState<{ total_active: number; total_pending: number } | null>(null);
  const [showQueueModal, setShowQueueModal] = useState(false);
  const [notification, setNotification] = useState<{ type: 'success' | 'info' | 'warning' | 'error'; message: string } | null>(null);

  const fetchQueueInfo = useCallback(async () => {
    try {
      const q = await getWorkflowQueue();
      setQueueInfo({ total_active: q.total_active, total_pending: q.total_pending });
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    fetchQueueInfo();
    const interval = setInterval(fetchQueueInfo, 4000);
    return () => clearInterval(interval);
  }, [fetchQueueInfo]);

  const handleStartWorkflow = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    clearLogs();

    try {
      const workflow = await startWorkflow(currentProject.id);
      setCurrentWorkflow(workflow);
      fetchQueueInfo();

      if (workflow.status === 'pending') {
        setNotification({
          type: 'info',
          message: `⏰ Maintenance ajoutée à la file d'attente pour "${currentProject.name}". Elle s'exécutera automatiquement à la suite du workflow en cours.`,
        });
      } else {
        setNotification({
          type: 'success',
          message: `🚀 Maintenance lancée immédiatement pour "${currentProject.name}".`,
        });
      }
    } catch (err: any) {
      console.error('Erreur workflow:', err);
      const errMsg = err.message || 'Impossible de lancer la maintenance.';
      setNotification({
        type: 'warning',
        message: errMsg,
      });
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleStartImportOnlyWorkflow = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    clearLogs();

    try {
      const workflow = await startWorkflow(currentProject.id, undefined, undefined, true);
      setCurrentWorkflow(workflow);
      fetchQueueInfo();

      if (workflow.status === 'pending') {
        setNotification({
          type: 'info',
          message: `⏰ Importation sans maintenance ajoutée à la file pour "${currentProject.name}".`,
        });
      } else {
        setNotification({
          type: 'success',
          message: `🚀 Lancement & Importation (sans maintenance) lancés pour "${currentProject.name}".`,
        });
      }
    } catch (err: any) {
      console.error('Erreur workflow:', err);
      const errMsg = err.message || 'Impossible de lancer l\'importation.';
      setNotification({
        type: 'warning',
        message: errMsg,
      });
    } finally {
      setWorkflowLoading(false);
    }
  };



  const refreshProjectState = async () => {
    if (!currentProject) return;
    try {
      const statusRes = await getProjectStatus(currentProject.id);
      const ddevData = statusRes.ddev.data as any;
      const rawStatus = ddevData?.raw?.status || (statusRes.ddev.status as string) || (statusRes.ddev.running ? 'running' : 'stopped');
      setDdevStatus(rawStatus);
      const allProjects = await getProjects();
      setProjects(allProjects.projects);
    } catch (err) {
      console.error('Error refreshing project status:', err);
    }
  };

  const handleStartProject = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    try {
      await startProject(currentProject.id);
      await refreshProjectState();
    } catch (err) {
      console.error('Error starting project:', err);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handlePauseProject = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    try {
      await pauseProject(currentProject.id);
      await refreshProjectState();
    } catch (err) {
      console.error('Error pausing project:', err);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleStopProject = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    try {
      await stopProject(currentProject.id);
      await refreshProjectState();
    } catch (err) {
      console.error('Error stopping project:', err);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleRestartProject = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    try {
      await restartProject(currentProject.id);
      await refreshProjectState();
    } catch (err) {
      console.error('Error restarting project:', err);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleRecreateProject = async () => {
    if (!currentProject) return;
    if (!confirm(`Recréer complètement l'environnement DDEV pour ${currentProject.name} ? Les fichiers seront préservés.`)) {
      return;
    }
    setWorkflowLoading(true);
    try {
      await recreateProject(currentProject.id);
      await refreshProjectState();
    } catch (err) {
      console.error('Error recreating project:', err);
    } finally {
      setWorkflowLoading(false);
    }
  };

  const handleCancelWorkflow = async () => {
    if (!currentWorkflow) return;
    try {
      await cancelWorkflow(currentWorkflow.id);
    } catch (err) {
      console.error('Erreur annulation:', err);
    }
  };

  const handleGlobalReset = async () => {
    if (!confirm("Voulez-vous vraiment réinitialiser l'environnement DDEV ?\nCela arrêtera TOUS les projets en cours (power-off).")) return;

    setWorkflowLoading(true);
    try {
      await resetDDEVGlobal();
      alert("DDEV a été réinitialisé avec succès.");
      // Optionnel : rafraîchir la santé ou les projets
      const h = await checkHealth();
      setHealth({ ddev: h.checks.ddev_installed, docker: h.checks.docker_running });
    } catch (err: any) {
      console.error('Error resetting DDEV:', err);
      alert(`Erreur lors de la réinitialisation : ${err.message}`);
    } finally {
      setWorkflowLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-border px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Wrench className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold">Auto Maintenance</h1>
            <Badge variant="outline" className="text-xs">v1.0</Badge>
          </div>

          {/* Navigation & Actions */}
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              asChild
              className="h-8 text-xs px-2"
            >
              <Link to="/containers">
                <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
                Containers
              </Link>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleGlobalReset}
              disabled={workflowLoading}
              title="Réinitialiser l'environnement DDEV (Global Power-off)"
              className="h-8 text-xs px-2"
            >
              <RotateCcw className={cn("mr-1.5 h-3.5 w-3.5", workflowLoading && "animate-spin")} />
              Reset DDEV
            </Button>

            {currentProject && (
              <div className="flex items-center gap-2 px-3 py-1 bg-muted/30 rounded-full border border-border/50">
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
              <div className="flex items-center gap-3">
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

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-80 border-r border-border flex flex-col shrink-0 custom-scrollbar">
          <div className="p-4 border-b border-border shrink-0">
            <ProjectForm />
          </div>
          <div className="flex-1 overflow-hidden p-4">
            <ProjectList />
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {currentProject ? (
            <>
              {/* Project Header */}
              <div className="px-6 py-4 border-b border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">{currentProject.name}</h2>
                    <a
                      href={`http://${currentProject.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
                    >
                      <Globe className="h-3 w-3" />
                      {currentProject.domain}
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowLogs(!showLogs)}
                      title={showLogs ? "Masquer les logs" : "Voir les logs"}
                    >
                      <FileText className="mr-2 h-4 w-4" />
                      {showLogs ? 'Masquer Logs' : 'Voir Logs'}
                    </Button>
                    {currentWorkflow?.status === 'running' ? (
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={handleCancelWorkflow}
                      >
                        <StopCircle className="mr-2 h-4 w-4" />
                        Annuler
                      </Button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleStartProject}
                          disabled={workflowLoading || ddevStatus === 'running'}
                          className="text-green-600 border-green-200 hover:bg-green-50"
                        >
                          <Play className="mr-2 h-4 w-4" />
                          Démarrer
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handlePauseProject}
                          disabled={workflowLoading || ddevStatus === 'paused' || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                          className="text-amber-600 border-amber-200 hover:bg-amber-50"
                        >
                          <Pause className="mr-2 h-4 w-4" />
                          Pause
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleStopProject}
                          disabled={workflowLoading || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                          className="text-orange-600 border-orange-200 hover:bg-orange-50"
                        >
                          <Square className="mr-2 h-4 w-4" />
                          Arrêter
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleRestartProject}
                          disabled={workflowLoading}
                          className="text-blue-600 border-blue-200 hover:bg-blue-50"
                        >
                          <RotateCcw className="mr-2 h-4 w-4" />
                          Redémarrer
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleRecreateProject}
                          disabled={workflowLoading}
                          className="text-purple-600 border-purple-200 hover:bg-purple-50"
                        >
                          <Hammer className="mr-2 h-4 w-4" />
                          Recréer
                        </Button>

                        <div className="h-6 w-px bg-border mx-1" />

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowQueueModal(true)}
                          className="text-amber-600 border-amber-500/30 hover:bg-amber-500/10 dark:text-amber-400"
                        >
                          <Clock className="mr-2 h-4 w-4" />
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
                          disabled={workflowLoading || currentProject.status === 'stopped'}
                          title="Lancer le projet et importer le site .wpress sans faire de maintenance"
                          className="border-primary/30 text-primary hover:bg-primary/10"
                        >
                          <Wrench className="mr-2 h-4 w-4" />
                          Lancer & Importer seulement
                        </Button>

                        <Button
                          size="sm"
                          onClick={handleStartWorkflow}
                          disabled={workflowLoading || currentProject.status === 'stopped'}
                        >
                          <Play className="mr-2 h-4 w-4" />
                          Lancer la maintenance
                        </Button>

                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Banner de notification / Feedback file d'attente */}
              {notification && (
                <div
                  className={cn(
                    "mx-6 mt-4 p-4 rounded-xl flex items-center justify-between border shadow-sm transition-all animate-in fade-in duration-200",
                    notification.type === 'success' && "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
                    notification.type === 'info' && "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400",
                    notification.type === 'warning' && "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
                    notification.type === 'error' && "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400",
                  )}
                >
                  <div className="flex items-center gap-2.5">
                    {notification.type === 'success' && <CheckCircle2 className="h-5 w-5 shrink-0" />}
                    {notification.type === 'info' && <Clock className="h-5 w-5 shrink-0" />}
                    {notification.type === 'warning' && <AlertCircle className="h-5 w-5 shrink-0" />}
                    {notification.type === 'error' && <AlertCircle className="h-5 w-5 shrink-0" />}
                    <span className="text-sm font-medium">{notification.message}</span>
                  </div>
                  <button
                    onClick={() => setNotification(null)}
                    className="text-xs font-semibold opacity-70 hover:opacity-100 ml-4 underline"
                  >
                    Fermer
                  </button>
                </div>
              )}


              {/* Workflow + Content Area */}

              {/* Workflow Progress (Fixed at top) */}
              <div className="p-6 pb-0 shrink-0">
                <Card>
                  <CardContent className="pt-6">
                    <WorkflowProgress />
                  </CardContent>
                </Card>
              </div>

              {/* Logs Panel (Top, resizable, toggleable) */}
              {showLogs && (
                <div
                  className="border-b border-border shrink-0 flex flex-col mt-6"
                  style={{ height: logPanelHeight }}
                >
                  <div className="flex-1 overflow-hidden">
                    <LogViewer />
                  </div>
                  {/* Resize handle (Bottom) */}
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
                className="flex-1 overflow-y-auto p-6 space-y-6"
              >
                {/* VRT Report */}
                {vrtReport && vrtReport.items.length > 0 && (
                  <>
                    {/* VRT Summary */}
                    <Card>
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-lg">
                          <ImageIcon className="h-5 w-5" />
                          Résumé
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          {/* Mises à jour */}
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

                          {/* Pages testées */}
                          <div className="space-y-1">
                            <div className="text-2xl font-bold">{vrtReport.total_pages}</div>
                            <div className="text-xs text-muted-foreground">Pages testées</div>
                          </div>

                          {/* Taux de succès VRT */}
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

                    {/* VRT Comparisons */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <CardTitle className="flex items-center gap-2 text-lg">
                            <ImageIcon className="h-5 w-5" />
                            Comparaison Visuelle
                            <Badge
                              variant={vrtReport.total_failed === 0 ? 'success' : 'destructive'}
                            >
                              {vrtReport.total_passed}/{vrtReport.total_pages} pass
                            </Badge>
                          </CardTitle>
                          <div className="flex items-center gap-2">
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
              </div>

              {/* Log panel (bottom, resizable) */}

            </>
          ) : (
            /* No project selected */
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

