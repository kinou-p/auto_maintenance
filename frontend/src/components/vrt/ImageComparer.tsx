import { useState, useRef, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import { ChevronDown, ChevronUp } from 'lucide-react';

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
    <div className="space-y-3 border border-border rounded-lg p-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={onToggleCollapse}
            className="p-0.5 hover:bg-muted rounded transition-colors"
            aria-label={isCollapsed ? 'Déplier' : 'Replier'}
          >
            {isCollapsed ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronUp className="h-4 w-4" />
            )}
          </button>
          <h4 className="text-sm font-semibold">{pageName}</h4>
          <Badge variant="outline">{device}</Badge>
          {passed !== undefined && (
            <Badge variant={passed ? 'success' : 'destructive'}>
              {passed ? 'PASS' : 'FAIL'}
            </Badge>
          )}
          {pageUrl && (
            <a
              href={pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-primary underline"
              onClick={(e) => e.stopPropagation()}
            >
              {pageUrl}
            </a>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {diffPercentage !== undefined && (
            <span>Diff: {diffPercentage.toFixed(2)}%</span>
          )}
          {ssimScore !== undefined && (
            <span>SSIM: {ssimScore.toFixed(4)}</span>
          )}
        </div>
      </div>

      {!isCollapsed && (
        <>
          <div className="flex gap-1">
            {(['slider', 'side-by-side', 'diff'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={cn(
                  'px-3 py-1 text-xs rounded transition-colors',
                  viewMode === mode
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
                )}
              >
                {mode === 'slider' ? 'Slider' : mode === 'side-by-side' ? 'Côte à côte' : 'Diff'}
              </button>
            ))}
          </div>

          {viewMode === 'slider' && (
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-lg border border-border cursor-col-resize select-none"
              style={{ aspectRatio: device === 'mobile' ? '375/812' : '16/9', maxHeight: '500px' }}
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
                className="absolute inset-0 w-full h-full object-cover object-top"
                style={{ clipPath: `inset(0 ${100 - sliderPos}% 0 0)` }}
              />
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg z-10"
                style={{ left: `${sliderPos}%` }}
              >
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-8 w-8 rounded-full bg-white shadow-lg flex items-center justify-center">
                  <span className="text-xs font-bold text-gray-800">⇔</span>
                </div>
              </div>
              <span className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded">
                AVANT
              </span>
              <span className="absolute top-2 right-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded">
                APRÈS
              </span>
            </div>
          )}

          {viewMode === 'side-by-side' && (
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Avant</span>
                <img
                  src={getScreenshotUrl(beforeSrc)}
                  alt="Avant"
                  loading="lazy"
                  className="w-full rounded-lg border border-border"
                />
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Après</span>
                <img
                  src={getScreenshotUrl(afterSrc)}
                  alt="Après"
                  loading="lazy"
                  className="w-full rounded-lg border border-border"
                />
              </div>
            </div>
          )}

          {viewMode === 'diff' && diffSrc && (
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Image de diff</span>
              <img
                src={getScreenshotUrl(diffSrc)}
                alt="Diff"
                loading="lazy"
                className="w-full rounded-lg border border-border"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
