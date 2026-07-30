import { create } from 'zustand';
import type { LogMessage, Project, Workflow } from '@/types';

const LOG_STORAGE_PREFIX = 'auto_maintenance_logs_';
const MAX_STORED_LOGS = 500;

function getStoredLogs(projectId: number): LogMessage[] {
  try {
    const raw = localStorage.getItem(`${LOG_STORAGE_PREFIX}${projectId}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function storeProjectLogs(projectId: number, logs: LogMessage[]): void {
  try {
    localStorage.setItem(
      `${LOG_STORAGE_PREFIX}${projectId}`,
      JSON.stringify(logs.slice(-MAX_STORED_LOGS)),
    );
  } catch {
    // silent fail
  }
}

function deleteProjectLogs(projectId: number): void {
  try {
    localStorage.removeItem(`${LOG_STORAGE_PREFIX}${projectId}`);
  } catch {
    // silent fail
  }
}

export interface AppNotification {
  id: string;
  title: string;
  description?: string;
  variant: 'default' | 'success' | 'warning' | 'destructive' | 'info';
  timestamp: string;
  read: boolean;
}

interface AppState {
  projects: Project[];
  currentProject: Project | null;
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  updateProject: (project: Project) => void;
  removeProject: (id: number) => void;

  currentWorkflow: Workflow | null;
  setCurrentWorkflow: (workflow: Workflow | null) => void;

  logs: LogMessage[];
  addLog: (log: LogMessage) => void;
  clearLogs: () => void;

  progress: number;
  currentStep: string | null;
  setProgress: (progress: number, step?: string) => void;

  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;

  sidebarOpen: boolean;
  toggleSidebar: () => void;

  ddevLoading: boolean;
  setDdevLoading: (loading: boolean) => void;

  workflowLoading: boolean;
  setWorkflowLoading: (loading: boolean) => void;

  notifications: AppNotification[];
  addNotification: (notification: Omit<AppNotification, 'id' | 'timestamp' | 'read'>) => void;
  markAllNotificationsAsRead: () => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  projects: [],
  currentProject: null,
  setProjects: (projects) => {
    const current = get().currentProject;
    if (current) {
      const updatedCurrent = projects.find((p) => p.id === current.id);
      set({ projects, currentProject: updatedCurrent || current });
    } else {
      set({ projects });
    }
  },
  setCurrentProject: (project) => {
    const current = get().currentProject;
    if (current && project && current.id === project.id) {
      set({ currentProject: project });
      return;
    }
    const logs = project ? getStoredLogs(project.id) : [];
    set({
      currentProject: project,
      logs,
      currentWorkflow: null,
      progress: 0,
      currentStep: null,
    });
  },
  updateProject: (project) =>
    set((state) => ({
      projects: state.projects.map((p) =>
        p.id === project.id ? project : p,
      ),
      currentProject:
        state.currentProject?.id === project.id
          ? project
          : state.currentProject,
    })),
  removeProject: (id) => {
    deleteProjectLogs(id);
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== id),
      currentProject:
        state.currentProject?.id === id ? null : state.currentProject,
      logs: state.currentProject?.id === id ? [] : state.logs,
    }));
  },

  currentWorkflow: null,
  setCurrentWorkflow: (workflow) =>
    set((state) => {
      let logs = state.logs;
      if (workflow && workflow.logs && workflow.logs.length > 0) {
        logs = workflow.logs;
        const projectId = state.currentProject?.id;
        if (projectId) {
          storeProjectLogs(projectId, logs);
        }
      }
      return { currentWorkflow: workflow, logs };
    }),

  logs: [],
  addLog: (log) =>
    set((state) => {
      const newLogs = [...state.logs, log].slice(-MAX_STORED_LOGS);
      const projectId = state.currentProject?.id;
      if (projectId) {
        storeProjectLogs(projectId, newLogs);
      }
      return { logs: newLogs };
    }),
  clearLogs: () => {
    const projectId = get().currentProject?.id;
    if (projectId) {
      deleteProjectLogs(projectId);
    }
    set({ logs: [] });
  },

  progress: 0,
  currentStep: null,
  setProgress: (progress, step) =>
    set({ progress, currentStep: step ?? null }),

  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  sidebarOpen: true,
  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  ddevLoading: false,
  setDdevLoading: (loading) => set({ ddevLoading: loading }),

  workflowLoading: false,
  setWorkflowLoading: (loading) => set({ workflowLoading: loading }),

  notifications: [],
  addNotification: (notification) =>
    set((state) => ({
      notifications: [
        {
          ...notification,
          id: `notif_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
          timestamp: new Date().toISOString(),
          read: false,
        },
        ...state.notifications,
      ].slice(0, 100),
    })),
  markAllNotificationsAsRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
    })),
  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),
  clearNotifications: () => set({ notifications: [] }),
}));

