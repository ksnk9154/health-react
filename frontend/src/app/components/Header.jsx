import { useEffect, useState } from 'react';
import { Menu, Moon, Sun, Bell, LogOut, Globe, CheckCheck, RefreshCw, Circle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import { useNavigate } from 'react-router';
import { notificationService } from '../services/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Avatar, AvatarFallback } from './ui/avatar';

const Header = ({ onMenuClick }) => {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { t, language, languages, changeLanguage } = useLanguage();
  const navigate = useNavigate();
  // Real notifications from the backend
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifLoading, setNotifLoading] = useState(false);
  const [notifError, setNotifError] = useState('');
  const [notifOpen, setNotifOpen] = useState(false);

  const timeAgo = (iso) => {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    const diffSeconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diffSeconds < 60) return t('header.justNow');
    const minutes = Math.floor(diffSeconds / 60);
    if (minutes < 60) return `${minutes} ${t('header.minAgo')}`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ${t('header.hourAgo')}`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} ${t('header.dayAgo')}`;
    return date.toLocaleDateString();
  };

  const loadNotifications = async (quiet = false) => {
    if (!quiet) setNotifLoading(true);
    setNotifError('');
    try {
      const result = await notificationService.list(50);
      const items = Array.isArray(result?.items) ? result.items : [];
      setNotifications(items);
      setUnreadCount(
        typeof result?.unread_count === 'number'
          ? result.unread_count
          : items.filter((n) => !n.is_read).length
      );
    } catch (error) {
      setNotifError(error.response?.data?.detail || t('header.notificationsError'));
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setNotifLoading(false);
    }
  };

  // Fetch notifications on mount
  useEffect(() => {
    loadNotifications(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh when the dropdown is opened (so the list stays current)
  useEffect(() => {
    if (notifOpen) {
      loadNotifications(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notifOpen]);

  const handleOpenChange = (open) => {
    setNotifOpen(open);
  };

  // Mark a single notification as read when clicked
  const handleNotificationClick = async (id) => {
    const item = notifications.find((n) => n.id === id);
    // Optimistic UI update
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    if (item && !item.is_read) {
      setUnreadCount((c) => Math.max(0, c - 1));
    }
    try {
      await notificationService.markRead(id);
    } catch (error) {
      // Revert on failure so the badge/state stays truthful
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: !!item?.is_read } : n)));
      if (item && !item.is_read) {
        setUnreadCount((c) => c + 1);
      }
    }
  };

  const handleMarkAllRead = async () => {
    const hadUnread = notifications.some((n) => !n.is_read);
    // Optimistic update
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    if (hadUnread) setUnreadCount(0);
    try {
      await notificationService.markAllRead();
    } catch (error) {
      // Reload from the backend to restore the true state
      loadNotifications(true);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getInitials = (name) => {
    if (!name) return 'U';
    return name
      .split(' ')
      .map(word => word[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <header className="sticky top-0 z-30 backdrop-blur-md bg-white/80 dark:bg-gray-900/80 border-b border-gray-200/50 dark:border-gray-700/50">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-4">
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Menu className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              {t('header.welcome', { name: user?.name || user?.username || 'User' })}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {new Date().toLocaleDateString(language === 'en' ? 'en-US' : language, { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
              })}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Language Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-1"
                aria-label={t('settings.language')}
              >
                <Globe className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                <span className="hidden sm:inline text-xs font-medium text-gray-700 dark:text-gray-300">
                  {language.toUpperCase()}
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {Object.entries(languages).map(([code, { label, flag }]) => (
                <DropdownMenuItem
                  key={code}
                  onClick={() => changeLanguage(code)}
                  className={language === code ? 'bg-blue-50 dark:bg-blue-900/30' : ''}
                >
                  <span className="mr-2 text-lg">{flag}</span>
                  {label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label={t('login.toggleTheme')}
          >
            {theme === 'light' ? (
              <Moon className="w-5 h-5 text-gray-700 dark:text-gray-300" />
            ) : (
              <Sun className="w-5 h-5 text-gray-700 dark:text-gray-300" />
            )}
          </button>

          {/* Notifications */}
          <DropdownMenu open={notifOpen} onOpenChange={handleOpenChange}>
  <DropdownMenuTrigger asChild>
    <button
      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors relative"
      aria-label={t('header.notifications')}
    >
      <Bell className="w-5 h-5 text-gray-700 dark:text-gray-300" />

      {unreadCount > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-semibold">
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  </DropdownMenuTrigger>

  <DropdownMenuContent
    align="end"
    className="w-80 backdrop-blur-md bg-white/95 dark:bg-gray-800/95"
  >
    <div className="flex items-center justify-between px-2 py-1.5">
      <DropdownMenuLabel className="px-2 py-0">{t('header.notifications')}</DropdownMenuLabel>
      {unreadCount > 0 && (
        <button
          type="button"
          onClick={handleMarkAllRead}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/30 transition-colors"
        >
          <CheckCheck className="size-3.5" />
          {t('header.markAllRead')}
        </button>
      )}
    </div>

    <DropdownMenuSeparator />

    {notifLoading && notifications.length === 0 ? (
      <div className="flex items-center gap-2 p-4 text-sm text-gray-500">
        <RefreshCw className="w-4 h-4 animate-spin" />
        {t('common.loading')}
      </div>
    ) : notifError ? (
      <div className="p-4 text-sm text-red-600 dark:text-red-400">{notifError}</div>
    ) : notifications.length === 0 ? (
      <div className="p-4 text-sm text-gray-500">
        {t('header.noNotifications')}
      </div>
    ) : (
      notifications.map((item) => (
        <DropdownMenuItem
          key={item.id}
          className="flex flex-col items-start py-3 cursor-pointer"
          onClick={() => handleNotificationClick(item.id)}
        >
          <div className="flex w-full items-start gap-2">
            {!item.is_read && (
              <Circle className="size-2 mt-1.5 shrink-0 fill-current text-blue-500" />
            )}
            <span className={`flex-1 font-medium ${item.is_read ? 'text-gray-700 dark:text-gray-300' : 'text-gray-900 dark:text-white'}`}>
              {item.title || item.message}
            </span>
          </div>

          <span className="pl-4 text-xs text-gray-500">
            {item.title && item.message && item.message.toLowerCase() !== item.title.toLowerCase()
              ? <span className="block">{item.message}</span>
              : null}
            <span className="block">{timeAgo(item.created_at)}</span>
          </span>
        </DropdownMenuItem>
      ))
    )}
  </DropdownMenuContent>
</DropdownMenu>

          {/* User Menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <Avatar>
                  <AvatarFallback className="bg-gradient-to-br from-blue-500 to-indigo-600 text-white">
                    {getInitials(user?.name || user?.username)}
                  </AvatarFallback>
                </Avatar>
                <div className="hidden md:block text-left">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {user?.name || user?.username}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {user?.role || 'User'}
                  </p>
                </div>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 backdrop-blur-md bg-white/95 dark:bg-gray-800/95">
              <DropdownMenuLabel>{t('header.myAccount')}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => navigate('/profile')}>
                {t('common.profile')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('/settings')}>
                {t('common.settings')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout} className="text-red-600 dark:text-red-400">
                <LogOut className="w-4 h-4 mr-2" />
                {t('common.logout')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
};

export default Header;