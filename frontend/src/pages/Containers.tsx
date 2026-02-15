import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Box,
    RefreshCcw,
    Play,
    Square,
    RotateCcw,
    Trash2,
    ExternalLink,
    HardDrive,
    Cpu,
    Database,
    Search,
    ArrowLeft,
    Loader2,
    AlertTriangle,
    ChevronRight
} from 'lucide-react';
import {
    listContainers,
    startContainer,
    stopContainer,
    restartContainer,
    deleteContainer,
} from '@/lib/api';
import { DDEVContainer } from '@/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

export const Containers: React.FC = () => {
    const navigate = useNavigate();
    const [containers, setContainers] = useState<DDEVContainer[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    const fetchContainers = async () => {
        setLoading(true);
        try {
            const data = await listContainers();
            setContainers(data);
            setError(null);
        } catch (err: any) {
            console.error('Fetch containers error:', err);
            setError('Impossible de récupérer la liste des containers DDEV.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchContainers();
    }, []);

    const handleAction = async (name: string, action: 'start' | 'stop' | 'restart' | 'delete') => {
        if (action === 'delete' && !confirm(`Voulez-vous vraiment supprimer le projet "${name}" ?`)) return;

        setActionLoading(`${name}-${action}`);
        try {
            if (action === 'start') await startContainer(name);
            else if (action === 'stop') await stopContainer(name);
            else if (action === 'restart') await restartContainer(name);
            else if (action === 'delete') await deleteContainer(name);

            await fetchContainers();
        } catch (err: any) {
            alert(`Erreur lors de l'action ${action} : ${err.message}`);
        } finally {
            setActionLoading(null);
        }
    };

    const filteredContainers = containers.filter(c =>
        c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.url?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    return (
        <div className="min-h-screen bg-background flex flex-col">
            {/* Header */}
            <header className="border-b border-border px-8 py-6 flex items-center justify-between bg-card/30 backdrop-blur-sm sticky top-0 z-10">
                <div className="flex items-center gap-6">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => navigate('/')}
                        className="rounded-full hover:bg-muted"
                    >
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">DDEV Container Manager</h1>
                        <p className="text-sm text-muted-foreground mt-1">Gérez tous les environnements DDEV de votre système</p>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className="relative w-80">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Rechercher un container..."
                            className="pl-10 bg-muted/50 border-none focus-visible:ring-1 focus-visible:ring-primary/20"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    <Button variant="outline" size="icon" onClick={fetchContainers} disabled={loading}>
                        <RefreshCcw className={cn("h-4 w-4", loading && "animate-spin")} />
                    </Button>
                </div>
            </header>

            <main className="flex-1 p-8 max-w-7xl mx-auto w-full">
                {error && (
                    <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-xl flex items-center gap-3 mb-6">
                        <AlertTriangle className="h-5 w-5" />
                        <p>{error}</p>
                    </div>
                )}

                {loading && containers.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 gap-4">
                        <Loader2 className="h-10 w-10 text-primary animate-spin" />
                        <p className="text-muted-foreground animate-pulse">Scan des containers DDEV...</p>
                    </div>
                ) : filteredContainers.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 gap-4 text-center border-2 border-dashed border-muted rounded-2xl">
                        <Box className="h-12 w-12 text-muted-foreground/30" />
                        <div>
                            <p className="text-lg font-medium">Aucun container trouvé</p>
                            <p className="text-sm text-muted-foreground mt-1">Essayez de modifier votre recherche ou de rafraîchir la liste.</p>
                        </div>
                        <Button variant="outline" onClick={fetchContainers}>Rafraîchir</Button>
                    </div>
                ) : (
                    <div className="grid gap-4">
                        {filteredContainers.map((container) => (
                            <div key={container.name} className="group bg-card hover:bg-card/80 border border-border rounded-xl p-5 transition-all hover:shadow-lg hover:-translate-y-0.5">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-5">
                                        <div className={cn(
                                            "h-12 w-12 rounded-xl flex items-center justify-center shrink-0",
                                            container.status === 'running' ? "bg-green-100 text-green-600" : "bg-muted text-muted-foreground"
                                        )}>
                                            <Box className="h-6 w-6" />
                                        </div>

                                        <div>
                                            <div className="flex items-center gap-3">
                                                <h3 className="font-bold text-lg">{container.name}</h3>
                                                <Badge variant={container.status === 'running' ? 'default' : 'secondary'} className={cn(
                                                    "capitalize",
                                                    container.status === 'running' && "bg-green-500 hover:bg-green-600"
                                                )}>
                                                    {container.status}
                                                </Badge>
                                            </div>
                                            <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                                                <div className="flex items-center gap-1.5">
                                                    <Cpu className="h-3.5 w-3.5" />
                                                    PHP {container.php_version}
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <Database className="h-3.5 w-3.5" />
                                                    {container.db_type} {container.db_version}
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <HardDrive className="h-3.5 w-3.5" />
                                                    {formatSize(container.storage_bytes)}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-2">
                                        {container.url && (
                                            <Button variant="ghost" size="sm" asChild className="text-primary hover:text-primary hover:bg-primary/10">
                                                <a href={container.url} target="_blank" rel="noopener noreferrer">
                                                    <ExternalLink className="h-4 w-4 mr-2" />
                                                    Ouvrir le site
                                                </a>
                                            </Button>
                                        )}

                                        <div className="h-8 w-px bg-border mx-2" />

                                        <div className="flex items-center gap-1.5">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => handleAction(container.name, 'start')}
                                                disabled={!!actionLoading || container.status === 'running'}
                                                className="h-9 gap-2 hover:bg-green-50 hover:text-green-600 hover:border-green-200"
                                            >
                                                {actionLoading === `${container.name}-start` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                                                Start
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => handleAction(container.name, 'stop')}
                                                disabled={!!actionLoading || container.status !== 'running'}
                                                className="h-9 gap-2 hover:bg-amber-50 hover:text-amber-600 hover:border-amber-200"
                                            >
                                                {actionLoading === `${container.name}-stop` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                                                Stop
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => handleAction(container.name, 'restart')}
                                                disabled={!!actionLoading}
                                                className="h-9 gap-2 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-200"
                                            >
                                                {actionLoading === `${container.name}-restart` ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                                                Restart
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => handleAction(container.name, 'delete')}
                                                disabled={!!actionLoading}
                                                className="h-9 gap-2 text-destructive hover:bg-destructive/10"
                                            >
                                                {actionLoading === `${container.name}-delete` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                                                Delete
                                            </Button>
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-4 pt-4 border-t border-border flex items-center justify-between text-[10px] text-muted-foreground/60 uppercase tracking-widest">
                                    <div className="flex items-center gap-4">
                                        <span>Approot: {container.approot}</span>
                                        <span className="h-1 w-1 rounded-full bg-border" />
                                        <span>Router: {container.router || 'traefik'}</span>
                                    </div>
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        Voir détails <ChevronRight className="h-3 w-3" />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};
