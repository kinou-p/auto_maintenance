/**
 * ProjectList - Liste des projets avec actions.
 */

import { useEffect, useState } from 'react';
import { useAppStore } from '@/stores/appStore';
import { getProjects, deleteProject, deleteProjectsBatch, startBatchWorkflows, resetProject } from '@/lib/api';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import {
  FolderOpen,
  Trash2,
  RefreshCw,
  CheckSquare,
  X,
  Loader2,
  Search,
  Play,
} from 'lucide-react';
import type { Project, ProjectStatus } from '@/types';

const STATUS_CONFIG: Record<ProjectStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' }> = {
  created: { label: 'Créé', variant: 'secondary' },
  initializing: { label: 'Initialisation', variant: 'default' },
  wordpress_installed: { label: 'WP Installé', variant: 'default' },
  importing: { label: 'Import en cours', variant: 'default' },
  ready: { label: 'Prêt', variant: 'success' },
  maintenance_in_progress: { label: 'Maintenance', variant: 'warning' },
  maintenance_done: { label: 'Terminé', variant: 'success' },
  error: { label: 'Erreur', variant: 'destructive' },
  stopped: { label: 'Arrêté', variant: 'outline' },
  paused: { label: 'En pause', variant: 'warning' },
  deleting: { label: 'Suppression...', variant: 'warning' },
};

