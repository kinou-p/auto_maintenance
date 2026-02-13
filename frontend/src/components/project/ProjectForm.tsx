/**
 * ProjectForm - Formulaire de création de projet.
 */

import { useState, useRef } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { createProject, createProjectsBatch } from '@/lib/api';
import { useAppStore } from '@/stores/appStore';
import { Upload, FolderPlus, Loader2, Files } from 'lucide-react';

export function ProjectForm() {
  const [mode, setMode] = useState<'single' | 'batch'>('single');
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [wpress, setWpress] = useState<File | null>(null);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { setCurrentProject, setProjects, projects } = useAppStore();

  const handleNameChange = (value: string) => {
    setName(value);
    if (!domain || domain === `${name}.ddev.site`) {
      setDomain(`${value}.ddev.site`);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (mode === 'batch') {
      // Mode batch : accepter plusieurs fichiers
      const validFiles = Array.from(files).filter(f => f.name.endsWith('.wpress'));
      if (validFiles.length !== files.length) {
        setError('Tous les fichiers doivent être au format .wpress');
        return;
      }
      setBatchFiles(validFiles);
      setError('');
    } else {
      // Mode simple : un seul fichier
      const file = files[0];
      if (!file) return;
      
      if (!file.name.endsWith('.wpress')) {
        setError('Le fichier doit être au format .wpress');
        return;
      }
      setWpress(file);
      setError('');

      // Auto-détection du nom depuis le fichier
      if (!name) {
        const autoName = file.name
          .replace('.wpress', '')
          .replace(/[^a-zA-Z0-9_-]/g, '-')
          .toLowerCase();
        handleNameChange(autoName);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (mode === 'batch') {
      // Mode batch
      if (batchFiles.length === 0) {
        setError('Aucun fichier sélectionné.');
        return;
      }

      setLoading(true);
      try {
        const result = await createProjectsBatch(batchFiles);
        
        // Ajouter les projets créés à la liste
        if (result.created && result.created.length > 0) {
          setProjects([...result.created, ...projects]);
          if (result.created[0]) {
            setCurrentProject(result.created[0]);
          }
        }

        // Afficher les erreurs s'il y en a
        if (result.errors && result.errors.length > 0) {
          const errorMsg = result.errors.map(e => `${e.file}: ${e.error}`).join('\n');
          setError(`${result.message}\n\nErreurs:\n${errorMsg}`);
        }

        // Reset form si succès complet
        if (!result.errors || result.errors.length === 0) {
          setBatchFiles([]);
          if (fileInputRef.current) fileInputRef.current.value = '';
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur lors de la création batch');
      } finally {
        setLoading(false);
      }
    } else {
      // Mode simple
      if (!name.trim()) {
        setError('Le nom du projet est requis.');
        return;
      }

      if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        setError('Le nom ne peut contenir que des lettres, chiffres, tirets et underscores.');
        return;
      }

      setLoading(true);
      try {
        const project = await createProject(
          name.trim(),
          domain.trim() || undefined,
          wpress || undefined,
        );

        setCurrentProject(project);
        setProjects([project, ...projects]);

        // Reset form
        setName('');
        setDomain('');
        setWpress(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur lors de la création');
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Card className="w-full max-w-lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <FolderPlus className="h-5 w-5" />
          Nouveau Projet
        </CardTitle>
        <div className="flex gap-2 mt-3">
          <Button
            type="button"
            variant={mode === 'single' ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              setMode('single');
              setBatchFiles([]);
              setError('');
            }}
          >
            Simple
          </Button>
          <Button
            type="button"
            variant={mode === 'batch' ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              setMode('batch');
              setWpress(null);
              setName('');
              setDomain('');
              setError('');
            }}
          >
            <Files className="h-4 w-4 mr-1" />
            Batch
          </Button>
        </div>
        <CardDescription>
          {mode === 'single' 
            ? 'Créez un nouveau projet de maintenance WordPress'
            : 'Créez plusieurs projets en une fois à partir de fichiers .wpress'}
        </CardDescription>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {mode === 'single' ? (
            <>
              {/* Nom du projet */}
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="project-name">
                  Nom du projet
                </label>
                <Input
                  id="project-name"
                  placeholder="mon-site-wordpress"
                  value={name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  disabled={loading}
                />
              </div>

              {/* Domaine */}
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="project-domain">
                  Domaine local
                </label>
                <Input
                  id="project-domain"
                  placeholder="monsite.ddev.site"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  disabled={loading}
                />
              </div>

              {/* Upload .wpress */}
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Fichier de sauvegarde (.wpress)
                </label>
                <div
                  className="border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".wpress"
                    onChange={handleFileChange}
                    className="hidden"
                    disabled={loading}
                  />
                  {wpress ? (
                    <div className="space-y-1">
                      <Upload className="h-8 w-8 mx-auto text-primary" />
                      <p className="text-sm font-medium">{wpress.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(wpress.size / 1024 / 1024).toFixed(1)} Mo
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">
                        Cliquez ou glissez votre fichier .wpress ici
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Upload multiple .wpress */}
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Fichiers de sauvegarde (.wpress)
                </label>
                <div
                  className="border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".wpress"
                    multiple
                    onChange={handleFileChange}
                    className="hidden"
                    disabled={loading}
                  />
                  {batchFiles.length > 0 ? (
                    <div className="space-y-2">
                      <Files className="h-8 w-8 mx-auto text-primary" />
                      <p className="text-sm font-medium">{batchFiles.length} fichier(s) sélectionné(s)</p>
                      <div className="max-h-32 overflow-y-auto text-xs text-muted-foreground space-y-1">
                        {batchFiles.map((f, idx) => (
                          <div key={idx}>
                            {f.name} ({(f.size / 1024 / 1024).toFixed(1)} Mo)
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Files className="h-8 w-8 mx-auto text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">
                        Cliquez ou glissez vos fichiers .wpress ici
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Les noms de projet seront générés automatiquement
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Erreur */}
          {error && (
            <p className="text-sm text-destructive whitespace-pre-line">{error}</p>
          )}
        </CardContent>

        <CardFooter>
          <Button 
            type="submit" 
            disabled={
              loading || 
              (mode === 'single' && !name.trim()) ||
              (mode === 'batch' && batchFiles.length === 0)
            } 
            className="w-full"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {mode === 'batch' ? 'Création des projets...' : 'Création en cours...'}
              </>
            ) : (
              mode === 'batch' ? `Créer ${batchFiles.length} projet(s)` : 'Créer le projet'
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
