import { useEffect, useRef } from 'react';
import { useAppStore } from '@/stores/appStore';

export function useWebSocket(projectId?: number) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const disposed = useRef(false);

  const storeRef = useRef(useAppStore.getState());
  storeRef.current = useAppStore.getState();

  useEffect(() => {
    disposed.current = false;

    function connect() {
      if (disposed.current) return;

      if (wsRef.current) {
        const old = wsRef.current;
        wsRef.current = null;
        old.onclose = null;
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
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 25000);
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
            const currentWorkflow = state.currentWorkflow;
            if (currentWorkflow && currentWorkflow.id === data.workflow_id) {
              state.setCurrentWorkflow({
                ...currentWorkflow,
                status: data.status,
              });
            }

            if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
              const project = state.projects.find(p => p.id === data.project_id);
              if (project) {
                let newStatus: string;
                if (data.status === 'cancelled') {
                  newStatus = 'ready';
                } else if (data.status === 'completed' && data.completed) {
                  newStatus = 'maintenance_done';
                } else {
                  newStatus = 'error';
                }
                state.updateProject({ ...project, status: newStatus as typeof project.status });
              }
              window.dispatchEvent(new CustomEvent('app:vrt_refresh'));
            } else if (data.status === 'running') {
              const project = state.projects.find(p => p.id === data.project_id);
              if (project && project.status !== 'maintenance_in_progress') {
                state.updateProject({ ...project, status: 'maintenance_in_progress' });
              }
            }
          } else if (data.type === 'project_deletion') {
            if (data.status === 'completed') {
              state.removeProject(data.project_id);
            } else if (data.status === 'failed') {
              const project = state.projects.find(p => p.id === data.project_id);
              if (project) {
                state.updateProject({ ...project, status: 'error' });
              }
            }
            state.addLog({
              type: 'log',
              timestamp: new Date().toISOString(),
              level: data.status === 'failed' ? 'error' : 'info',
              message: data.message || '',
              step: 'deletion',
              details: null,
              progress: null,
              project_id: data.project_id || 0,
              workflow_id: 0,
            });
          } else if (data.type === 'vrt_report') {
            window.dispatchEvent(new CustomEvent('app:vrt_refresh'));
          } else if (data.type === 'updates_results' || data.type === 'updates_available') {
            console.log(`[WS] ${data.type} reçu:`, data);
          } else if (data.type === 'log' || data.level) {
            state.addLog({
              type: 'log',
              timestamp: data.timestamp || new Date().toISOString(),
              level: data.level || 'info',
              message: data.message || '',
              step: data.step || null,
              details: null,
              progress: null,
              project_id: data.project_id || 0,
              workflow_id: data.workflow_id || 0,
            });
          }
        } catch (err) {
          console.warn('[WS] Erreur de parsing ou de traitement:', err);
        }
      };

      ws.onclose = () => {
        clearInterval(heartbeatTimer.current);
        storeRef.current.setWsConnected(false);
        if (!disposed.current) {
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
      clearInterval(heartbeatTimer.current);
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null;
        ws.onclose = null;
        ws.close();
      }
      storeRef.current.setWsConnected(false);
    };
  }, [projectId]);

  return wsRef;
}
