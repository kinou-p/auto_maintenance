import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ImageComparer } from '@/components/vrt/ImageComparer';
import type { VRTReport } from '@/types';
import {
  ImageIcon,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ImageOff,
  RefreshCw,
} from 'lucide-react';

interface VRTReportViewerProps {
  vrtReport: VRTReport | null;
  vrtLoading: boolean;
  globalViewMode: 'slider' | 'side-by-side' | 'diff';
  setGlobalViewMode: (mode: 'slider' | 'side-by-side' | 'diff') => void;
  collapsedItems: Set<number>;
  setCollapsedItems: React.Dispatch<React.SetStateAction<Set<number>>>;
  hasCurrentProject: boolean;
}

export function VRTReportViewer({
  vrtReport,
  vrtLoading,
  globalViewMode,
  setGlobalViewMode,
  collapsedItems,
  setCollapsedItems,
  hasCurrentProject,
}: VRTReportViewerProps) {
  if (vrtLoading) {
    return (
      <Card>
        <CardContent className="pt-6 flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">Chargement du rapport VRT...</span>
        </CardContent>
      </Card>
    );
  }

  if (vrtReport && vrtReport.items.length > 0) {
    return (
      <>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ImageIcon className="h-5 w-5" />
              Résumé
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-1">
                <div className="text-2xl font-bold">{vrtReport.updates_total || 0}</div>
                <div className="text-xs text-muted-foreground">Mises à jour</div>
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold text-green-500 flex items-center gap-1">
                  <CheckCircle2 className="h-5 w-5" />
                  {vrtReport.updates_success || 0}
                </div>
                <div className="text-xs text-muted-foreground">MàJ Réussies</div>
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold">{vrtReport.total_pages}</div>
                <div className="text-xs text-muted-foreground">Pages testées</div>
              </div>
              <div className="space-y-1">
                <div className="text-2xl font-bold">
                  {vrtReport.total_pages > 0
                    ? ((vrtReport.total_passed / vrtReport.total_pages) * 100).toFixed(0)
                    : 0}%
                </div>
                <div className="text-xs text-muted-foreground">Succès VRT</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle className="flex items-center gap-2 text-lg">
                <ImageIcon className="h-5 w-5" />
                Comparaison Visuelle
                <Badge
                  variant={vrtReport.total_failed === 0 ? 'success' : 'destructive'}
                >
                  {vrtReport.total_passed}/{vrtReport.total_pages} pass
                </Badge>
              </CardTitle>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground mr-2">Mode de vue :</span>
                <div className="flex gap-1">
                  {(['slider', 'side-by-side', 'diff'] as const).map((mode) => (
                    <Button
                      key={mode}
                      variant={globalViewMode === mode ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setGlobalViewMode(mode)}
                    >
                      {mode === 'slider' ? 'Slider' : mode === 'side-by-side' ? 'Côte à côte' : 'Diff'}
                    </Button>
                  ))}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (collapsedItems.size === vrtReport.items.length) {
                      setCollapsedItems(new Set());
                    } else {
                      setCollapsedItems(new Set(vrtReport.items.map((_, idx) => idx)));
                    }
                  }}
                >
                  {collapsedItems.size === vrtReport.items.length ? (
                    <>
                      <ChevronDown className="mr-2 h-4 w-4" />
                      Tout déplier
                    </>
                  ) : (
                    <>
                      <ChevronUp className="mr-2 h-4 w-4" />
                      Tout replier
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {vrtReport.items.map((item, idx) => (
              <ImageComparer
                key={idx}
                beforeSrc={item.before_screenshot || ''}
                afterSrc={item.after_screenshot || ''}
                diffSrc={item.diff_image || undefined}
                diffPercentage={item.diff_percentage || undefined}
                ssimScore={item.ssim_score || undefined}
                passed={item.passed || undefined}
                pageName={item.page_name}
                pageUrl={item.page_url}
                device={item.device}
                defaultViewMode={globalViewMode}
                isCollapsed={collapsedItems.has(idx)}
                onToggleCollapse={() => {
                  setCollapsedItems((prev) => {
                    const newSet = new Set(prev);
                    if (newSet.has(idx)) {
                      newSet.delete(idx);
                    } else {
                      newSet.add(idx);
                    }
                    return newSet;
                  });
                }}
              />
            ))}
          </CardContent>
        </Card>
      </>
    );
  }

  if (hasCurrentProject) {
    return (
      <Card>
        <CardContent className="pt-6 flex flex-col items-center justify-center py-12 text-center">
          <ImageOff className="h-12 w-12 text-muted-foreground/30 mb-4" />
          <h3 className="text-lg font-semibold text-muted-foreground">
            Aucun rapport VRT
          </h3>
          <p className="text-sm text-muted-foreground mt-2 max-w-md">
            Lancez une maintenance pour générer des captures d'écran avant/après et comparer visuellement les changements.
          </p>
        </CardContent>
      </Card>
    );
  }

  return null;
}
