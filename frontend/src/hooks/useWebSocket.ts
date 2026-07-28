/**
 * Hook WebSocket pour la réception des logs en temps réel.
 *
 * Gère la connexion, la reconnexion automatique et la prévention
 * des connexions zombies (React StrictMode, changement de projet).
 */

import { useEffect, useRef } from 'react';
import { useAppStore } from '@/stores/appStore';
import type { LogMessage } from '@/types';

export function useWebSocket(projectId?: number) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Flag pour empêcher les reconnexions zombies après cleanup
  const disposed = useRef(false);

  // Utiliser des refs stables pour les fonctions du store
  const storeRef = useRef(useAppStore.getState());
  storeRef.current = useAppStore.getState();

  useEffect(() => {
    disposed.current = false;

    function connect() {
      // Ne pas reconnecter si le hook a été nettoyé
      if (disposed.current) return;

      // Fermer toute connexion existante proprement
      if (wsRef.current) {
        const old = wsRef.current;
        wsRef.current = null;
        old.onclose = null; // Empêcher la reconnexion auto
        old.close();
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const path = projectId != null ? `/ws/${projectId}` : '/ws';
      const url = `${protocol}//${host}${path}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed.current) { ws.close(); return; }
        storeRef.current.setWsConnected(true);
        console.log(`[WS] Connecté (${path})`);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const state = useAppStore.getState();

          if (data.type === 'queue_updated' || data.type === 'workflow_status') {
            window.dispatchEvent(new CustomEvent('app:queue_updated'));
          }

          if (data.type === 'progress') {
            state.setProgress(data.progress, data.step);
          } else if (data.type === 'step_completed') {
            // Mise à jour en temps réel des étapes complétées/échouées
            const currentWorkflow = state.currentWorkflow;
            if (currentWorkflow && currentWorkflow.id === data.workflow_id) {
              state.setCurrentWorkflow({
                ...currentWorkflow,
                current_step: data.step,
                steps_completed: data.steps_completed || currentWorkflow.steps_completed,
                steps_failed: data.steps_failed || currentWorkflow.steps_failed,
              });
            }
          } else if (data.type === 'workflow_status') {
            // Événement de changement de statut du workflow
            const currentWorkflow = state.currentWorkflow;
            if (currentWorkflow && currentWorkflow.id === data.workflow_id) {
              // Mettre à jour le workflow actuel
              state.setCurrentWorkflow({
                ...currentWorkflow,
                status: data.status,
              });
            }

            // Mettre à jour le statut du projet concerné
            if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
              const project = state.projects.find(p => p.id === data.project_id);
              if (project) {
                const newStatus = data.completed ? 'maintenance_done' : 'error';
                state.updateProject({ ...project, status: newStatus });
              }
            } else if (data.status === 'running') {
              // Si le workflow démarre, mettre le projet en maintenance
              const project = state.projects.find(p => p.id === data.project_id);
              if (project && project.status !== 'maintenance_in_progress') {
                state.updateProject({ ...project, status: 'maintenance_in_progress' });
              }
            }
          } else if (data.type === 'project_deletion') {
            // Événement de suppression de projet
            if (data.status === 'completed') {
              // Retirer le projet de la liste
              state.removeProject(data.project_id);
            } else if (data.status === 'failed') {
              // Marquer le projet comme en erreur
              const project = state.projects.find(p => p.id === data.project_id);
              if (project) {
                state.updateProject({ ...project, status: 'error' });
              }
            }
            // Logger le message de suppression
            state.addLog({
              timestamp: new Date().toISOString(),
              level: data.status === 'failed' ? 'error' : 'info',
              message: data.message,
              step: 'deletion',
            } as LogMessage);
          } else if (data.type === 'updates_results' || data.type === 'vrt_report' || data.type === 'updates_available') {
            // Messages de données structurées - ignorer (gérés via API)
            console.log(`[WS] ${data.type} reçu:`, data);
          } else if (data.type === 'log' || data.level) {
            // Messages de logs avec timestamp
            state.addLog({
              timestamp: data.timestamp || new Date().toISOString(),
              level: data.level || 'info',
              message: data.message || '',
              step: data.step,
            } as LogMessage);
          }
        } catch (err) {
          console.warn('[WS] Erreur de parsing ou de traitement:', err);
        }
      };

      ws.onclose = () => {
        storeRef.current.setWsConnected(false);
        // Ne pas reconnecter si le hook a été nettoyé
        if (!disposed.current) {
          console.log('[WS] Déconnecté, reconnexion dans 3s...');
          reconnectTimer.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = (error) => {
        console.error('[WS] Erreur:', error);
        ws.close();
      };
    }

    connect();

    return () => {
      disposed.current = true;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null;
        ws.onclose = null; // Empêcher la reconnexion zombie
        ws.close();
      }
      storeRef.current.setWsConnected(false);
    };
  }, [projectId]);

  return wsRef;
}
