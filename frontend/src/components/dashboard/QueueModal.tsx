/**
 * QueueModal - Modal / Tiroir d'affichage de la file d'attente des workflows.
 */

import { useState, useEffect, useCallback } from 'react';
import { getWorkflowQueue, cancelWorkflow, type QueueItem } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Clock, X, StopCircle, RefreshCw, Layers } from 'lucide-react';

import { cn } from '@/lib/utils';

interface QueueModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function QueueModal({ isOpen, onClose }: QueueModalProps) {
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getWorkflowQueue();
      setQueueItems(res.queue);
    } catch (err) {
      console.error('Erreur chargement file:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchQueue();
      const handleUpdate = () => fetchQueue();
      window.addEventListener('app:queue_updated', handleUpdate);
      return () => window.removeEventListener('app:queue_updated', handleUpdate);
    }
  }, [isOpen, fetchQueue]);

  const handleCancel = async (id: number) => {
    setCancellingId(id);
    try {
      await cancelWorkflow(id);
      await fetchQueue();
    } catch (err) {
      console.error('Erreur lors de l\'annulation:', err);
    } finally {
      setCancellingId(null);
    }
  };

  if (!isOpen) return null;

  const runningItems = queueItems.filter((i) => i.status === 'running');
  const pendingItems = queueItems.filter((i) => i.status === 'pending');

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl shadow-xl max-w-2xl w-full flex flex-col max-h-[85vh] overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-5 border-b border-border flex items-center justify-between bg-muted/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-500">
              <Layers className="h-5 w-5" />
            </div>
            <div>
              <h2 className="font-semibold text-lg leading-tight">File d'attente des maintenances</h2>
              <p className="text-xs text-muted-foreground">
                {runningItems.length} en cours, {pendingItems.length} en attente de traitement
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={fetchQueue} disabled={loading}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {queueItems.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground space-y-2">
              <Clock className="h-10 w-10 mx-auto opacity-40 mb-2" />
              <p className="font-medium text-foreground">Aucune maintenance en attente</p>
              <p className="text-xs max-w-sm mx-auto">
                Toutes les maintenances lancées s'exécutent les unes après les autres. La file d'attente est actuellement vide.
              </p>
            </div>
          ) : (
            <>
              {/* En cours (RUNNING) */}
              {runningItems.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                    </span>
                    En cours d'exécution
                  </h3>

                  {runningItems.map((item) => (
                    <Card key={item.id} className="border-emerald-500/30 bg-emerald-500/5">
                      <CardContent className="p-4 flex items-center justify-between gap-4">
                        <div className="space-y-1 min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm truncate">{item.project_name}</span>
                            <Badge variant="success" className="text-[10px]">EN COURS</Badge>
                          </div>
                          <p className="text-xs text-muted-foreground truncate">
                            {item.domain} {item.current_step && `• Étape : ${item.current_step}`}
                          </p>
                        </div>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCancel(item.id)}
                          disabled={cancellingId === item.id}
                          className="text-destructive border-destructive/30 hover:bg-destructive/10 shrink-0"
                        >
                          <StopCircle className="h-3.5 w-3.5 mr-1" />
                          Annuler
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}

              {/* En attente (PENDING) */}
              {pendingItems.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-amber-500" />
                    En attente dans la file ({pendingItems.length})
                  </h3>

                  <div className="space-y-2">
                    {pendingItems.map((item) => (
                      <Card key={item.id} className="hover:border-border/80 transition-colors">
                        <CardContent className="p-3.5 flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div className="w-7 h-7 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold text-xs flex items-center justify-center shrink-0">
                              #{item.position}
                            </div>
                            <div className="min-w-0">
                              <div className="font-medium text-sm truncate">{item.project_name}</div>
                              <div className="text-xs text-muted-foreground truncate">{item.domain}</div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 shrink-0">
                            <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-500/30">
                              EN ATTENTE
                            </Badge>

                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCancel(item.id)}
                              disabled={cancellingId === item.id}
                              className="text-xs text-muted-foreground hover:text-destructive"
                            >
                              Annuler
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-muted/20 flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Fermer
          </Button>
        </div>
      </div>
    </div>
  );
}
