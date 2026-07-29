import { useState, useRef, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import { ChevronDown, ChevronUp, Sliders, Columns, Eye, ExternalLink, CheckCircle2, AlertTriangle } from 'lucide-react';

interface ImageComparerProps {
  beforeSrc: string;
  afterSrc: string;
  diffSrc?: string;
  diffPercentage?: number;
  ssimScore?: number;
  passed?: boolean;
  pageName: string;
  pageUrl?: string;
  device: string;
  defaultViewMode?: 'slider' | 'side-by-side' | 'diff';
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function ImageComparer({
  beforeSrc,
  afterSrc,
  diffSrc,
  diffPercentage,
  ssimScore,
  passed,
  pageName,
  pageUrl,
  device,
  defaultViewMode = 'slider',
  isCollapsed = false,
  onToggleCollapse,
}: ImageComparerProps) {
  const [sliderPos, setSliderPos] = useState(50);
  const [isDragging, setIsDragging] = useState(false);
  const [viewMode, setViewMode] = useState<'slider' | 'side-by-side' | 'diff'>(defaultViewMode);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setViewMode(defaultViewMode);
  }, [defaultViewMode]);

  const handleMove = useCallback(
    (clientX: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
      setSliderPos((x / rect.width) * 100);
    },
    [],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isDragging) handleMove(e.clientX);
    },
    [isDragging, handleMove],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (isDragging && e.touches[0]) handleMove(e.touches[0].clientX);
    },
    [isDragging, handleMove],
  );

  const getScreenshotUrl = (path: string | undefined | null) => {
    if (!path) return '';
    const normalized = path.replace(/\\/g, '/');
    const match = normalized.match(/data\/screenshots\/(.+)/i);
    if (match) {
      return `/static/data/screenshots/${match[1]}`;
    }
    if (normalized.startsWith('/static/') || normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return normalized;
    }
    return `/static/data/screenshots/${normalized}`;
  };

  return (
    <div className="group border border-border/80 hover:border-primary/40 rounded-xl bg-card/60 backdrop-blur-xs transition-all duration-300 shadow-xs hover:shadow-md overflow-hidden">
      {/* Header Bar */}
      <div className="p-3 sm:p-4 flex items-center justify-between flex-wrap gap-3 bg-muted/20 border-b border-border/40">
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={onToggleCollapse}
            className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted/80 rounded-md transition-colors"
            aria-label={isCollapsed ? 'Déplier' : 'Replier'}
          >
            {isCollapsed ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronUp className="h-4 w-4" />
            )}
          </button>
          <span className="font-semibold text-sm tracking-tight text-foreground">{pageName}</span>
          <Badge variant="outline" className="text-[11px] font-mono capitalize px-2 py-0.5 bg-background/50">
            {device}
          </Badge>
          {passed !== undefined && (
            <Badge
              variant={passed ? 'success' : 'destructive'}
              className="text-[11px] font-bold px-2 py-0.5 shadow-xs flex items-center gap-1"
            >
              {passed ? (
                <>
                  <CheckCircle2 className="h-3 w-3" /> PASS
                </>
              ) : (
                <>
                  <AlertTriangle className="h-3 w-3" /> FAIL
                </>
              )}
            </Badge>
          )}
          {pageUrl && (
            <a
              href={pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3 shrink-0" />
              <span className="truncate max-w-[200px]">{pageUrl}</span>
            </a>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs font-mono text-muted-foreground bg-background/40 px-2.5 py-1 rounded-lg border border-border/30">
          {diffPercentage !== undefined && (
            <div className="flex items-center gap-1">
              <span>Diff:</span>
              <span className={cn(
                "font-semibold",
                diffPercentage > 0 ? "text-amber-500 dark:text-amber-400" : "text-emerald-500"
              )}>
                {diffPercentage.toFixed(2)}%
              </span>
            </div>
          )}
          {ssimScore !== undefined && (
            <div className="flex items-center gap-1 border-l border-border/50 pl-3">
              <span>SSIM:</span>
              <span className="font-semibold text-foreground">{ssimScore.toFixed(4)}</span>
            </div>
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-4 space-y-4">
          {/* Mode Switcher Buttons */}
          <div className="inline-flex p-1 bg-muted/40 rounded-lg border border-border/40 gap-1">
            <button
              onClick={() => setViewMode('slider')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200',
                viewMode === 'slider'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              )}
            >
              <Sliders className="h-3.5 w-3.5" />
              Slider
            </button>
            <button
              onClick={() => setViewMode('side-by-side')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200',
                viewMode === 'side-by-side'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              )}
            >
              <Columns className="h-3.5 w-3.5" />
              Côte à côte
            </button>
            {diffSrc && (
              <button
                onClick={() => setViewMode('diff')}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200',
                  viewMode === 'diff'
                    ? 'bg-background text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                <Eye className="h-3.5 w-3.5" />
                Diff Image
              </button>
            )}
          </div>

          {/* Slider Mode */}
          {viewMode === 'slider' && (
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-xl border border-border/60 shadow-inner bg-black/5 cursor-col-resize select-none group/slider"
              style={{ aspectRatio: device === 'mobile' ? '375/700' : '16/9', maxHeight: '550px' }}
              onMouseDown={() => setIsDragging(true)}
              onMouseUp={() => setIsDragging(false)}
              onMouseLeave={() => setIsDragging(false)}
              onMouseMove={handleMouseMove}
              onTouchStart={() => setIsDragging(true)}
              onTouchEnd={() => setIsDragging(false)}
              onTouchMove={handleTouchMove}
            >
              <img
                src={getScreenshotUrl(afterSrc)}
                alt="Après"
                loading="lazy"
                className="absolute inset-0 w-full h-full object-cover object-top"
              />
              <img
                src={getScreenshotUrl(beforeSrc)}
                alt="Avant"
                loading="lazy"
                className="absolute inset-0 w-full h-full object-cover object-top transition-all"
                style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
              />
              {/* Divider Line & Handle */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_10px_rgba(0,0,0,0.5)] z-10"
                style={{ left: `${sliderPos}%` }}
              >
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-white/90 backdrop-blur-md shadow-lg border border-black/10 flex items-center justify-center text-slate-800 transition-transform hover:scale-110">
                  <Sliders className="h-4 w-4 rotate-90 text-primary" />
                </div>
              </div>

              {/* Labels */}
              <span className="absolute top-3 left-3 bg-black/70 backdrop-blur-md text-white text-[11px] font-semibold px-2.5 py-1 rounded-md shadow-xs border border-white/10">
                AVANT
              </span>
              <span className="absolute top-3 right-3 bg-black/70 backdrop-blur-md text-white text-[11px] font-semibold px-2.5 py-1 rounded-md shadow-xs border border-white/10">
                APRÈS
              </span>
            </div>
          )}

          {/* Side by Side Mode */}
          {viewMode === 'side-by-side' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Avant</span>
                </div>
                <div className="rounded-xl overflow-hidden border border-border/60 shadow-xs bg-muted/10">
                  <img
                    src={getScreenshotUrl(beforeSrc)}
                    alt="Avant"
                    loading="lazy"
                    className="w-full object-cover object-top max-h-[500px]"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Après</span>
                </div>
                <div className="rounded-xl overflow-hidden border border-border/60 shadow-xs bg-muted/10">
                  <img
                    src={getScreenshotUrl(afterSrc)}
                    alt="Après"
                    loading="lazy"
                    className="w-full object-cover object-top max-h-[500px]"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Diff Image Mode */}
          {viewMode === 'diff' && diffSrc && (
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Visualisation Diff</span>
              <div className="rounded-xl overflow-hidden border border-border/60 shadow-xs bg-black/20 p-2">
                <img
                  src={getScreenshotUrl(diffSrc)}
                  alt="Diff"
                  loading="lazy"
                  className="w-full object-cover object-top max-h-[550px] rounded-lg"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

