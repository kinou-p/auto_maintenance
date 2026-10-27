import { Button } from '@/components/ui/Button';
import type { Project, Workflow } from '@/types';
import {
  Play,
  Pause,
  Square,
  Wrench,
  RotateCcw,
  Globe,
  FileText,
  StopCircle,
  Hammer,
  RefreshCw,
  MoreVertical,
} from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';

interface ProjectToolbarProps {
  currentProject: Project;
  currentWorkflow: Workflow | null;
  ddevStatus: string;
  anyLoading: boolean;
  workflowLoading: boolean;
  showLogs: boolean;
  onToggleLogs: () => void;
  onCancelWorkflow: () => void;
  onStartProject: () => void;
  onPauseProject: () => void;
  onStopProject: () => void;
  onRestartProject: () => void;
  onRecreateProject: () => void;
  onResetProject: () => void;
  onStartWorkflow: () => void;
  onStartImportOnlyWorkflow: () => void;
}

export function ProjectToolbar({
  currentProject,
  currentWorkflow,
  ddevStatus,
  anyLoading,
  workflowLoading,
  showLogs,
  onToggleLogs,
  onCancelWorkflow,
  onStartProject,
  onPauseProject,
  onStopProject,
  onRestartProject,
  onRecreateProject,
  onResetProject,
  onStartWorkflow,
  onStartImportOnlyWorkflow,
}: ProjectToolbarProps) {
  return (
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
            onClick={onToggleLogs}
            title={showLogs ? "Masquer les logs" : "Voir les logs"}
          >
            <FileText className="h-4 w-4" />
            <span className="hidden sm:inline ml-1.5">{showLogs ? 'Logs ↑' : 'Logs'}</span>
          </Button>
          {currentWorkflow?.status === 'running' ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={onCancelWorkflow}
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
                  onClick={onStartProject}
                  disabled={anyLoading || ddevStatus === 'running'}
                  title="Démarrer DDEV"
                  className="text-green-600 border-green-200 hover:bg-green-50"
                >
                  <Play className="h-4 w-4" />
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onPauseProject}
                  disabled={anyLoading || ddevStatus === 'paused' || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                  title="Pause DDEV"
                  className="text-amber-600 border-amber-200 hover:bg-amber-50"
                >
                  <Pause className="h-4 w-4" />
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onStopProject}
                  disabled={anyLoading || ddevStatus === 'stopped' || ddevStatus === 'unknown'}
                  title="Arrêter DDEV"
                  className="text-orange-600 border-orange-200 hover:bg-orange-50"
                >
                  <Square className="h-4 w-4" />
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onRestartProject}
                  disabled={anyLoading}
                  title="Redémarrer DDEV"
                  className="text-blue-600 border-blue-200 hover:bg-blue-50"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onRecreateProject}
                  disabled={anyLoading}
                  title="Recréer le projet"
                  className="text-purple-600 border-purple-200 hover:bg-purple-50"
                >
                  <Hammer className="h-4 w-4" />
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={onResetProject}
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
                      onSelect={onStartProject}
                    >
                      <Play className="h-4 w-4 text-green-600" />
                      Démarrer
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                      disabled={anyLoading || ddevStatus !== 'running'}
                      onSelect={onPauseProject}
                    >
                      <Pause className="h-4 w-4 text-amber-600" />
                      Pause
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                      disabled={anyLoading || (ddevStatus !== 'running' && ddevStatus !== 'paused')}
                      onSelect={onStopProject}
                    >
                      <Square className="h-4 w-4 text-orange-600" />
                      Arrêter
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                      disabled={anyLoading}
                      onSelect={onRestartProject}
                    >
                      <RotateCcw className="h-4 w-4 text-blue-600" />
                      Redémarrer
                    </DropdownMenu.Item>
                    <DropdownMenu.Separator className="h-px bg-border my-1" />
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent disabled:opacity-50"
                      disabled={anyLoading}
                      onSelect={onRecreateProject}
                    >
                      <Hammer className="h-4 w-4 text-purple-600" />
                      Recréer
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-sm cursor-pointer outline-none hover:bg-accent text-destructive disabled:opacity-50"
                      disabled={anyLoading}
                      onSelect={onResetProject}
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
            onClick={onStartImportOnlyWorkflow}
            disabled={workflowLoading}
            title="Lancer le projet et importer le site .wpress sans faire de maintenance"
            className="border-primary/30 text-primary hover:bg-primary/10"
          >
            <Wrench className="mr-1.5 h-4 w-4" />
            <span className="hidden sm:inline">Lancer & Importer</span>
          </Button>

          <Button
            size="sm"
            onClick={onStartWorkflow}
            disabled={workflowLoading}
          >
            <Play className="mr-1.5 h-4 w-4" />
            Lancer la maintenance
          </Button>
        </div>
      )}
    </div>
  );
}
