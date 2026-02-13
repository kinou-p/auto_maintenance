/**
 * Auto Maintenance - Client API.
 */

import type {
  HealthCheck,
  Project,
  UpdateItem,
  UpdateResult,
  VRTReport,
  Workflow,
} from '@/types';

const API_BASE = '/api';

async function apiFetch<T>(
  path: string,
  options?: RequestInit & { timeout?: number },
): Promise<T> {
  const timeout = options?.timeout || 30000; // Défaut 30s
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `API Error ${res.status}`);
    }

    return res.json();
  } catch (error) {
    clearTimeout(timeoutId);
    
    // Si c'est une erreur d'abort (timeout)
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`L'opération a dépassé le délai maximum (${timeout / 1000}s). Elle continue peut-être en arrière-plan.`);
    }
    
    // Si c'est une erreur réseau (backend inaccessible)
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error('Impossible de contacter le serveur backend. Vérifiez qu\'il est démarré.');
    }
    throw error;
  }
}

// ── Health ────────────────────────────────────────────────────────
export const checkHealth = () => apiFetch<HealthCheck>('/health');

// ── Projects ─────────────────────────────────────────────────────
export const getProjects = () =>
  apiFetch<{ projects: Project[]; total: number }>('/projects');

export const getProject = (id: number) =>
  apiFetch<Project>(`/projects/${id}`);

export const getProjectStatus = (id: number) =>
  apiFetch<{ project: Project; ddev: Record<string, unknown> }>(
    `/projects/${id}/status`,
  );

export const createProject = async (
  name: string,
  domain?: string,
  wpress?: File,
): Promise<Project> => {
  const formData = new FormData();
  formData.append('name', name);
  if (domain) formData.append('domain', domain);
  if (wpress) formData.append('wpress_file', wpress);

  const res = await fetch(`${API_BASE}/projects/`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API Error ${res.status}`);
  }

  return res.json();
};

export const createProjectsBatch = async (
  wpressFiles: File[],
): Promise<{ status: string; message: string; created: Project[]; errors: Array<{ file: string; error: string }> }> => {
  const formData = new FormData();
  wpressFiles.forEach((file) => {
    formData.append('wpress_files', file);
  });

  const res = await fetch(`${API_BASE}/projects/batch`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API Error ${res.status}`);
  }

  return res.json();
};

export const deleteProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}`, {
    method: 'DELETE',
    timeout: 30000, // 30s - la requête retourne immédiatement, la suppression continue en arrière-plan
  });

export const stopProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/stop`, {
    method: 'POST',
  });

export const startProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/start`, {
    method: 'POST',
  });

// ── Workflows ────────────────────────────────────────────────────
export const startWorkflow = (
  projectId: number,
  steps?: string[],
  selectedUpdates?: string[],
) =>
  apiFetch<Workflow>('/workflows/', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      steps,
      selected_updates: selectedUpdates,
    }),
  });

export const getWorkflow = (id: number) =>
  apiFetch<Workflow>(`/workflows/${id}`);

export const getProjectWorkflows = (projectId: number) =>
  apiFetch<Workflow[]>(`/workflows/project/${projectId}`);

export const getActiveWorkflow = (projectId: number) =>
  apiFetch<Workflow | null>(`/workflows/project/${projectId}/active`);

export const cancelWorkflow = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/workflows/${id}/cancel`, {
    method: 'POST',
  });

export const getWorkflowLogs = (id: number) =>
  apiFetch<{ workflow_id: number; status: string; logs: unknown[] }>(
    `/workflows/${id}/logs`,
  );

// ── Updates ──────────────────────────────────────────────────────
export const getUpdates = (projectId: number) =>
  apiFetch<{
    project_id: number;
    core: UpdateItem | null;
    plugins: UpdateItem[];
    themes: UpdateItem[];
    total_available: number;
  }>(`/projects/${projectId}/updates`);

export const applyUpdates = (
  projectId: number,
  updateCore: boolean,
  pluginNames: string[],
  themeNames: string[],
) =>
  apiFetch<{
    project_id: number;
    results: UpdateResult[];
    total_success: number;
    total_failed: number;
  }>(`/projects/${projectId}/updates/apply`, {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      update_core: updateCore,
      plugin_names: pluginNames,
      theme_names: themeNames,
    }),
  });

// ── VRT ──────────────────────────────────────────────────────────
export const getVRTReport = (projectId: number) =>
  apiFetch<VRTReport>(`/projects/${projectId}/vrt`);

export const getVRTJsonReport = (projectId: number) =>
  apiFetch<Record<string, unknown>>(`/projects/${projectId}/vrt/report-json`);

// ── Sudoers ──────────────────────────────────────────────────────
export const setupSudoers = () =>
  apiFetch<{ status: string; message: string }>('/setup/sudoers', {
    method: 'POST',
  });
