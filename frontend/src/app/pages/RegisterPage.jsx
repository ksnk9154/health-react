import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../i18n/LanguageContext';
import GlassCard from '../components/GlassCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { authService } from '../services/api';
import { Moon, Sun, Lock, User, Heart, Mail, Globe } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';

const RegisterPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { t, language, languages, changeLanguage } = useLanguage();
  const navigate = useNavigate();

  // Redirect if already authenticated
  if (isAuthenticated) {
    navigate('/home');
    return null;
  }

  const validate = () => {
    if (!username.trim()) return t('register.errorUsernameRequired');
    if (!/^[a-zA-Z0-9_]{3,32}$/.test(username.trim())) {
      return t('register.errorUsernameFormat');
    }
    if (!password) return t('register.errorPasswordRequired');
    if (password.length < 8) return t('register.errorPasswordLength');
    if (password !== confirmPassword) return t('register.errorPasswordMatch');
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const validationError = validate();
    if (validationError) {
      toast.error(validationError);
      return;
    }

    setLoading(true);
    try {
      await authService.register(username.trim(), password);

      toast.success(t('register.success'));

      // Auto-login (optional but smooth UX). Matches requirement to allow sign-in.
      // If login fails, user can still go to /login.
      try {
        await login(username.trim(), password);
        navigate('/home');
      } catch {
        navigate('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute w-96 h-96 bg-blue-400/30 rounded-full blur-3xl -top-48 -left-48 animate-pulse"></div>
        <div className="absolute w-96 h-96 bg-purple-400/30 rounded-full blur-3xl -bottom-48 -right-48 animate-pulse delay-1000"></div>
      </div>

      {/* Top-right controls: Language + Theme */}
      <div className="absolute top-6 right-6 flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="p-3 rounded-xl backdrop-blur-md bg-white/70 dark:bg-gray-800/70 hover:bg-white/90 dark:hover:bg-gray-800/90 transition-all shadow-lg flex items-center gap-2"
              aria-label={t('settings.language')}
            >
              <Globe className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {languages[language]?.flag} {language.toUpperCase()}
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

        <button
          onClick={toggleTheme}
          className="p-3 rounded-xl backdrop-blur-md bg-white/70 dark:bg-gray-800/70 hover:bg-white/90 dark:hover:bg-gray-800/90 transition-all shadow-lg"
          aria-label={t('login.toggleTheme')}
        >
          {theme === 'light' ? (
            <Moon className="w-5 h-5 text-gray-700" />
          ) : (
            <Sun className="w-5 h-5 text-gray-300" />
          )}
        </button>
      </div>

      <div className="relative z-10 w-full max-w-md">
        <GlassCard className="p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg mb-4">
              <Heart className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">{t('register.title')}</h1>
            <p className="text-gray-600 dark:text-gray-400">{t('register.subtitle')}</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="username">{t('register.username')}</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  id="username"
                  type="text"
                  placeholder={t('register.usernamePlaceholder')}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700"
                  disabled={loading}
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">{t('register.password')}</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  id="password"
                  type="password"
                  placeholder={t('register.passwordPlaceholder')}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700"
                  disabled={loading}
                  autoComplete="new-password"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">{t('register.confirmPassword')}</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder={t('register.confirmPasswordPlaceholder')}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700"
                  disabled={loading}
                  autoComplete="new-password"
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white shadow-lg"
              disabled={loading}
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  {t('register.creating')}
                </div>
              ) : (
                t('register.createAccount')
              )}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t('register.haveAccount')}{' '}
              <button
                type="button"
                className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                onClick={() => navigate('/login')}
                disabled={loading}
              >
                {t('register.signIn')}
              </button>
            </p>
          </div>

          <div className="mt-6 p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
            <p className="text-xs text-blue-800 dark:text-blue-300 text-center">
              {t('register.demo')}
            </p>
          </div>
        </GlassCard>
      </div>
    </div>
  );
};

export default RegisterPage;