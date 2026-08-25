import { NavLink } from 'react-router';
import { 
  Home, 
  LayoutDashboard, 
  FileText, 
  BarChart3, 
  Users, 
  UserCircle, 
  Settings,
  Bot,
  X
} from 'lucide-react';
import { cn } from './ui/utils';
import { useLanguage } from '../i18n/LanguageContext';
import { useAuth } from '../contexts/AuthContext';

const Sidebar = ({ isOpen, onClose }) => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const isAdmin = (user?.role || '').toLowerCase() === 'admin';

  const navigation = [
    { name: t('sidebar.home'), href: '/home', icon: Home },
    { name: t('sidebar.dashboard'), href: '/dashboard', icon: LayoutDashboard, adminOnly: true },
    { name: t('sidebar.records'), href: '/records', icon: FileText },
    { name: t('sidebar.documents'), href: '/documents', icon: FileText },
    { name: t('sidebar.analytics'), href: '/analytics', icon: BarChart3, adminOnly: true },
    { name: t('sidebar.userManagement'), href: '/admin/users', icon: Users, adminOnly: true },
    { name: t('sidebar.profile'), href: '/profile', icon: UserCircle },
    { name: t('sidebar.settings'), href: '/settings', icon: Settings },
    { name: t('sidebar.aiAssistant'), href: '/llm', icon: Bot },
  ].filter((item) => (item.adminOnly ? isAdmin : true));

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed lg:static inset-y-0 left-0 z-50 w-64 transform transition-transform duration-300 ease-in-out',
          'backdrop-blur-md bg-white/80 dark:bg-gray-900/80 border-r border-gray-200/50 dark:border-gray-700/50',
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between px-6 py-6 border-b border-gray-200/50 dark:border-gray-700/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg">
                <span className="text-white font-bold text-xl">H</span>
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900 dark:text-white">{t('sidebar.brand')}</h1>
                <p className="text-xs text-gray-600 dark:text-gray-400">{t('sidebar.brandSub')}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="lg:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
            {navigation.map((item) => (
              <NavLink
                key={item.name}
                to={item.href}
                onClick={() => window.innerWidth < 1024 && onClose()}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200',
                    'hover:bg-gray-100 dark:hover:bg-gray-800',
                    isActive
                      ? 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-lg'
                      : 'text-gray-700 dark:text-gray-300'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon className="w-5 h-5" />
                    <span className="font-medium">{item.name}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200/50 dark:border-gray-700/50">
            <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
              {t('sidebar.footer')}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;