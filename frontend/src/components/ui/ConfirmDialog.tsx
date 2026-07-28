import { useState, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { AlertTriangle } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'destructive';
  onConfirm: () => void;
  loading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirmer',
  cancelLabel = 'Annuler',
  variant = 'default',
  onConfirm,
  loading = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {variant === 'destructive' && (
              <AlertTriangle className="h-5 w-5 text-destructive" />
            )}
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-4">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={variant === 'destructive' ? 'destructive' : 'default'}
            onClick={() => {
              onConfirm();
              onOpenChange(false);
            }}
            disabled={loading}
          >
            {loading ? '...' : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function useConfirmDialog() {
  const [state, setState] = useState<{
    open: boolean;
    props: Omit<ConfirmDialogProps, 'open' | 'onOpenChange' | 'onConfirm'>;
    resolve: ((value: boolean) => void) | null;
  }>({
    open: false,
    props: { title: '', description: '' },
    resolve: null,
  });

  const confirm = useCallback(
    (props: Omit<ConfirmDialogProps, 'open' | 'onOpenChange' | 'onConfirm'>): Promise<boolean> => {
      return new Promise((resolve) => {
        setState({ open: true, props, resolve });
      });
    },
    [],
  );

  const handleConfirm = useCallback(() => {
    state.resolve?.(true);
    setState((prev) => ({ ...prev, open: false, resolve: null }));
  }, [state.resolve]);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        state.resolve?.(false);
        setState((prev) => ({ ...prev, open: false, resolve: null }));
      }
    },
    [state.resolve],
  );

  const dialog = (
    <ConfirmDialog
      open={state.open}
      onOpenChange={handleOpenChange}
      onConfirm={handleConfirm}
      {...state.props}
    />
  );

  return { confirm, dialog };
}
