// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../stores/appStore';
import type { Project, LogMessage } from '../types';

describe('useAppStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useAppStore.setState({
      projects: [],
      currentProject: null,
      currentWorkflow: null,
      logs: [],
      progress: 0,
      currentStep: null,
      wsConnected: false,
      sidebarOpen: true,
      ddevLoading: false,
      workflowLoading: false,
    });
  });

  it('manages projects list and active project', () => {
    const dummyProject: Project = {
      id: 1,
      name: 'test-project',
      domain: 'test-project.ddev.site',
      status: 'ready',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    useAppStore.getState().setProjects([dummyProject]);
    expect(useAppStore.getState().projects).toHaveLength(1);

    useAppStore.getState().setCurrentProject(dummyProject);
    expect(useAppStore.getState().currentProject?.id).toBe(1);
  });

  it('adds log messages and updates state', () => {
    const dummyLog: LogMessage = {
      timestamp: '2026-01-01T00:00:00Z',
      level: 'info',
      step: 'test_step',
      message: 'Test log message',
    };

    useAppStore.getState().addLog(dummyLog);
    expect(useAppStore.getState().logs).toHaveLength(1);
    expect(useAppStore.getState().logs[0].message).toBe('Test log message');
  });

  it('toggles sidebar state', () => {
    expect(useAppStore.getState().sidebarOpen).toBe(true);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarOpen).toBe(false);
  });

  it('updates progress and current step', () => {
    useAppStore.getState().setProgress(75, 'vrt_check');
    expect(useAppStore.getState().progress).toBe(75);
    expect(useAppStore.getState().currentStep).toBe('vrt_check');
  });
});
