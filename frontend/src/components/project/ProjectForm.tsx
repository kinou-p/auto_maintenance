/**
 * ProjectForm - Formulaire de création de projet (Redesigned).
 */

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/Card';
import { createProject, createProjectsBatch, listWpressFiles, createProjectsFromLibrary } from '@/lib/api';
import { useAppStore } from '@/stores/appStore';
import { Upload, FolderPlus, Loader2, Files } from 'lucide-react';

export function ProjectForm() {
  const [activeTab, setActiveTab] = useState<'new' | 'library'>('new');

  // States pour "Nouveau" (Upload)
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);

  // States pour "Bibliothèque"
  const [libraryFiles, setLibraryFiles] = useState<{ path: string; name: string; size: number; created: number }[]>([]);
  const [selectedLibraryFiles, setSelectedLibraryFiles] = useState<string[]>([]);
  const [librarySearch, setLibrarySearch] = useState('');

  // States globaux
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { setCurrentProject, setProjects, projects } = useAppStore();

  // Charger la librairie au changement d'onglet
  useEffect(() => {
    if (activeTab === 'library') {
      fetchLibraryFiles();
    }
  }, [activeTab]);

  const fetchLibraryFiles = async () => {
    setLoading(true);
    try {
      const files = await listWpressFiles();
      setLibraryFiles(files);
    } catch (err) {
      console.error('Error fetching library files:', err);
      setError('Impossible de charger les fichiers de la bibliothèque.');
    } finally {
      setLoading(false);
    }
  };

  const handleNameChange = (value: string) => {
    setName(value);
    if (!domain || domain === `${name}.ddev.site`) {
      setDomain(`${value}.ddev.site`);
    }
  };

  const handleUploadFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newFiles = Array.from(files).filter(f => f.name.endsWith('.wpress'));
    if (newFiles.length !== files.length) {
      setError('Certains fichiers ont été ignorés car ils ne sont pas au format .wpress');
    } else {
      setError('');
    }

    setUploadFiles(newFiles);

    // Auto-fill name si un seul fichier
    if (newFiles.length === 1 && !name) {
      const autoName = newFiles[0].name
        .replace('.wpress', '')
        .replace(/[^a-zA-Z0-9_-]/g, '-')
        .toLowerCase();
      handleNameChange(autoName);
    }
  };

  const handleLibrarySelection = (path: string) => {
    setSelectedLibraryFiles(prev => {
      if (prev.includes(path)) {
        return prev.filter(p => p !== path);
      } else {
        return [...prev, path];
      }
    });
  };

  const handleSelectAllLibrary = () => {
    if (selectedLibraryFiles.length === filteredLibraryFiles.length) {
      setSelectedLibraryFiles([]);
    } else {
      setSelectedLibraryFiles(filteredLibraryFiles.map(f => f.path));
    }
  };

  const filteredLibraryFiles = libraryFiles.filter(f =>
    f.name.toLowerCase().includes(librarySearch.toLowerCase())
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (activeTab === 'new') {
        // SCÉNARIO 1 : Upload
        if (uploadFiles.length === 0) {
          throw new Error("Veuillez sélectionner au moins un fichier .wpress");
        }

        if (uploadFiles.length === 1) {
          // Création simple
          if (!name.trim()) throw new Error("Le nom du projet est requis.");
          const project = await createProject(
            name.trim(),
            domain.trim() || undefined,
            uploadFiles[0]
          );
          setCurrentProject(project);
          setProjects([project, ...projects]);
        } else {
          // Création Batch (Upload)
          const result = await createProjectsBatch(uploadFiles);
          if (result.created.length > 0) {
            setProjects([...result.created, ...projects]);
            setCurrentProject(result.created[0]);
          }
          if (result.errors.length > 0) {
            const errorMsg = result.errors.map(e => `${e.file}: ${e.error}`).join('\n');
            throw new Error(`${result.message}\n\nErreurs:\n${errorMsg}`);
          }
        }

        // Reset
        setUploadFiles([]);
        setName('');
        setDomain('');
        if (fileInputRef.current) fileInputRef.current.value = '';

      } else {
        // SCÉNARIO 2 : Librairie
        if (selectedLibraryFiles.length === 0) {
          throw new Error("Veuillez sélectionner au moins un fichier dans la bibliothèque.");
        }

        const result = await createProjectsFromLibrary(selectedLibraryFiles);
        if (result.created.length > 0) {
          setProjects([...result.created, ...projects]);
          setCurrentProject(result.created[0]);
        }
        if (result.errors.length > 0) {
          const errorMsg = result.errors.map(e => `${e.file}: ${e.error}`).join('\n');
          throw new Error(`${result.message}\n\nErreurs:\n${errorMsg}`);
        }

        setSelectedLibraryFiles([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Une erreur est survenue');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full max-w-lg border-none shadow-lg bg-card/50 backdrop-blur-sm">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
          <FolderPlus className="h-6 w-6 text-primary" />
          Nouveau Projet
        </CardTitle>
        <CardDescription>
          Ajoutez des projets WordPress à votre environnement.
        </CardDescription>

        {/* Custom Tabs */}
        <div className="flex p-1 mt-4 bg-muted/50 rounded-lg">
          <button
            type="button"
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'new' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('new')}
          >
            Importer (.wpress)
          </button>
          <button
            type="button"
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${activeTab === 'library' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('library')}
          >
            Bibliothèque
          </button>
        </div>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="min-h-[300px] space-y-4">

          {/* ONGLET 1 : NOUVEAU (UPLOAD) */}
          {activeTab === 'new' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${uploadFiles.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-border hover:border-primary/30 hover:bg-accent/50'}`}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".wpress"
                  multiple
                  onChange={handleUploadFilesChange}
                  className="hidden"
                  disabled={loading}
                />

                {uploadFiles.length > 0 ? (
                  <div className="space-y-2">
                    <Files className="h-10 w-10 mx-auto text-primary" />
                    <div className="text-sm font-medium">
                      {uploadFiles.length} fichier(s) sélectionné(s)
                    </div>
                    <p className="text-xs text-muted-foreground">Cliquez pour changer</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="h-10 w-10 mx-auto text-muted-foreground/50" />
                    <p className="text-sm font-medium text-foreground">
                      Cliquez ou glissez vos fichiers .wpress
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Jusqu'à 500Mo par fichier
                    </p>
                  </div>
                )}
              </div>

              {/* Formulaire si 1 seul fichier */}
              {uploadFiles.length === 1 && (
                <div className="space-y-3 pt-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Nom du projet</label>
                    <Input
                      value={name}
                      onChange={(e) => handleNameChange(e.target.value)}
                      placeholder="mon-super-projet"
                      className="bg-background/50"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Domaine local</label>
                    <Input
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="projet.ddev.site"
                      className="bg-background/50"
                    />
                  </div>
                </div>
              )}

              {/* Liste si plusieurs fichiers */}
              {uploadFiles.length > 1 && (
                <div className="bg-accent/30 rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                  {uploadFiles.map((f, i) => (
                    <div key={i} className="flex justify-between text-xs items-center">
                      <span className="truncate max-w-[200px]">{f.name}</span>
                      <span className="text-muted-foreground">{(f.size / 1024 / 1024).toFixed(1)} Mo</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ONGLET 2 : BIBLIOTHEQUE */}
          {activeTab === 'library' && (
            <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300 h-full flex flex-col">
              {/* Recherche et Filtres */}
              <div className="flex gap-2">
                <Input
                  placeholder="Rechercher..."
                  value={librarySearch}
                  onChange={(e) => setLibrarySearch(e.target.value)}
                  className="h-9 text-sm"
                />
              </div>

              {/* Liste des fichiers */}
              <div className="border rounded-md flex-1 overflow-hidden flex flex-col max-h-[250px] min-h-[200px]">
                <div className="bg-muted/30 p-2 text-xs font-medium text-muted-foreground flex justify-between items-center border-b">
                  <span>{filteredLibraryFiles.length} fichiers trouvés</span>
                  <button
                    type="button"
                    onClick={handleSelectAllLibrary}
                    className="text-primary hover:underline"
                  >
                    {selectedLibraryFiles.length === filteredLibraryFiles.length ? 'Tout désélectionner' : 'Tout sélectionner'}
                  </button>
                </div>

                <div className="overflow-y-auto p-1 space-y-1 flex-1">
                  {filteredLibraryFiles.map((file) => {
                    const isSelected = selectedLibraryFiles.includes(file.path);
                    return (
                      <div
                        key={file.path}
                        onClick={() => handleLibrarySelection(file.path)}
                        className={`flex items-center gap-3 p-2 rounded-md cursor-pointer text-sm transition-colors ${isSelected ? 'bg-primary/10 hover:bg-primary/15' : 'hover:bg-accent'}`}
                      >
                        <div className={`h-4 w-4 rounded border flex items-center justify-center ${isSelected ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground'}`}>
                          {isSelected && <div className="h-2 w-2 bg-current rounded-sm" />}
                        </div>
                        <div className="flex-1 truncate">
                          <div className="font-medium truncate">{file.name}</div>
                          <div className="text-xs text-muted-foreground flex justify-between mt-0.5">
                            <span>{(file.size / 1024 / 1024).toFixed(1)} Mo</span>
                            <span>{new Date(file.created * 1000).toLocaleDateString()}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {filteredLibraryFiles.length === 0 && (
                    <div className="p-8 text-center text-muted-foreground text-sm">
                      Aucun fichier trouvé.
                    </div>
                  )}
                </div>
              </div>

              {selectedLibraryFiles.length > 0 && (
                <div className="text-xs text-right text-muted-foreground">
                  {selectedLibraryFiles.length} fichier(s) sélectionné(s)
                </div>
              )}
            </div>
          )}

          {/* Erreur globale */}
          {error && (
            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md whitespace-pre-line animate-in fade-in zoom-in-95 duration-200">
              {error}
            </div>
          )}

        </CardContent>

        <CardFooter className="pt-2">
          <Button
            type="submit"
            disabled={
              loading ||
              (activeTab === 'new' && uploadFiles.length === 0) ||
              (activeTab === 'library' && selectedLibraryFiles.length === 0)
            }
            className="w-full shadow-md font-semibold"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Traitement en cours...
              </>
            ) : (
              activeTab === 'new'
                ? (uploadFiles.length > 1 ? `Importer ${uploadFiles.length} projets` : 'Créer le projet')
                : `Créer ${selectedLibraryFiles.length} projet(s)`
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
