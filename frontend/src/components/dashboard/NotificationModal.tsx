import { useAppStore } from '@/stores/appStore';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
  Trash2,
  CheckCheck,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface NotificationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function NotificationModal({ isOpen, onClose }: NotificationModalProps) {
  const {
    notifications,
    markAllNotificationsAsRead,
    removeNotification,
    clearNotifications,
  } = useAppStore();

  const unreadCount = notifications.filter((n) => !n.read).length;

  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return '';
    }
  };

  const getVariantConfig = (variant: string) => {
    switch (variant) {
      case 'success':
        return {
          icon: <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />,
          borderColor: 'border-l-green-500',
          bg: 'bg-green-500/5',
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />,
          borderColor: 'border-l-amber-500',
          bg: 'bg-amber-500/5',
        };
      case 'destructive':
        return {
          icon: <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />,
          borderColor: 'border-l-red-500',
          bg: 'bg-red-500/5',
        };
      case 'info':
      default:
        return {
          icon: <Info className="h-4 w-4 text-blue-500 shrink-0" />,
          borderColor: 'border-l-blue-500',
          bg: 'bg-blue-500/5',
        };
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-4 border-b border-border flex flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <DialogTitle className="text-lg font-bold">Notifications</DialogTitle>
            {unreadCount > 0 && (
              <Badge variant="destructive" className="px-1.5 py-0 text-xs">
                {unreadCount} non lue{unreadCount > 1 ? 's' : ''}
              </Badge>
            )}
          </div>
          {notifications.length > 0 && (
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={markAllNotificationsAsRead}
                  className="h-8 text-xs text-muted-foreground hover:text-foreground"
                  title="Tout marquer comme lu"
                >
                  <CheckCheck className="h-3.5 w-3.5 mr-1" />
                  Tout lire
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={clearNotifications}
                className="h-8 text-xs text-muted-foreground hover:text-destructive"
                title="Vider toutes les notifications"
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Vider
              </Button>
            </div>
          )}
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-4 space-y-2.5 custom-scrollbar">
          {notifications.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground flex flex-col items-center justify-center space-y-2">
              <Bell className="h-10 w-10 text-muted-foreground/30" />
              <p className="text-sm font-medium">Aucune notification pour le moment.</p>
            </div>
          ) : (
            notifications.map((notif) => {
              const config = getVariantConfig(notif.variant);
              return (
                <div
                  key={notif.id}
                  className={cn(
                    'p-3 rounded-md border border-border border-l-4 transition-all relative group flex items-start gap-3',
                    config.borderColor,
                    notif.read ? 'bg-background opacity-80' : cn(config.bg, 'shadow-xs font-medium')
                  )}
                >
                  <div className="mt-0.5">{config.icon}</div>

                  <div className="flex-1 min-w-0 pr-6">
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="text-sm font-semibold text-foreground truncate">
                        {notif.title}
                      </h4>
                      <span className="text-[11px] text-muted-foreground shrink-0">
                        {formatTime(notif.timestamp)}
                      </span>
                    </div>

                    {notif.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap break-words">
                        {notif.description}
                      </p>
                    )}
                  </div>

                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeNotification(notif.id)}
                    className="h-6 w-6 absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                    title="Supprimer la notification"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
