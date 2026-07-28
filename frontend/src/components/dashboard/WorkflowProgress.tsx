import { useAppStore } from '@/stores/appStore';
import { Progress } from '@/components/ui/Progress';
import { Badge } from '@/components/ui/Badge';
import { WORKFLOW_STEP_LABELS } from '@/types';
import { cn } from '@/lib/utils';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react';

const ALL_STEPS = [
  'ddev_create',
  'dns_setup',
  'wp_install',
  'plugin_install',
  'wpress_import',
  'screenshots_before',
  'updates_list',
  'updates_apply',
  'screenshots_after',
  'vrt_compare',
];

export function WorkflowProgress() {
  const { progress, currentStep, currentWorkflow } = useAppStore();

  const completedSteps = currentWorkflow?.steps_completed || [];
  const failedSteps = currentWorkflow?.steps_failed || [];
  const status = currentWorkflow?.status || 'pending';

  const getStepStatus = (step: string) => {
    if (completedSteps.includes(step)) return 'completed';
    if (failedSteps.includes(step)) return 'failed';
    if (step === currentStep) return 'running';
    return 'pending';
  };

  const getStepIcon = (stepStatus: string) => {
    switch (stepStatus) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-400" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-400" />;
      case 'running':
        return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
      default:
        return <Circle className="h-4 w-4 text-muted-foreground/40" />;
    }
  };

  const statusVariant = () => {
    switch (status) {
      case 'completed': return 'success' as const;
      case 'failed': return 'destructive' as const;
      case 'cancelled': return 'warning' as const;
      case 'running': return 'default' as const;
      default: return 'secondary' as const;
    }
  };

  const statusLabel = () => {
    switch (status) {
      case 'running': return 'En cours';
      case 'completed': return 'Terminé';
      case 'failed': return 'Échoué';
      case 'cancelled': return 'Annulé';
      default: return 'En attente';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Progression du Workflow</h3>
          {currentStep && (
            <p className="text-xs text-muted-foreground mt-1">
              {WORKFLOW_STEP_LABELS[currentStep] || currentStep}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusVariant()}>
            {statusLabel()}
          </Badge>
          <span className="text-sm font-medium text-muted-foreground">
            {Math.round(progress)}%
          </span>
        </div>
      </div>

      <Progress value={progress} />

      <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2">
        {ALL_STEPS.map((step) => {
          const stepStatus = getStepStatus(step);
          return (
            <div
              key={step}
              className={cn(
                'flex items-center gap-1.5 text-xs px-2 py-1.5 rounded border',
                stepStatus === 'completed' && 'border-green-800 bg-green-950/30',
                stepStatus === 'failed' && 'border-red-800 bg-red-950/30',
                stepStatus === 'running' && 'border-primary bg-primary/10',
                stepStatus === 'pending' && 'border-border',
              )}
              title={WORKFLOW_STEP_LABELS[step] || step}
            >
              {getStepIcon(stepStatus)}
              <span className="truncate hidden lg:inline">
                {WORKFLOW_STEP_LABELS[step] || step}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
