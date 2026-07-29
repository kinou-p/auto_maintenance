import React, { useState, useEffect } from 'react';
import { getSystemSettings, updateSystemSettings } from '@/lib/api';
import type { SystemSettings } from '@/types';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Toaster, useToast } from '@/components/ui/Toaster';
import { UserMenu } from '@/components/ui/UserMenu';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { Link } from 'react-router-dom';
import {
  Sliders,
  Eye,
  Cpu,
  Globe,
  Save,
  RotateCcw,
  Loader2,
  CheckCircle2,
  Wrench,
  Layers,
  ShieldCheck,
  LayoutGrid,
} from 'lucide-react';

export const Settings: React.FC = () => {
  const { toasts, toast, dismiss } = useToast();
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = await getSystemSettings();
      setSettings(data);
    } catch (err: any) {
      toast({ title: 'Erreur', description: err.message || 'Erreur lors de la récupération des paramètres', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;

    setSaving(true);
    try {
      const updated = await updateSystemSettings(settings);
      setSettings(updated);
      toast({ title: 'Succès', description: 'Paramètres système enregistrés avec succès !', variant: 'success' });
    } catch (err: any) {
      toast({ title: 'Échec', description: err.message || 'Échec de la sauvegarde des paramètres', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleDeviceToggle = (device: string) => {
    if (!settings) return;
    const current = settings.screenshot_enabled_devices.split(',').map((d) => d.trim()).filter(Boolean);
    let next: string[];
    if (current.includes(device)) {
      if (current.length === 1) {
        toast({ title: 'Attention', description: 'Au moins un appareil doit rester activé.', variant: 'warning' });
        return;
      }
      next = current.filter((d) => d !== device);
    } else {
      next = [...current, device];
    }
    setSettings({ ...settings, screenshot_enabled_devices: next.join(',') });
  };

  if (loading || !settings) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
        <span className="text-sm font-medium">Chargement des paramètres...</span>
      </div>
    );
  }

  const ssimPercent = Math.round(settings.vrt_min_ssim_score * 100);
  const activeDevices = settings.screenshot_enabled_devices.split(',').map((d) => d.trim());

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Toaster toasts={toasts} dismiss={dismiss} />

      {/* Header Bar */}
      <header className="sticky top-0 z-40 bg-slate-900/80 backdrop-blur-xl border-b border-slate-800 px-6 py-4 flex items-center justify-between shadow-xl">
        <div className="flex items-center space-x-4">
          <Link
            to="/"
            className="flex items-center space-x-3 text-slate-300 hover:text-white transition-colors"
          >
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <Wrench className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-lg text-slate-100 block leading-tight">Auto Maintenance</span>
              <span className="text-xs text-slate-400">Plateforme de maintenance WordPress</span>
            </div>
          </Link>
        </div>

        <nav className="flex items-center space-x-6">
          <Link
            to="/"
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-2"
          >
            <LayoutGrid className="w-4 h-4" />
            Dashboard
          </Link>
          <Link
            to="/containers"
            className="text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-2"
          >
            <Layers className="w-4 h-4" />
            Conteneurs
          </Link>
          <span className="text-sm font-medium text-emerald-400 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <Sliders className="w-4 h-4" />
            Paramètres
          </span>

          <div className="h-5 w-px bg-slate-800" />
          <ThemeToggle />
          <UserMenu />
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-6 md:p-8 space-y-8">
        {/* Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-100 tracking-tight flex items-center gap-3">
              <Sliders className="w-8 h-8 text-emerald-400" />
              Paramètres du Système
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Personnalisez les seuils de comparaison visuelle (VRT), les paramètres de capture et la gestion des workflows.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <Button
              variant="secondary"
              onClick={fetchSettings}
              disabled={saving}
              className="flex items-center gap-2 text-xs"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Réinitialiser
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-2 text-sm px-5 py-2.5 shadow-lg shadow-emerald-600/20"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Sauvegarder les modifications
            </Button>
          </div>
        </div>

        <form onSubmit={handleSave} className="space-y-8">
          {/* Section 1: Visual Regression Testing (VRT) */}
          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl overflow-hidden">
            <CardHeader className="border-b border-slate-800/60 bg-slate-900/80 px-6 py-4">
              <CardTitle className="text-lg font-bold text-slate-100 flex items-center gap-2.5">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                Comparaison Visuelle VRT (Structural Similarity)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
              {/* Seuil SSIM slider */}
              <div className="space-y-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-semibold text-slate-200 block">
                      Taux SSIM Minimal pour Validation (PASS)
                    </label>
                    <span className="text-xs text-slate-400">
                      Score de similarité structurelle requis pour valider le test avant/après.
                    </span>
                  </div>
                  <span className="text-lg font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 rounded-lg">
                    {settings.vrt_min_ssim_score.toFixed(2)} ({ssimPercent}%)
                  </span>
                </div>

                <input
                  type="range"
                  min="0.50"
                  max="1.00"
                  step="0.01"
                  value={settings.vrt_min_ssim_score}
                  onChange={(e) =>
                    setSettings({ ...settings, vrt_min_ssim_score: parseFloat(e.target.value) })
                  }
                  className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />

                <div className="flex justify-between text-xs text-slate-500 font-mono">
                  <span>0.50 (Permissif)</span>
                  <span>0.85 (Modéré)</span>
                  <span>0.95 (Recommandé)</span>
                  <span>1.00 (Strict)</span>
                </div>
              </div>

              {/* Seuil max diff pixel */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Pourcentage Max de Différence Pixels (%)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.1"
                      min="0.0"
                      max="100.0"
                      value={settings.vrt_max_diff_percentage}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          vrt_max_diff_percentage: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-emerald-500 font-mono"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 font-semibold">%</span>
                  </div>
                  <span className="text-xs text-slate-500">
                    Seuil maximal toléré de divergence graphique globale.
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Tolérance Anti-Aliasing (pixels)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="20"
                    value={settings.vrt_anti_aliasing_tolerance}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        vrt_anti_aliasing_tolerance: parseInt(e.target.value) || 0,
                      })
                    }
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-emerald-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Tolérance aux variations de lissage de police et de rendus graphiques.
                  </span>
                </div>
              </div>

              {/* Toggle masquage dynamique */}
              <div className="flex items-center justify-between bg-slate-950/40 border border-slate-800/60 rounded-xl p-4">
                <div>
                  <span className="text-sm font-semibold text-slate-200 block">
                    Masquage automatique des éléments dynamiques (DOM Snapshot)
                  </span>
                  <span className="text-xs text-slate-400">
                    Masque les bannières de cookies, horloges et widgets animés lors de la capture.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setSettings({ ...settings, vrt_enable_dom_snapshot: !settings.vrt_enable_dom_snapshot })
                  }
                  className={`w-12 h-6 rounded-full transition-colors relative focus:outline-none ${
                    settings.vrt_enable_dom_snapshot ? 'bg-emerald-500' : 'bg-slate-800'
                  }`}
                >
                  <span
                    className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-transform ${
                      settings.vrt_enable_dom_snapshot ? 'left-6.5' : 'left-0.5'
                    }`}
                  />
                </button>
              </div>
            </CardContent>
          </Card>

          {/* Section 2: Screenshot Captures & Devices */}
          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl overflow-hidden">
            <CardHeader className="border-b border-slate-800/60 bg-slate-900/80 px-6 py-4">
              <CardTitle className="text-lg font-bold text-slate-100 flex items-center gap-2.5">
                <Eye className="w-5 h-5 text-cyan-400" />
                Captures & Appareils Actifs
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
              {/* Devices selection */}
              <div>
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-3">
                  Appareils de Capture Déployés
                </label>
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { id: 'desktop', label: 'Desktop (1920x1080)' },
                    { id: 'tablet', label: 'Tablette (768x1024)' },
                    { id: 'mobile', label: 'Mobile (375x812)' },
                  ].map((dev) => {
                    const isActive = activeDevices.includes(dev.id);
                    return (
                      <button
                        type="button"
                        key={dev.id}
                        onClick={() => handleDeviceToggle(dev.id)}
                        className={`p-3.5 rounded-xl border text-sm font-medium transition-all flex items-center justify-between cursor-pointer ${
                          isActive
                            ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-300 shadow-md shadow-cyan-500/10'
                            : 'bg-slate-950/40 border-slate-800 text-slate-500 hover:border-slate-700'
                        }`}
                      >
                        <span>{dev.label}</span>
                        {isActive && <CheckCircle2 className="w-4 h-4 text-cyan-400" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Stabilize delay & Timeout */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Délai de stabilisation (ms)
                  </label>
                  <input
                    type="number"
                    step="100"
                    min="0"
                    max="10000"
                    value={settings.screenshot_stabilize_delay}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        screenshot_stabilize_delay: parseInt(e.target.value) || 0,
                      })
                    }
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-cyan-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Pause d'attente avant la prise de vue pour stabilisation visuelle.
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Timeout de chargement de page (ms)
                  </label>
                  <input
                    type="number"
                    step="1000"
                    min="1000"
                    max="60000"
                    value={settings.screenshot_load_timeout}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        screenshot_load_timeout: parseInt(e.target.value) || 0,
                      })
                    }
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-cyan-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Temps maximal accordé au chargement du DOM et des ressources.
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 3: Performance & Workflows */}
          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl overflow-hidden">
            <CardHeader className="border-b border-slate-800/60 bg-slate-900/80 px-6 py-4">
              <CardTitle className="text-lg font-bold text-slate-100 flex items-center gap-2.5">
                <Cpu className="w-5 h-5 text-indigo-400" />
                Workflows & Execution Engine
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Workflows Simultanés Max
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={settings.max_concurrent_workflows}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        max_concurrent_workflows: parseInt(e.target.value) || 1,
                      })
                    }
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-indigo-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Nombre maximal de sites WordPress traités simultanément en file d'attente.
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Timeout Playwright Global (ms)
                  </label>
                  <input
                    type="number"
                    step="5000"
                    min="5000"
                    max="300000"
                    value={settings.playwright_timeout}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        playwright_timeout: parseInt(e.target.value) || 60000,
                      })
                    }
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-indigo-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Délai d'expiration de l'instance de navigateur Playwright.
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section 4: WordPress Defaults */}
          <Card className="bg-slate-900/60 border-slate-800 backdrop-blur-xl shadow-xl overflow-hidden">
            <CardHeader className="border-b border-slate-800/60 bg-slate-900/80 px-6 py-4">
              <CardTitle className="text-lg font-bold text-slate-100 flex items-center gap-2.5">
                <Globe className="w-5 h-5 text-amber-400" />
                Configurations WordPress par Défaut
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Langue Locale WordPress
                  </label>
                  <input
                    type="text"
                    value={settings.wp_locale}
                    onChange={(e) => setSettings({ ...settings, wp_locale: e.target.value })}
                    placeholder="fr_FR"
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-amber-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Ex: fr_FR, en_US.
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                    Email Administrateur WordPress par Défaut
                  </label>
                  <input
                    type="email"
                    value={settings.wp_admin_email}
                    onChange={(e) => setSettings({ ...settings, wp_admin_email: e.target.value })}
                    placeholder="admin@exemple.com"
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-amber-500 font-mono"
                  />
                  <span className="text-xs text-slate-500">
                    Email par défaut attribué lors de l'installation WordPress.
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Bottom Action Bar */}
          <div className="flex items-center justify-end space-x-4 pt-4">
            <Button
              type="submit"
              disabled={saving}
              className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-medium px-8 py-3 rounded-xl shadow-lg shadow-emerald-500/25 transition-all text-sm"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  Sauvegarde en cours...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  Enregistrer les Paramètres
                </>
              )}
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
};
