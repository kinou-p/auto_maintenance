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
} from '@/lib/api';
import { ProjectForm } from '@/components/project/ProjectForm';
import { ProjectList } from '@/components/project/ProjectList';
import { LogViewer } from '@/components/dashboard/LogViewer';
import { WorkflowProgress } from '@/components/dashboard/WorkflowProgress';
import { ImageComparer } from '@/components/vrt/ImageComparer';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import {
  Wrench,
  Play,
  StopCircle,
  ImageIcon,
  Heart,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Globe,
  FileText,
  RotateCcw,
} from 'lucide-react';
import type { VRTReport } from '@/types';

export function Dashboard() {
  const {
    currentProject,
    currentWorkflow,
    setCurrentWorkflow,
    clearLogs,
  } = useAppStore();

  const [vrtReport, setVrtReport] = useState<VRTReport | null>(null);
  const [health, setHealth] = useState<{ ddev: boolean; docker: boolean } | null>(null);
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
      return;
    }

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
  }, [currentProject, setCurrentWorkflow]);

  const handleStartWorkflow = async () => {
    if (!currentProject) return;
    setWorkflowLoading(true);
    clearLogs();

    try {
      const workflow = await startWorkflow(currentProject.id);
      setCurrentWorkflow(workflow);
    } catch (err) {
      console.error('Erreur workflow:', err);
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

          {/* Health indicators */}
          <div className="flex items-center gap-4">
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
                      <Button
                        size="sm"
                        onClick={handleStartWorkflow}
                        disabled={workflowLoading}
                      >
                        <Play className="mr-2 h-4 w-4" />
                        Lancer la maintenance
                      </Button>
                    )}
                  </div>
                </div>
              </div>

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
    </div>
  );
}
