import type {
  HealthCheck,
  Project,
  UpdateItem,
  UpdateResult,
  VRTReport,
  Workflow,
  DDEVContainer,
} from '@/types';

const API_BASE = '/api';

let globalErrorHandler: ((message: string) => void) | null = null;

export function setGlobalErrorHandler(handler: (message: string) => void) {
  globalErrorHandler = handler;
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit & { timeout?: number },
): Promise<T> {
  const timeout = options?.timeout || 30000;
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
      const message = error.detail || `API Error ${res.status}`;
      throw new Error(message);
    }

    return res.json();
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error && error.name === 'AbortError') {
      const message = `L'opération a dépassé le délai maximum (${timeout / 1000}s). Elle continue peut-être en arrière-plan.`;
      globalErrorHandler?.(message);
      throw new Error(message);
    }

    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      const message = 'Impossible de contacter le serveur backend. Vérifiez qu\'il est démarré.';
      globalErrorHandler?.(message);
      throw new Error(message);
    }
    throw error;
  }
}

export const checkHealth = () => apiFetch<HealthCheck>('/health');

export const getProjects = () =>
  apiFetch<{ projects: Project[]; total: number }>('/projects/');

export const getProject = (id: number) =>
  apiFetch<Project>(`/projects/${id}`);

export const getProjectStatus = (id: number) =>
  apiFetch<{ project: Project; ddev: Record<string, unknown> }>(
    `/projects/${id}/status`,
  );

interface UploadController {
  abort: () => void;
}

function uploadWithProgress<T>(
  url: string,
  formData: FormData,
  onProgress?: (progress: number) => void,
  controller?: UploadController,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    if (controller) {
      controller.abort = () => {
        xhr.abort();
        reject(new Error('Upload annulé'));
      };
    }

    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve(xhr.responseText as unknown as T);
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `API Error ${xhr.status}`));
        } catch {
          reject(new Error(`API Error ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Erreur réseau lors de l\'envoi du fichier.'));
    xhr.ontimeout = () => reject(new Error('Le délai d\'envoi a expiré.'));
    xhr.onabort = () => reject(new Error('Upload annulé'));

    xhr.send(formData);
  });
}

export const createProject = async (
  name: string,
  domain?: string,
  wpress?: File,
  localFilePath?: string,
  onProgress?: (progress: number) => void,
  controller?: UploadController,
): Promise<Project> => {
  const formData = new FormData();
  formData.append('name', name);
  if (domain) formData.append('domain', domain);
  if (wpress) formData.append('wpress_file', wpress);
  if (localFilePath) formData.append('local_file_path', localFilePath);

  return uploadWithProgress<Project>(`${API_BASE}/projects/`, formData, onProgress, controller);
};

export const listWpressFiles = () =>
  apiFetch<{ path: string; name: string; size: number; created: number }[]>('/projects/files');

export const createProjectsBatch = async (
  wpressFiles: File[],
  onProgress?: (progress: number) => void,
  controller?: UploadController,
): Promise<{ status: string; message: string; created: Project[]; errors: Array<{ file: string; error: string }> }> => {
  const formData = new FormData();
  wpressFiles.forEach((file) => {
    formData.append('wpress_files', file);
  });

  return uploadWithProgress(`${API_BASE}/projects/batch`, formData, onProgress, controller);
};

export const createProjectsFromLibrary = async (
  files: string[],
): Promise<{ status: string; message: string; created: Project[]; errors: Array<{ file: string; error: string }> }> => {
  return apiFetch<{ status: string; message: string; created: Project[]; errors: Array<{ file: string; error: string }> }>('/projects/batch-library', {
    method: 'POST',
    body: JSON.stringify({ files }),
  });
};

export const deleteProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}`, {
    method: 'DELETE',
    timeout: 30000,
  });

export const deleteProjectsBatch = (ids: number[], cleanupDdev = true) =>
  apiFetch<{ status: string; message: string; count: number }>('/projects/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ project_ids: ids, cleanup_ddev: cleanupDdev }),
  });

export const stopProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/stop`, {
    method: 'POST',
  });

export const pauseProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/pause`, {
    method: 'POST',
  });

export const startProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/start`, {
    method: 'POST',
  });

export const restartProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/restart`, {
    method: 'POST',
    timeout: 180000,
  });

export const recreateProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/recreate`, {
    method: 'POST',
    timeout: 300000,
  });

export const resetProject = (id: number) =>
  apiFetch<{ status: string; message: string }>(`/projects/${id}/reset`, {
    method: 'POST',
    timeout: 120000,
  });

export const startWorkflow = (
  projectId: number,
  steps?: string[],
  selectedUpdates?: { update_core?: boolean; plugin_names?: string[]; theme_names?: string[] },
  importOnly?: boolean,
) =>
  apiFetch<Workflow>('/workflows/', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      steps,
      selected_updates: selectedUpdates,
      import_only: importOnly,
    }),
  });

export const startBatchWorkflows = (projectIds: number[], importOnly?: boolean) =>
  apiFetch<Workflow[]>('/workflows/batch', {
    method: 'POST',
    body: JSON.stringify({ project_ids: projectIds, import_only: importOnly }),
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

export interface QueueItem {
  id: number;
  project_id: number;
  project_name: string;
  domain: string;
  status: string;
  current_step?: string;
  position: number;
  created_at?: string;
  started_at?: string;
}

export const getWorkflowQueue = () =>
  apiFetch<{ queue: QueueItem[]; total_active: number; total_pending: number }>(
    '/workflows/queue',
  );

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

export const getVRTReport = (projectId: number) =>
  apiFetch<VRTReport>(`/projects/${projectId}/vrt`);

export const getVRTJsonReport = (projectId: number) =>
  apiFetch<Record<string, unknown>>(`/projects/${projectId}/vrt/report-json`);

export const setupSudoers = () =>
  apiFetch<{ status: string; message: string }>('/setup/sudoers', {
    method: 'POST',
  });

export const resetDDEVGlobal = () =>
  apiFetch<{ status: string; message: string }>('/system/ddev-reset', {
    method: 'POST',
    timeout: 60000,
  });

export const listContainers = () =>
  apiFetch<DDEVContainer[]>('/system/containers');

export const startContainer = (name: string) =>
  apiFetch<{ status: string; message: string }>(`/system/containers/${name}/start`, {
    method: 'POST',
    timeout: 180000,
  });

export const stopContainer = (name: string) =>
  apiFetch<{ status: string; message: string }>(`/system/containers/${name}/stop`, {
    method: 'POST',
    timeout: 60000,
  });

export const pauseContainer = (name: string) =>
  apiFetch<{ status: string; message: string }>(`/system/containers/${name}/pause`, {
    method: 'POST',
    timeout: 60000,
  });

export const restartContainer = (name: string) =>
  apiFetch<{ status: string; message: string }>(`/system/containers/${name}/restart`, {
    method: 'POST',
    timeout: 180000,
  });

export const deleteContainer = (name: string) =>
  apiFetch<{ status: string; message: string }>(`/system/containers/${name}`, {
    method: 'DELETE',
    timeout: 120000,
  });
