/**
 * Auto Maintenance - Types TypeScript.
 */

// ── Project ──────────────────────────────────────────────────────
export interface Project {
  id: number;
  name: string;
  domain: string;
  status: ProjectStatus;
  wpress_file: string | null;
  created_at: string;
  updated_at: string;
}

export type ProjectStatus =
  | 'created'
  | 'initializing'
  | 'wordpress_installed'
  | 'importing'
  | 'ready'
  | 'maintenance_in_progress'
  | 'maintenance_done'
  | 'error'
  | 'stopped'
  | 'deleting';

// ── Workflow ─────────────────────────────────────────────────────
export interface Workflow {
  id: number;
  project_id: number;
  status: WorkflowStatus;
  current_step: string | null;
  steps_completed: string[];
  steps_failed: string[];
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export type WorkflowStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type WorkflowStep =
  | 'ddev_create'
  | 'dns_setup'
  | 'wp_install'
  | 'plugin_install'
  | 'wpress_import'
  | 'screenshots_before'
  | 'updates_list'
  | 'updates_apply'
  | 'screenshots_after'
  | 'vrt_compare';

export const WORKFLOW_STEP_LABELS: Record<string, string> = {
  ddev_create: 'Création DDEV',
  dns_setup: 'Configuration DNS',
  wp_install: 'Installation WordPress',
  plugin_install: 'Installation Plugin AIO',
  wpress_import: 'Import .wpress',
  screenshots_before: 'Screenshots (avant)',
  updates_list: 'Liste des mises à jour',
  updates_apply: 'Application des mises à jour',
  screenshots_after: 'Screenshots (après)',
  vrt_compare: 'Comparaison visuelle',

};

// ── Updates ──────────────────────────────────────────────────────
export interface UpdateItem {
  name: string;
  type: 'core' | 'plugin' | 'theme';
  current_version: string;
  new_version: string;
  status: string;
}

export interface UpdateResult {
  name: string;
  type: string;
  success: boolean;
  message: string;
  old_version: string;
  new_version: string | null;
}

// ── VRT ──────────────────────────────────────────────────────────
export interface VRTReportItem {
  page_name: string;
  page_url: string;
  device: string;
  before_screenshot: string | null;
  after_screenshot: string | null;
  diff_image: string | null;
  diff_percentage: number | null;
  ssim_score: number | null;
  passed: boolean | null;
}

export interface VRTReport {
  project_id: number;
  total_pages: number;
  total_passed: number;
  total_failed: number;
  updates_total: number;
  updates_success: number;
  updates_failed: number;
  items: VRTReportItem[];
}

// ── WebSocket ────────────────────────────────────────────────────
export interface LogMessage {
  type: 'log' | 'progress' | 'updates_available' | 'updates_results' | 'vrt_report';
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'success' | 'debug';
  step: string | null;
  message: string;
  details: Record<string, unknown> | null;
  progress: number | null;
  project_id: number;
  workflow_id: number;
}

export interface ProgressMessage {
  type: 'progress';
  timestamp: string;
  project_id: number;
  workflow_id: number;
  step: string;
  progress: number;
  message: string;
}

// ── API ──────────────────────────────────────────────────────────
export interface ApiError {
  detail: string;
}

export interface HealthCheck {
  status: string;
  version: string;
  checks: {
    ddev_installed: boolean;
    docker_running: boolean;
  };
}

export interface DDEVContainer {
  name: string;
  status: string;
  php_version: string;
  db_type: string;
  db_version: string;
  url: string;
  approot: string;
  storage_bytes: number;
  type: string;
  router: string;
}
