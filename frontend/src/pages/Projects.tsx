import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAppStore } from '@/stores/appStore';
import {
  getProjects,
  deleteProject,
  resetProject,
  startWorkflow,
  resetDDEVGlobal,
  checkHealth,
  startBatchWorkflows,
  deleteProjectsBatch,
} from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ProjectForm } from '@/components/project/ProjectForm';
import { NotificationModal } from '@/components/dashboard/NotificationModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { useConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Toaster, useToast } from '@/components/ui/Toaster';
import { cn } from '@/lib/utils';
import type { Project, ProjectStatus } from '@/types';
import {
  Wrench,
  FolderOpen,
  Globe,
  Play,
  RotateCcw,
  Trash2,
  RefreshCw,
  Search,
  LayoutGrid,
  CheckSquare,
  X,
  Plus,
  Loader2,
  Heart,
  AlertCircle,
  Bell,
  ArrowRight,
  FileArchive,
  Layers,
} from 'lucide-react';

const STATUS_CONFIG: Record<
  ProjectStatus,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' }
> = {
  created: { label: 'Créé', variant: 'secondary' },
  initializing: { label: 'Initialisation', variant: 'default' },
  wordpress_installed: { label: 'WP Installé', variant: 'default' },
  importing: { label: 'Import en cours', variant: 'default' },
  ready: { label: 'Prêt', variant: 'success' },
  pending: { label: 'En attente', variant: 'warning' },
  maintenance_in_progress: { label: 'Maintenance', variant: 'warning' },
  maintenance_done: { label: 'Terminé', variant: 'success' },
  error: { label: 'Erreur', variant: 'destructive' },
  stopped: { label: 'Arrêté', variant: 'outline' },
  paused: { label: 'En pause', variant: 'warning' },
  deleting: { label: 'Suppression...', variant: 'warning' },
};

