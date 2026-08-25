import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import GlassCard from '../components/GlassCard';
import {
  Activity, AlertTriangle, ArrowRight, Bot, Calendar, ClipboardList, Clock,
  Droplets, FileText, FlaskConical, Heart, HeartPulse, LogOut, Moon, Pill,
  RefreshCw, Scale, Sparkles, Stethoscope, Target, TrendingUp, Users
} from 'lucide-react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis
} from 'recharts';
import {
  adminAnalyticsService, healthObservationService, healthOverviewService, recordsService
} from '../services/api';
import { Button } from '../components/ui/button';

const Metric = ({ label, icon: Icon, value }) => (
  <div className="rounded-xl border border-slate-100 p-3 dark:border-slate-700 bg-white/40 dark:bg-gray-800/40">
    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
      <Icon className="size-4 text-blue-500" />{label}
    </div>
    <p className="mt-1 font-semibold text-slate-900 dark:text-white">{value}</p>
  </div>
);

const HomePage = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { t } = useLanguage();

  const [overview, setOverview] = useState(null);
  const [observations, setObservations] = useState([]);
  const [records, setRecords] = useState([]);
  const [adminKpis, setAdminKpis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [chartMetric, setChartMetric] = useState(null);

  const [loadError, setLoadError] = useState(false);

  const isAdmin = (user?.role || '').toLowerCase() === 'admin';

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    let coreFailed = false;
    const soft = (p, fallback) => p.catch(() => fallback);
    const core = (p) =>
      p.catch(() => {
        coreFailed = true;
        return undefined;
      });
    const [ov, obs, recs, kpis] = await Promise.all([
      core(healthOverviewService.get()),
      soft(healthObservationService.list(), []),
      core(recordsService.getAll()),
      isAdmin ? soft(adminAnalyticsService.getDashboard(), null) : Promise.resolve(null),
    ]);
    setOverview(ov || null);
    setObservations(Array.isArray(obs) ? obs : []);
    setRecords(Array.isArray(recs) ? recs : []);
    setAdminKpis(kpis?.kpis || kpis || null);
    setLoadError(coreFailed);
    setLoading(false);
  }, [isAdmin]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const metrics = overview?.metrics || {};
  const latestWeight = metrics.latest_weight ?? null;
  const weightChange = metrics.weight_change ?? null;
  const averageSleep = metrics.average_sleep ?? null;
  const averageWater = metrics.average_water ?? null;
  const observationCount = metrics.observation_count ?? 0;
  const documentCount = metrics.document_count ?? 0;
  const totalRecords = records.length;
  const alerts = Array.isArray(overview?.alerts) ? overview.alerts : [];
  const hasData = totalRecords + observationCount + documentCount > 0;

  const healthScore = useMemo(() => {
    if (!hasData) return 12;
    let s = 100 - Math.min(alerts.length * 7, 35);
    const goal = overview?.weight_goal;
    if (goal?.target_weight_kg != null && latestWeight != null) {
      const diff = Math.abs(goal.target_weight_kg - latestWeight);
      if (diff <= 2) s += 5;
      else if (diff > 5) s -= 5;
    }
    return Math.max(0, Math.min(100, Math.round(s)));
  }, [hasData, alerts, latestWeight, overview]);

  const scoreTone =
    healthScore >= 80 ? 'from-emerald-500 to-teal-500'
      : healthScore >= 50 ? 'from-amber-500 to-orange-500'
        : 'from-rose-500 to-red-500';

  const chartSeries = useMemo(() => {
    const list = [];
    const seen = new Set();
    const add = (label, unit, pts) => {
      const data = (pts || []).filter((p) => p.value != null).map((p) => ({ date: p.date, value: Number(p.value) }));
      const key = String(label).toLowerCase();
      if (!label || seen.has(key) || data.length === 0) return;
      seen.add(key);
      list.push({ label, unit: unit || '', data });
    };
    add(t('home.weight'), 'kg', overview?.weight_trend || []);
    Object.entries(overview?.trends || {}).forEach(([name, pts]) => add(name, pts?.[0]?.unit, pts));
    return list;
  }, [overview, t]);

  const activeSeries = chartSeries.find((s) => s.label === chartMetric) || chartSeries[0] || null;

  const recentActivity = useMemo(() => {
    const items = [];
    observations.forEach((o) => {
      const val = o.value_text != null && o.value_text !== '' ? o.value_text : o.value_numeric;
      items.push({
        id: `o-${o.id}`,
        title: o.name,
        detail: val != null ? `${val} ${o.unit || ''}`.trim() : '',
        date: o.observation_date,
        icon: FlaskConical,
        tone: 'from-blue-500 to-cyan-500',
      });
    });
    records.forEach((r, idx) => {
      const detail = r.weight_kg != null ? `${r.weight_kg} kg` : (r.record_date || '');
      items.push({
        id: `r-${r.id ?? idx}`,
        title: t('home.record'),
        detail,
        date: r.record_date,
        icon: FileText,
        tone: 'from-emerald-500 to-teal-500',
      });
    });
    return items
      .sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')))
      .slice(0, 6);
  }, [observations, records, t]);

  const goal = overview?.weight_goal;
  const goalPct = useMemo(() => {
    if (!goal?.target_weight_kg || latestWeight == null) return null;
    const ref = Math.max(latestWeight, goal.target_weight_kg, 1);
    return Math.max(0, Math.min(100, Math.round(100 - (Math.abs(latestWeight - goal.target_weight_kg) / ref) * 100)));
  }, [goal, latestWeight]);
  const reachedGoal = goalPct != null && goalPct >= 99;

  const formatNumber = (n) => (n == null ? '0' : Number(n).toLocaleString());
  const today = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

  const handleLogout = () => { logout(); navigate('/login'); };

  const quickAccess = [
    { label: t('home.healthOverview'), icon: Stethoscope, to: isAdmin ? '/dashboard' : '/records', color: 'from-blue-500 to-blue-600' },
    { label: t('home.records'), icon: ClipboardList, to: '/records', color: 'from-emerald-500 to-emerald-600' },
    { label: t('home.healthScore'), icon: Heart, to: '/home', color: 'from-rose-500 to-rose-600' },
    { label: t('home.medication'), icon: Pill, to: '/documents', color: 'from-purple-500 to-purple-600' },
    { label: t('home.appointments'), icon: Calendar, to: '/records', color: 'from-amber-500 to-orange-600' },
    { label: t('home.aiAssistant'), icon: Bot, to: '/llm', color: 'from-teal-500 to-cyan-600' },
  ];

  const insightStats = [
    { label: t('home.healthScore'), value: `${healthScore}%`, icon: Heart, color: scoreTone, note: healthScore >= 80 ? t('home.highScore') : healthScore >= 50 ? t('home.midScore') : t('home.lowScore') },
    { label: t('home.totalRecords'), value: formatNumber(totalRecords), icon: FileText, color: 'from-emerald-500 to-teal-500', note: t('home.viewRecords') },
    { label: t('home.verifiedObservations'), value: formatNumber(observationCount), icon: FlaskConical, color: 'from-blue-500 to-indigo-500', note: `${formatNumber(documentCount)} ${t('home.documents')}` },
    { label: t('home.needsAttention'), value: formatNumber(alerts.length), icon: AlertTriangle, color: alerts.length ? 'from-amber-500 to-orange-500' : 'from-gray-400 to-gray-500', note: alerts.length ? t('home.alertsTitle') : t('home.noAlerts') },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Load error recovery */}
      {loadError && !loading && (
        <GlassCard className="p-4 border-amber-200/60 dark:border-amber-700/40">
          <div className="flex items-center gap-3 text-amber-800 dark:text-amber-200">
            <RefreshCw className="w-5 h-5" />
            <span className="flex-1 text-sm">{t('home.loadError')}</span>
            <Button size="sm" variant="outline" onClick={loadData}>
              {t('common.retry')}
            </Button>
          </div>
        </GlassCard>
      )}
      {/* Welcome hero */}
      <GlassCard className="relative overflow-hidden p-6 sm:p-8">
        <div className="absolute -top-16 -right-16 w-64 h-64 rounded-full bg-gradient-to-br from-blue-500/20 to-purple-500/20 blur-3xl"></div>
        <div className="relative flex flex-col md:flex-row md:items-center gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Activity className="w-4 h-4" />
              <span>{today}</span>
              {loading && <span className="ml-1 text-xs text-blue-500 animate-pulse">…</span>}
            </div>
            <h1 className="mt-2 text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white">
              {t('home.welcome', { name: user?.name || user?.username || 'Admin' })}
            </h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              {hasData ? t('home.healthSummary') : t('home.noData')}
            </p>
            <p className="mt-1 text-sm font-medium text-blue-600 dark:text-blue-400">
              <Sparkles className="inline size-4 mr-1" />{t('home.motivational')}
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={() => navigate('/records')}>
                <FileText className="size-4" />{t('home.viewRecords')}
              </Button>
              <Button size="lg" variant="outline" onClick={() => navigate('/llm')}>
                <Bot className="size-4" />{t('home.askAssistant')}
              </Button>
              <Button size="icon" variant="ghost" title={t('home.logout')} onClick={handleLogout} className="ml-auto">
                <LogOut className="size-5" />
              </Button>
            </div>
          </div>
          <div className="relative hidden md:flex items-center justify-center w-52 h-52 shrink-0">
            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-blue-500/15 to-emerald-500/15 blur-xl"></div>
            <div className={`relative w-28 h-28 rounded-full bg-gradient-to-br ${scoreTone} shadow-2xl flex items-center justify-center`}>
              <HeartPulse className="w-12 h-12 text-white" />
            </div>
            <div className="absolute top-4 right-0 rounded-xl bg-white/90 dark:bg-gray-800/90 shadow-lg px-3 py-2 text-center border border-white/40 dark:border-gray-600/40">
              <p className="text-[11px] text-gray-500">{t('home.healthScore')}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">{healthScore}%</p>
            </div>
            <div className="absolute bottom-2 left-0 rounded-xl bg-white/90 dark:bg-gray-800/90 shadow-lg px-3 py-2 text-center border border-white/40 dark:border-gray-600/40">
              <p className="text-[11px] text-gray-500">{t('home.totalRecords')}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">{totalRecords}</p>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Insight stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {insightStats.map((s) => (
          <GlassCard key={s.label} hover className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{s.label}</p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{s.value}</p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{s.note}</p>
              </div>
              <div className={`p-3 rounded-xl bg-gradient-to-br ${s.color} shadow-lg`}>
                <s.icon className="w-5 h-5 text-white" />
              </div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Health overview */}
      <GlassCard className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white">
            <Stethoscope className="size-5 text-blue-500" />{t('home.healthOverview')}
          </h2>
          <Button variant="ghost" size="sm" onClick={() => navigate('/records')}>
            {t('home.viewRecords')}<ArrowRight className="size-4" />
          </Button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Metric label={t('home.latestWeight')} icon={Scale} value={latestWeight != null ? `${latestWeight} kg` : '—'} />
          <Metric label={t('home.weightChange')} icon={TrendingUp} value={weightChange != null ? `${weightChange > 0 ? '+' : ''}${weightChange} kg` : '—'} />
          <Metric label={t('home.avgSleep')} icon={Moon} value={averageSleep != null ? `${averageSleep} h` : '—'} />
          <Metric label={t('home.avgWater')} icon={Droplets} value={averageWater != null ? `${averageWater} L` : '—'} />
        </div>
        <div className="mt-5 rounded-xl bg-slate-50 dark:bg-gray-900/40 p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              <Target className="size-4 text-blue-500" />{t('home.weightGoal')}
            </p>
            {goal?.target_weight_kg != null ? (
              reachedGoal ? (
                <span className="text-sm font-semibold text-emerald-600">{t('home.reachedGoal')}</span>
              ) : (
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  {latestWeight != null ? `${Math.abs(latestWeight - goal.target_weight_kg)} ${t('home.toGoal')}` : `${goal.target_weight_kg} kg`}
                </span>
              )
            ) : (
              <span className="text-sm text-gray-500 dark:text-gray-400">{t('home.noGoal')}</span>
            )}
          </div>
          <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${reachedGoal ? 'from-emerald-500 to-teal-500' : 'from-blue-500 to-indigo-500'} transition-all`}
              style={{ width: `${goalPct ?? 0}%` }}
            ></div>
          </div>
        </div>
      </GlassCard>
      {/* Health Trends + Recent Activity */}
      <div className="grid gap-6 lg:grid-cols-3">
        <GlassCard className="p-6 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white">
              <Activity className="size-5 text-blue-500" />{t('home.healthTrends')}
            </h2>
            {chartSeries.length > 1 && (
              <div className="flex flex-wrap gap-2">
                {chartSeries.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => setChartMetric(s.label)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      s.label === activeSeries?.label
                        ? 'bg-blue-600 text-white shadow'
                        : 'text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {activeSeries ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activeSeries.data} margin={{ top: 10, right: 10, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="healthFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="currentColor" />
                  <YAxis tick={{ fontSize: 11 }} stroke="currentColor" />
                  <Tooltip formatter={(value) => [`${value} ${activeSeries.unit}`, activeSeries.label]} />
                  <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fill="url(#healthFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
              {t('home.noTrendData')}
            </div>
          )}
        </GlassCard>

        <GlassCard className="p-6">
          <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white mb-4">
            <Clock className="size-5 text-blue-500" />{t('home.recentActivity')}
          </h2>
          <div className="space-y-2">
            {recentActivity.length ? recentActivity.map((a) => (
              <div key={a.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/40 dark:hover:bg-gray-800/40 transition-colors">
                <div className={`p-2 rounded-lg bg-gradient-to-br ${a.tone}`}>
                  <a.icon className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{a.title}</p>
                  {a.detail ? <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{a.detail}</p> : null}
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">{a.date || '—'}</span>
              </div>
            )) : (
              <div className="py-10 text-center text-sm text-gray-500 dark:text-gray-400">{t('home.noRecentActivity')}</div>
            )}
          </div>
        </GlassCard>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <GlassCard className="p-6 border-amber-200/60 dark:border-amber-700/40">
          <h2 className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white mb-4">
            <AlertTriangle className="size-5 text-amber-500" />{t('home.alertsTitle')}
          </h2>
          <div className="space-y-3">
            {alerts.map((a) => (
              <div key={a.observation_id} className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                <p className="font-medium">{a.title}</p>
                <p className="mt-0.5 text-xs">{a.detail}{a.document_name ? ` · ${a.document_name}` : ''}{a.source_page ? ` · p. ${a.source_page}` : ''}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* AI Assistant banner */}
      <GlassCard className="relative overflow-hidden p-6 sm:p-8">
        <div className="absolute -bottom-20 -left-16 w-72 h-72 rounded-full bg-gradient-to-br from-teal-500/20 to-cyan-500/20 blur-3xl"></div>
        <div className="relative flex flex-col md:flex-row items-start md:items-center gap-6">
          <div className="p-3 rounded-2xl bg-gradient-to-br from-teal-500 to-cyan-600 shadow-xl">
            <Bot className="w-8 h-8 text-white" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t('home.aiTitle')}</h2>
            <p className="mt-1 text-gray-600 dark:text-gray-400">{t('home.aiDescription')}</p>
          </div>
          <Button size="lg" className="bg-gradient-to-r from-teal-500 to-cyan-600 hover:from-teal-600 hover:to-cyan-700 text-white" onClick={() => navigate('/llm')}>
            {t('home.startConversation')}<ArrowRight className="size-4" />
          </Button>
        </div>
      </GlassCard>

      {/* Quick access */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {quickAccess.map((q) => (
          <button
            key={q.label}
            onClick={() => navigate(q.to)}
            className="group p-4 rounded-2xl backdrop-blur-md bg-white/60 dark:bg-gray-800/60 border border-white/40 dark:border-gray-700/50 hover:border-blue-400/60 hover:shadow-lg transition-all text-left"
          >
            <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${q.color} flex items-center justify-center mb-3 shadow`}>
              <q.icon className="w-5 h-5 text-white" />
            </div>
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{q.label}</p>
          </button>
        ))}
      </div>

      {/* Admin system overview */}
      {isAdmin && (
        <GlassCard className="p-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">{t('home.systemStats')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: t('home.systemPatients'), value: formatNumber(adminKpis?.total_users), icon: Users },
              { label: t('home.systemRecords'), value: formatNumber(adminKpis?.total_records), icon: FileText },
              { label: t('home.systemActive'), value: formatNumber(adminKpis?.active_users), icon: Activity },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-3 p-4 rounded-xl bg-slate-50 dark:bg-gray-900/40">
                <s.icon className="w-6 h-6 text-blue-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{s.label}</p>
                  <p className="text-xl font-bold text-gray-900 dark:text-white">{s.value}</p>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
};

export default HomePage;