export function ProjectList() {
  const { projects, setProjects, currentProject, setCurrentProject } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<{ projectId: number; action: 'delete' | 'reset' } | null>(null);
  const [selectedProjects, setSelectedProjects] = useState<Set<number>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [selectionMode, setSelectionMode] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const data = await getProjects();
      setProjects(data.projects);
    } catch (err) {
      console.error('Erreur lors du chargement des projets:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();

    const handleQueueUpdated = () => {
      fetchProjects();
    };

    window.addEventListener('app:queue_updated', handleQueueUpdated);
    const interval = setInterval(fetchProjects, 3000);

    return () => {
      window.removeEventListener('app:queue_updated', handleQueueUpdated);
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleSelection = (id: number) => {
    const newSet = new Set(selectedProjects);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedProjects(newSet);
  };

  const toggleSelectionMode = () => {
    setSelectionMode(!selectionMode);
    setSelectedProjects(new Set());
  };

  const handleBatchRun = async () => {
    if (selectedProjects.size === 0) return;

    if (!confirm(`Lancer la maintenance pour ces ${selectedProjects.size} projet(s) sélectionné(s) ?`)) {
      return;
    }

    setBatchLoading(true);
    try {
      const workflows = await startBatchWorkflows(Array.from(selectedProjects));

      // Si des workflows ont été créés, on focus le premier projet
      if (workflows && workflows.length > 0) {
        const firstProjectId = workflows[0]?.project_id;
        if (firstProjectId) {
          const projectToFocus = projects.find(p => p.id === firstProjectId);
          if (projectToFocus) {
            setCurrentProject(projectToFocus);
          }
        }
      }

      // Optionnel : notification toaster
      setSelectionMode(false);
      setSelectedProjects(new Set());
    } catch (err) {
      console.error('Erreur batch:', err);
      alert('Erreur lors du lancement groupé.');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedProjects.size === 0) return;

    if (!confirm(`Supprimer définitivement ces ${selectedProjects.size} projets ? Cette action est irréversible.`)) {
      return;
    }

    setBatchLoading(true);
    try {
      await deleteProjectsBatch(Array.from(selectedProjects));
      await fetchProjects();
      setSelectionMode(false);
      setSelectedProjects(new Set());
    } catch (err) {
      console.error('Erreur batch delete:', err);
      alert('Erreur lors de la suppression groupée.');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleBatchReset = async () => {
    if (selectedProjects.size === 0) return;

    if (!confirm(`Réinitialiser les ${selectedProjects.size} projet(s) sélectionné(s) ?\nLeurs conteneurs DDEV et rapports seront réinitialisés, et leur statut repassera à 'Créé' (sans supprimer les fichiers .wpress).`)) {
      return;
    }

    setBatchLoading(true);
    try {
      for (const id of Array.from(selectedProjects)) {
        await resetProject(id);
      }
      await fetchProjects();
      setSelectionMode(false);
      setSelectedProjects(new Set());
    } catch (err) {
      console.error('Erreur batch reset:', err);
      alert('Erreur lors de la réinitialisation groupée.');
    } finally {
      setBatchLoading(false);
    }
  };

  const handleSelectAll = () => {
    if (selectedProjects.size === projects.length) {
      setSelectedProjects(new Set());
    } else {
      setSelectedProjects(new Set(projects.map(p => p.id)));
    }
  };

  const handleDelete = async (project: Project) => {
    console.log('[CLICK] ProjectList handleDelete triggered', project);
    if (!window.confirm(`Supprimer définitivement le projet ${project.name} ?`)) return;

    setActionLoading({ projectId: project.id, action: 'delete' });
    try {
      await deleteProject(project.id);
      if (currentProject?.id === project.id) {
        setCurrentProject(null);
      }
      await fetchProjects();
    } catch (err) {
      console.error('Error deleting project:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReset = async (project: Project) => {
    console.log('[CLICK] ProjectList handleReset triggered', project);
    if (!window.confirm(`Réinitialiser le projet "${project.name}" ?\nLe conteneur DDEV et les rapports seront supprimés, et le statut repassera à 'Créé' (le fichier .wpress est conservé).`)) return;

    setActionLoading({ projectId: project.id, action: 'reset' });
    try {
      await resetProject(project.id);
      await fetchProjects();
    } catch (err) {
      console.error('Error resetting project:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const filteredProjects = projects.filter(p =>
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.domain.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 shrink-0">
        <h3 className="text-sm font-semibold text-foreground/90">
          Projets <span className="text-muted-foreground ml-1 font-normal">({projects.length})</span>
        </h3>
        <div className="flex items-center gap-1">
          {selectionMode ? (
            <div className="flex items-center gap-1 animate-in fade-in slide-in-from-right-4 duration-200">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleSelectAll}
                title={selectedProjects.size === projects.length ? "Tout désélectionner" : "Tout sélectionner"}
              >
                <CheckSquare className={cn("h-4 w-4", selectedProjects.size === projects.length && "text-primary")} />
              </Button>

              <div className="h-4 w-px bg-border mx-1" />

              <Button
                size="sm"
                variant="destructive"
                disabled={selectedProjects.size === 0 || batchLoading}
                onClick={handleBatchDelete}
                className="h-7 text-xs px-2"
                title="Supprimer définitivement la sélection"
              >
                {batchLoading ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3" />
                )}
                <span className="ml-1.5 hidden sm:inline">{selectedProjects.size}</span>
              </Button>

              <Button
                size="sm"
                variant="outline"
                disabled={selectedProjects.size === 0 || batchLoading}
                onClick={handleBatchReset}
                className="h-7 text-xs px-2 text-rose-600 border-rose-200 hover:bg-rose-50 dark:border-rose-900/50"
                title="Réinitialiser la sélection"
              >
                {batchLoading ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <RefreshCw className="h-3 w-3" />
                )}
                <span className="ml-1.5 hidden sm:inline">{selectedProjects.size}</span>
              </Button>

              <Button
                size="sm"
                variant="default"
                disabled={selectedProjects.size === 0 || batchLoading}
                onClick={handleBatchRun}
                className="h-7 text-xs px-2"
                title="Lancer la maintenance sélection"
              >
                {batchLoading ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <Play className="h-3 w-3" />
                )}
                <span className="ml-1.5 hidden sm:inline">{selectedProjects.size}</span>
              </Button>

              <Button size="icon" variant="ghost" className="h-7 w-7 ml-1" onClick={toggleSelectionMode}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 hover:bg-muted"
                onClick={toggleSelectionMode}
                title="Sélection multiple"
                disabled={projects.length === 0}
              >
                <CheckSquare className="h-4 w-4 text-muted-foreground" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-muted"
                onClick={fetchProjects}
                disabled={loading}
              >
                <RefreshCw className={cn("h-4 w-4 text-muted-foreground", loading && "animate-spin")} />
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="relative mb-3 shrink-0">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
        <Input
          placeholder="Rechercher un projet..."
          className="h-8 pl-8 text-xs bg-muted/30 border-none focus-visible:ring-1 focus-visible:ring-primary/20"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        {searchTerm && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 -translate-y-1/2 h-5 w-5 hover:bg-transparent"
            onClick={() => setSearchTerm('')}
          >
            <X className="h-3 w-3 text-muted-foreground/50 hover:text-muted-foreground" />
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 space-y-2 pr-2 custom-scrollbar">
        {filteredProjects.map((project) => {
          const statusConfig = STATUS_CONFIG[project.status] || STATUS_CONFIG.created;
          const isSelected = currentProject?.id === project.id;
          const isDeleting = project.status === 'deleting';
          const isChecked = selectedProjects.has(project.id);

          // Determine if project is running a task
          const isRunning = ['initializing', 'wordpress_installed', 'importing', 'maintenance_in_progress'].includes(project.status);

          return (
            <div
              key={project.id}
              className={cn(
                'group relative rounded-md border transition-all duration-200',
                isSelected && !selectionMode
                  ? 'border-primary bg-primary/5 shadow-sm'
                  : 'border-transparent bg-card hover:bg-accent/50 hover:border-border/50',
                isDeleting && 'opacity-60 pointer-events-none grayscale',
                isChecked && selectionMode && 'bg-primary/10 border-primary/50'
              )}
              onClick={() => {
                if (selectionMode) {
                  toggleSelection(project.id);
                } else if (!isDeleting) {
                  setCurrentProject(project);
                }
              }}
            >
              {/* Selection Checkbox Overlay */}
              {selectionMode && (
                <div className="absolute left-3 top-3 z-10">
                  <div className={cn(
                    "h-4 w-4 rounded border flex items-center justify-center transition-all bg-background",
                    isChecked ? "bg-primary border-primary text-primary-foreground" : "border-muted-foreground"
                  )}>
                    {isChecked && <CheckSquare className="h-3 w-3" />}
                  </div>
                </div>
              )}

              <div className={cn("p-3", selectionMode && "pl-9")}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {isDeleting ? (
                        <RefreshCw className="h-3.5 w-3.5 text-muted-foreground animate-spin shrink-0" />
                      ) : isRunning ? (
                        <Loader2 className="h-3.5 w-3.5 text-primary animate-spin shrink-0" />
                      ) : (
                        <FolderOpen className={cn("h-3.5 w-3.5 shrink-0", isSelected ? "text-primary" : "text-muted-foreground")} />
                      )}
                      <span className={cn("text-sm font-medium truncate", isSelected && "text-primary")}>
                        {project.name}
                      </span>
                    </div>

                    <div className="text-xs text-muted-foreground/70 truncate pl-5.5">
                      {project.domain}
                    </div>
                  </div>

                  <Badge
                    variant={statusConfig.variant}
                    className="shrink-0 text-[10px] px-1.5 py-0 h-5 font-normal"
                  >
                    {statusConfig.label}
                  </Badge>
                </div>

                {isSelected && !isDeleting && !selectionMode && (
                  <div className="flex items-center justify-end gap-1.5 mt-3 pt-2 border-t border-border/50 animate-in fade-in duration-200">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 text-xs text-rose-600 border-rose-200 hover:bg-rose-50 dark:border-rose-900/50"
                      onClick={(e) => { e.stopPropagation(); handleReset(project); }}
                      title="Réinitialiser le projet"
                      disabled={actionLoading?.projectId === project.id}
                    >
                      {actionLoading?.projectId === project.id && actionLoading.action === 'reset' ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5 mr-1" />
                      )}
                      Reset
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 hover:bg-background shadow-sm border border-border/50 hover:border-border hover:text-destructive"
                      onClick={(e) => { e.stopPropagation(); handleDelete(project); }}
                      title="Supprimer définitivement"
                      disabled={actionLoading?.projectId === project.id}
                    >
                      {actionLoading?.projectId === project.id && actionLoading.action === 'delete' ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {projects.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-12 text-center border-2 border-dashed border-border/50 rounded-lg bg-muted/20">
            <FolderOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
            <p className="text-sm text-muted-foreground">
              Aucun projet
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
