import { useState, useCallback } from 'react';
import { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from '@/components/ui/Toast';

import { useAppStore } from '@/stores/appStore';

type ToastVariant = 'default' | 'success' | 'info' | 'warning' | 'destructive';

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration?: number;
}

let toastCount = 0;

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback(
    ({ title, description, variant = 'default', duration = 5000 }: Omit<ToastItem, 'id'>) => {
      const id = `toast-${++toastCount}`;
      setToasts((prev) => [...prev, { id, title, description, variant, duration }]);
      useAppStore.getState().addNotification({ title, description, variant });
    },
    [],
  );

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toast, dismiss, toasts };
}

interface ToasterProps {
  toasts: ToastItem[];
  dismiss: (id: string) => void;
}

export function Toaster({ toasts, dismiss }: ToasterProps) {
  return (
    <ToastProvider>
      {toasts.map((t) => (
        <Toast
          key={t.id}
          variant={t.variant}
          duration={t.duration}
          onOpenChange={(open) => {
            if (!open) dismiss(t.id);
          }}
        >
          <div className="grid gap-1">
            <ToastTitle>{t.title}</ToastTitle>
            {t.description && <ToastDescription>{t.description}</ToastDescription>}
          </div>
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
