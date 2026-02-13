/**
 * ProjectList - Liste des projets avec actions.
 */

import { useEffect, useState } from 'react';
import { useAppStore } from '@/stores/appStore';
import { getProjects, deleteProject, stopProject, startProject } from '@/lib/api';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import {
  FolderOpen,
  Play,
  Square,
  Trash2,
  RefreshCw,
  Globe,
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
  deleting: { label: 'Suppression...', variant: 'warning' },
};

export function ProjectList() {
  const { projects, setProjects, currentProject, setCurrentProject, removeProject, updateProject } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<{ projectId: number; action: 'start' | 'stop' | 'delete' } | null>(null);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (project: Project) => {
    if (!confirm(`Supprimer le projet "${project.name}" ? Cette action est irréversible.`)) {
      return;
    }
    
    // Désélectionner si c'est le projet actuel
    if (currentProject?.id === project.id) {
      setCurrentProject(null);
    }
    
    setActionLoading({ projectId: project.id, action: 'delete' });
    
    try {
      await deleteProject(project.id);
      // Recharger immédiatement pour voir le statut "deleting"
      fetchProjects();
    } catch (err) {
      console.error('Erreur lors de la suppression:', err);
      const errorMsg = err instanceof Error ? err.message : 'Erreur inconnue';
      alert(`Erreur lors du lancement de la suppression:\n\n${errorMsg}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async (project: Project) => {
    setActionLoading({ projectId: project.id, action: 'stop' });
    try {
      await stopProject(project.id);
      // Mettre à jour le statut localement
      updateProject({ ...project, status: 'stopped' });
    } catch (err) {
      console.error('Erreur:', err);
      alert(`Erreur lors de l'arrêt du projet: ${err instanceof Error ? err.message : 'Erreur inconnue'}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStart = async (project: Project) => {
    setActionLoading({ projectId: project.id, action: 'start' });
    try {
      await startProject(project.id);
      // Mettre à jour le statut localement
      updateProject({ ...project, status: 'ready' });
    } catch (err) {
      console.error('Erreur:', err);
      alert(`Erreur lors du démarrage du projet: ${err instanceof Error ? err.message : 'Erreur inconnue'}`);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Projets ({projects.length})</h3>
        <Button variant="ghost" size="icon" onClick={fetchProjects} disabled={loading}>
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </Button>
      </div>

      <div className="space-y-2">
        {projects.map((project) => {
          const statusConfig = STATUS_CONFIG[project.status] || STATUS_CONFIG.created;
          const isSelected = currentProject?.id === project.id;
          const isDeleting = project.status === 'deleting';

          return (
            <div
              key={project.id}
              className={cn(
                'p-3 rounded-lg border cursor-pointer transition-colors',
                isSelected
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/30',
                isDeleting && 'opacity-60',
              )}
              onClick={() => !isDeleting && setCurrentProject(project)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {isDeleting ? (
                    <RefreshCw className="h-4 w-4 text-primary animate-spin" />
                  ) : (
                    <FolderOpen className="h-4 w-4 text-primary" />
                  )}
                  <span className="text-sm font-medium">{project.name}</span>
                </div>
                <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
              </div>

              <div className="flex items-center gap-2 mt-2 text-xs">
                <Globe className="h-3 w-3 text-muted-foreground" />
                <a
                  href={`http://${project.domain}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-muted-foreground hover:text-primary underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  {project.domain}
                </a>
              </div>

              {isSelected && !isDeleting && (
                <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); handleStart(project); }}
                    title="Démarrer"
                    disabled={actionLoading?.projectId === project.id}
                  >
                    {actionLoading?.projectId === project.id && actionLoading.action === 'start' ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); handleStop(project); }}
                    title="Arrêter"
                    disabled={actionLoading?.projectId === project.id}
                  >
                    {actionLoading?.projectId === project.id && actionLoading.action === 'stop' ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Square className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <div className="flex-1" />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); handleDelete(project); }}
                    className="text-destructive hover:text-destructive"
                    title="Supprimer"
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
          );
        })}

        {projects.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground text-center py-8">
            Aucun projet. Créez votre premier projet ci-dessus.
          </p>
        )}
      </div>
    </div>
  );
}
