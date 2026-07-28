/**
 * Auto Maintenance - Store global (Zustand).
 */

import { create } from 'zustand';
import type { LogMessage, Project, Workflow } from '@/types';

// ── Helpers localStorage pour les logs par projet ────────────────
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
    // localStorage plein — silent fail
  }
}

function deleteProjectLogs(projectId: number): void {
  try {
    localStorage.removeItem(`${LOG_STORAGE_PREFIX}${projectId}`);
  } catch {
    // silent fail
  }
}

interface AppState {
  // ── Projects ───────────────────────────────────────────────────
  projects: Project[];
  currentProject: Project | null;
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  updateProject: (project: Project) => void;
  removeProject: (id: number) => void;

  // ── Workflows ──────────────────────────────────────────────────
  currentWorkflow: Workflow | null;
  setCurrentWorkflow: (workflow: Workflow | null) => void;

  // ── Logs ───────────────────────────────────────────────────────
  logs: LogMessage[];
  addLog: (log: LogMessage) => void;
  clearLogs: () => void;

  // ── Progress ───────────────────────────────────────────────────
  progress: number;
  currentStep: string | null;
  setProgress: (progress: number, step?: string) => void;

  // ── WebSocket ──────────────────────────────────────────────────
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;

  // ── UI ─────────────────────────────────────────────────────────
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Projects
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
    // Charger les logs sauvegardés du projet sélectionné
    const logs = project ? getStoredLogs(project.id) : [];
    set({
      currentProject: project,
      logs,
      // Réinitialiser l'état du workflow/progression au changement de projet
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
    // Supprimer les logs persistés du projet
    deleteProjectLogs(id);
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== id),
      currentProject:
        state.currentProject?.id === id ? null : state.currentProject,
      // Vider les logs si c'est le projet courant
      logs: state.currentProject?.id === id ? [] : state.logs,
    }));
  },

  // Workflows
  currentWorkflow: null,
  setCurrentWorkflow: (workflow) => set({ currentWorkflow: workflow }),

  // Logs
  logs: [],
  addLog: (log) =>
    set((state) => {
      const newLogs = [...state.logs, log].slice(-MAX_STORED_LOGS);
      // Persister dans localStorage pour le projet courant
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

  // Progress
  progress: 0,
  currentStep: null,
  setProgress: (progress, step) =>
    set({ progress, currentStep: step ?? null }),

  // WebSocket
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  // UI
  sidebarOpen: true,
  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));
