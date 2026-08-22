import React, { useEffect, useState } from 'react';
import { userService } from '../api';
import type { NotificationItem } from '../api';

interface NotificationsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function NotificationsDrawer({ isOpen, onClose }: NotificationsDrawerProps) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      loadNotifications();
    }
  }, [isOpen]);

  const loadNotifications = async () => {
    setLoading(true);
    try {
      const res = await userService.getPendingNotifications();
      setNotifications(res.notifications || []);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-background/50 backdrop-blur-sm z-40 transition-opacity" onClick={onClose}></div>
      <div className="fixed top-0 right-0 h-full w-full max-w-sm bg-surface shadow-2xl z-50 transform transition-transform border-l border-surface-variant flex flex-col">
        
        <div className="p-6 border-b border-surface-variant flex justify-between items-center bg-surface-container-lowest">
          <h2 className="font-headline-md text-[22px] font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">notifications</span> Notifications
          </h2>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-surface-container-lowest">
          {loading ? (
            <div className="flex justify-center p-8 text-on-surface-variant">
              <span className="material-symbols-outlined animate-spin text-[32px]">sync</span>
            </div>
          ) : notifications.length === 0 ? (
            <div className="text-center p-12">
              <div className="w-16 h-16 bg-surface-variant/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="material-symbols-outlined text-on-surface-variant">notifications_paused</span>
              </div>
              <p className="font-body-md text-on-surface-variant">You're all caught up!</p>
            </div>
          ) : (
            notifications.map((n, i) => (
              <div key={i} className="bg-surface border border-surface-variant p-4 rounded-2xl shadow-sm relative overflow-hidden">
                <div className={`absolute left-0 top-0 bottom-0 w-1 ${n.type === 'alert' ? 'bg-error' : 'bg-primary'}`}></div>
                <h4 className="font-label-md text-on-surface font-semibold mb-1">{n.title}</h4>
                <p className="font-caption text-on-surface-variant text-sm">{n.message}</p>
              </div>
            ))
          )}
        </div>

      </div>
    </>
  );
}