export const Projects: React.FC = () => {
  const navigate = useNavigate();
  const {
    projects,
    setProjects,
    setCurrentProject,
    setCurrentWorkflow,
    notifications,
    ddevLoading,
    setDdevLoading,
  } = useAppStore();

  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [actionLoading, setActionLoading] = useState<{ projectId: number; action: string } | null>(null);
  const [selectedProjects, setSelectedProjects] = useState<Set<number>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [showNewProjectForm, setShowNewProjectForm] = useState(false);
  const [showNotificationModal, setShowNotificationModal] = useState(false);
  const [health, setHealth] = useState<{ ddev: boolean; docker: boolean } | null>(null);

  const { confirm, dialog } = useConfirmDialog();
  const { toast, dismiss, toasts } = useToast();

  useWebSocket();

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getProjects();
      setProjects(data.projects);
    } catch (err) {
      console.error('Erreur lors du chargement des projets:', err);
      toast({ title: 'Erreur', description: 'Impossible de charger la liste des projets.', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [setProjects, toast]);

  useEffect(() => {
    fetchProjects();
    checkHealth()
      .then((h) =>
        setHealth({
          ddev: h.checks.ddev_installed,
          docker: h.checks.docker_running,
        })
      )
      .catch(() => setHealth(null));

    const handleQueueUpdate = () => fetchProjects();
    window.addEventListener('app:queue_updated', handleQueueUpdate);
    return () => window.removeEventListener('app:queue_updated', handleQueueUpdate);
  }, [fetchProjects]);

  const handleStartWorkflow = async (project: Project) => {
    setActionLoading({ projectId: project.id, action: 'start' });
    try {
      const workflow = await startWorkflow(project.id);
      setCurrentWorkflow(workflow);
      setCurrentProject(project);
      toast({
        title: 'Maintenance lancée',
        description: `Maintenance démarrée pour "${project.name}". Redirection vers le tableau de bord...`,
        variant: 'success',
      });
      setTimeout(() => {
        navigate(`/?project=${project.id}`);
      }, 600);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Impossible de lancer la maintenance.';
      toast({ title: 'Erreur', description: errMsg, variant: 'warning' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReset = async (project: Project) => {
    setActionLoading({ projectId: project.id, action: 'reset' });
    try {
      await resetProject(project.id);
      await fetchProjects();
      toast({ title: 'Projet réinitialisé', description: `"${project.name}" a été réinitialisé.`, variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (project: Project) => {
    const confirmed = await confirm({
      title: 'Supprimer le projet',
      description: `Voulez-vous vraiment supprimer le projet "${project.name}" ? Cette action est irréversible.`,
      confirmLabel: 'Supprimer',
      variant: 'destructive',
    });
    if (!confirmed) return;

    setActionLoading({ projectId: project.id, action: 'delete' });
    try {
      await deleteProject(project.id);
      await fetchProjects();
      toast({ title: 'Projet supprimé', description: `"${project.name}" a été supprimé.`, variant: 'success' });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleOpenProject = (project: Project) => {
    setCurrentProject(project);
    navigate(`/?project=${project.id}`);
  };

  const handleGlobalReset = async () => {
    const confirmed = await confirm({
      title: 'Réinitialiser DDEV',
      description: 'Voulez-vous vraiment réinitialiser l\'environnement DDEV ? Cela arrêtera TOUS les projets en cours.',
      confirmLabel: 'Réinitialiser',
      variant: 'destructive',
    });
    if (!confirmed) return;

    setDdevLoading(true);
    try {
      await resetDDEVGlobal();
      toast({ title: 'DDEV réinitialisé avec succès', variant: 'success' });
      await fetchProjects();
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      toast({ title: 'Erreur', description: errMsg, variant: 'destructive' });
    } finally {
      setDdevLoading(false);
    }
  };

  const toggleSelection = (id: number) => {
    const newSet = new Set(selectedProjects);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedProjects(newSet);
  };

  const handleBatchRun = async () => {
    if (selectedProjects.size === 0) return;
    const confirmed = await confirm({
      title: 'Lancer la maintenance groupée',
      description: `Lancer la maintenance pour ces ${selectedProjects.size} projet(s) sélectionné(s) ?`,
      confirmLabel: 'Lancer',
    });
    if (!confirmed) return;

    setBatchLoading(true);
    try {
      await startBatchWorkflows(Array.from(selectedProjects));
      toast({ title: 'Maintenance groupée lancée', variant: 'success' });
      setSelectionMode(false);
      setSelectedProjects(new Set());
      await fetchProjects();
    } catch (err) {
      console.error(err);
      toast({ title: 'Erreur lors du lancement groupé', variant: 'destructive' });
    } finally {
      setBatchLoading(false);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedProjects.size === 0) return;
    const confirmed = await confirm({
      title: 'Supprimer les projets',
      description: `Supprimer définitivement ces ${selectedProjects.size} projets ? Cette action est irréversible.`,
      confirmLabel: 'Supprimer',
      variant: 'destructive',
    });
    if (!confirmed) return;

    setBatchLoading(true);
    try {
      await deleteProjectsBatch(Array.from(selectedProjects));
      toast({ title: 'Projets supprimés', variant: 'success' });
      setSelectionMode(false);
      setSelectedProjects(new Set());
      await fetchProjects();
    } catch (err) {
      console.error(err);
      toast({ title: 'Erreur lors de la suppression groupée', variant: 'destructive' });
    } finally {
      setBatchLoading(false);
    }
  };

  const filteredProjects = projects.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.domain.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || p.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const unreadNotifications = notifications.filter((n) => !n.read).length;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {dialog}
      <Toaster toasts={toasts} dismiss={dismiss} />

      {/* Header */}
      <header className="border-b border-border px-4 md:px-6 py-3 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Wrench className="h-6 w-6 text-primary" />
            <Link to="/" className="text-xl font-bold hover:text-primary transition-colors">
              Auto Maintenance
            </Link>
            <Badge variant="outline" className="text-xs hidden sm:block">
              Projets
            </Badge>
          </div>

          <div className="flex items-center gap-2 md:gap-4">
            <Button variant="outline" size="sm" asChild className="h-8 text-xs px-2.5">
              <Link to="/">
                <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
                <span>Tableau de bord</span>
              </Link>
            </Button>

            <Button variant="outline" size="sm" asChild className="h-8 text-xs px-2.5">
              <Link to="/containers">
                <Layers className="mr-1.5 h-3.5 w-3.5" />
                <span className="hidden sm:inline">Containers</span>
              </Link>
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleGlobalReset}
              disabled={ddevLoading}
              title="Réinitialiser l'environnement DDEV (Global Power-off)"
              className="h-8 text-xs px-2"
            >
              <RotateCcw className={cn('mr-1.5 h-3.5 w-3.5', ddevLoading && 'animate-spin')} />
              <span className="hidden sm:inline">Reset DDEV</span>
            </Button>

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

            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowNotificationModal(true)}
              className="h-8 w-8 relative text-muted-foreground hover:text-foreground"
              title="Notifications"
            >
              <Bell className="h-4 w-4" />
              {unreadNotifications > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white shadow-xs animate-pulse">
                  {unreadNotifications > 9 ? '9+' : unreadNotifications}
                </span>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto space-y-6 max-w-7xl mx-auto w-full">
        {/* Page Title & Quick Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
              <FolderOpen className="h-7 w-7 text-primary" />
              Gestion des Projets
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Gérez l'ensemble de vos sites WordPress, lancez des maintenances et visualisez leur état.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              onClick={() => setShowNewProjectForm(!showNewProjectForm)}
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              {showNewProjectForm ? 'Masquer le formulaire' : 'Nouveau Projet'}
            </Button>
          </div>
        </div>

        {/* Collapsible New Project Form */}
        {showNewProjectForm && (
          <Card className="animate-in fade-in slide-in-from-top-4 duration-200 border-primary/20 bg-primary/5">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center justify-between">
                <span>Ajouter un nouveau projet</span>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowNewProjectForm(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProjectForm onToast={(title, variant) => toast({ title, variant: variant || 'default' })} />
            </CardContent>
          </Card>
        )}

        {/* Filters and Controls Bar */}
        <Card className="p-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2 w-full md:w-auto flex-1">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
                <Input
                  placeholder="Rechercher par nom ou domaine..."
                  className="pl-9 h-9 text-sm"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                {searchTerm && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchTerm('')}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>

              <select
                className="h-9 px-3 text-xs md:text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-1 focus:ring-ring"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="all">Tous les statuts ({projects.length})</option>
                <option value="ready">Prêt</option>
                <option value="pending">En attente</option>
                <option value="maintenance_in_progress">Maintenance en cours</option>
                <option value="maintenance_done">Maintenance terminée</option>
                <option value="error">Erreur</option>
                <option value="stopped">Arrêté</option>
              </select>
            </div>

            <div className="flex items-center gap-2 w-full md:w-auto justify-end">
              {selectionMode ? (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={selectedProjects.size === 0 || batchLoading}
                    onClick={handleBatchDelete}
                    className="h-9 text-xs px-3"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                    Supprimer ({selectedProjects.size})
                  </Button>

                  <Button
                    size="sm"
                    variant="default"
                    disabled={selectedProjects.size === 0 || batchLoading}
                    onClick={handleBatchRun}
                    className="h-9 text-xs px-3"
                  >
                    <Play className="h-3.5 w-3.5 mr-1.5" />
                    Lancer ({selectedProjects.size})
                  </Button>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setSelectionMode(false);
                      setSelectedProjects(new Set());
                    }}
                    className="h-9 text-xs"
                  >
                    Annuler
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 text-xs gap-1.5"
                    onClick={() => setSelectionMode(true)}
                    disabled={projects.length === 0}
                  >
                    <CheckSquare className="h-3.5 w-3.5" />
                    Sélection multiple
                  </Button>

                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9"
                    onClick={fetchProjects}
                    disabled={loading}
                    title="Actualiser les projets"
                  >
                    <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
                  </Button>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Projects Cards Grid */}
        {loading && projects.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-3 text-sm text-muted-foreground">Chargement des projets...</span>
          </div>
        ) : filteredProjects.length === 0 ? (
          <Card className="py-16 text-center border-dashed">
            <CardContent className="flex flex-col items-center justify-center space-y-3">
              <FolderOpen className="h-12 w-12 text-muted-foreground/30" />
              <h3 className="text-lg font-semibold text-muted-foreground">Aucun projet trouvé</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                {searchTerm || statusFilter !== 'all'
                  ? 'Aucun projet ne correspond à vos critères de recherche.'
                  : 'Commencez par ajouter votre premier projet WordPress.'}
              </p>
              {!showNewProjectForm && (
                <Button onClick={() => setShowNewProjectForm(true)} className="mt-2 gap-1.5">
                  <Plus className="h-4 w-4" />
                  Créer un projet
                </Button>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredProjects.map((project) => {
              const statusConfig = STATUS_CONFIG[project.status] || STATUS_CONFIG.created;
              const isChecked = selectedProjects.has(project.id);
              const isLoadingAction = actionLoading?.projectId === project.id;
              const isDeleting = project.status === 'deleting';

              return (
                <Card
                  key={project.id}
                  className={cn(
                    'group relative transition-all duration-200 hover:shadow-md flex flex-col justify-between border-border/80',
                    selectionMode && isChecked && 'border-primary bg-primary/5',
                    isDeleting && 'opacity-60 pointer-events-none'
                  )}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {selectionMode && (
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggleSelection(project.id)}
                            className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                          />
                        )}
                        <FolderOpen className="h-5 w-5 text-primary shrink-0" />
                        <h3 className="font-bold text-base truncate text-foreground group-hover:text-primary transition-colors">
                          {project.name}
                        </h3>
                      </div>
                      <Badge variant={statusConfig.variant} className="shrink-0 text-xs font-normal">
                        {statusConfig.label}
                      </Badge>
                    </div>

                    <a
                      href={`http://${project.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1.5 mt-1 transition-colors truncate"
                    >
                      <Globe className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{project.domain}</span>
                    </a>
                  </CardHeader>

                  <CardContent className="pt-0 pb-4 flex-1">
                    <div className="text-xs text-muted-foreground/80 space-y-1.5 bg-muted/20 p-2.5 rounded-md border border-border/40">
                      <div className="flex items-center justify-between">
                        <span>Fichier .wpress :</span>
                        <span className="font-mono text-[11px] truncate max-w-[150px]" title={project.wpress_file || 'Non défini'}>
                          {project.wpress_file ? (
                            <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                              <FileArchive className="h-3 w-3" /> Present
                            </span>
                          ) : (
                            <span className="text-muted-foreground font-normal">Non fourni</span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Créé le :</span>
                        <span>{new Date(project.created_at).toLocaleDateString('fr-FR')}</span>
                      </div>
                    </div>
                  </CardContent>

                  {/* Actions Footer */}
                  <div className="p-3 bg-muted/10 border-t border-border/50 flex items-center justify-between gap-1">
                    <Button
                      size="sm"
                      variant="default"
                      className="h-8 px-2.5 text-xs bg-primary text-primary-foreground shadow-xs gap-1"
                      onClick={() => handleStartWorkflow(project)}
                      disabled={isLoadingAction || isDeleting}
                      title="Lancer la maintenance / ajouter à la file"
                    >
                      {isLoadingAction && actionLoading?.action === 'start' ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Play className="h-3.5 w-3.5 fill-current" />
                      )}
                      <span>Lancer</span>
                    </Button>

                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2 text-xs gap-1"
                      onClick={() => handleOpenProject(project)}
                      title="Ouvrir dans le tableau de bord"
                    >
                      <span>Tableau de bord</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>

                    <div className="flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="outline"
                        className="h-8 w-8 text-rose-600 border-rose-200 hover:bg-rose-50 dark:border-rose-900/50"
                        onClick={() => handleReset(project)}
                        disabled={isLoadingAction || isDeleting}
                        title="Réinitialiser le projet"
                      >
                        {isLoadingAction && actionLoading?.action === 'reset' ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3.5 w-3.5" />
                        )}
                      </Button>

                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        onClick={() => handleDelete(project)}
                        disabled={isLoadingAction || isDeleting}
                        title="Supprimer définitivement"
                      >
                        {isLoadingAction && actionLoading?.action === 'delete' ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <NotificationModal isOpen={showNotificationModal} onClose={() => setShowNotificationModal(false)} />
    </div>
  );
};
