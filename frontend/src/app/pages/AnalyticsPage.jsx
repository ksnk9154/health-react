import { useEffect, useState } from 'react';
import GlassCard from '../components/GlassCard';
import StatCard from '../components/StatCard';
import { Users, FileText, TrendingUp, Activity, Calendar, Download, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import {
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { useLanguage } from '../i18n/LanguageContext';
import { adminAnalyticsService } from '../services/api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'];

// Simple CSV export helper
const downloadCSV = (filename, rows) => {
  if (!rows || rows.length === 0) return;
  const headers = Object.keys(rows[0]);
  const lines = [
    headers.join(','),
    ...rows.map((r) =>
      headers
        .map((h) => {
          const v = r[h];
          if (v == null) return '';
          const s = String(v);
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        })
        .join(',')
    ),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const AnalyticsPage = () => {
  const { t } = useLanguage();
  const [timeRange, setTimeRange] = useState('month');

  // Backend-driven data
  const [kpis, setKpis] = useState(null);
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashResult, statsResult, analyticsResult] = await Promise.all([
        adminAnalyticsService.getDashboard(),
        adminAnalyticsService.getStats(),
        adminAnalyticsService.getAnalytics(),
      ]);
      setKpis(dashResult?.kpis || null);
      setStats(statsResult || null);
      setAnalytics(analyticsResult || null);
    } catch (err) {
      setError(err.response?.data?.detail || t('dashboard.loadFailed'));
      console.error('Failed to load analytics data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatNumber = (n) => (n == null ? '0' : Number(n).toLocaleString());

  // Monthly trends: combine user_growth + record_trends from backend
  const monthlyData = (analytics?.user_growth || []).map((item) => {
    const trend = (analytics?.record_trends || []).find((r) => r.month === item.month);
    return {
      month: item.month || '',
      patients: item.active_users || 0,
      records: trend?.records || 0,
    };
  });

  // Users by role -> pie chart
  const roleEntries = Object.entries(stats?.users_by_role || {});
  const departmentData = roleEntries.map(([name, value], index) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: Number(value) || 0,
    color: COLORS[index % COLORS.length],
  }));

  // Records by month -> bar chart
  const recordsByMonthData = (stats?.records_by_month || []).map((item) => ({
    name: item.month || '',
    records: item.count || 0,
  }));

  // Staff activity -> bar chart
  const staffActivityData = (analytics?.staff_activity || []).map((item) => ({
    name: `Staff ${item.staff_id}`,
    managedUsers: item.managed_users || 0,
  }));

  const totalUsers = kpis?.total_users || 0;
  const totalRecords = kpis?.total_records || 0;
  const activeUsers = kpis?.active_users || 0;
  const totalStaff = kpis?.total_staff || 0;

  const monthlyGrowth =
    analytics?.user_growth && analytics.user_growth.length >= 2
      ? Math.max(
          ((analytics.user_growth[analytics.user_growth.length - 1].active_users || 0) -
            (analytics.user_growth[0].active_users || 0)) /
            Math.max(analytics.user_growth[0].active_users || 1, 1) *
            100,
          0
        )
      : null;

  const handleExport = () => {
    const data =
      monthlyData.length > 0
        ? monthlyData
        : recordsByMonthData.map((r) => ({ month: r.name, count: r.records }));
    downloadCSV('analytics.csv', data);
  };

  const timeRangeLabels = {
    week: t('analytics.week'),
    month: t('analytics.month'),
    year: t('analytics.year'),
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('analytics.title')}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {t('analytics.subtitle')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-2">
            {['week', 'month', 'year'].map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  timeRange === range
                    ? 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-lg'
                    : 'backdrop-blur-md bg-white/70 dark:bg-gray-800/70 text-gray-700 dark:text-gray-300 hover:bg-white/90 dark:hover:bg-gray-800/90'
                }`}
              >
                {timeRangeLabels[range]}
              </button>
            ))}
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label={t('common.refresh')}
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <Button
            variant="outline"
            onClick={handleExport}
            className="backdrop-blur-md bg-white/70 dark:bg-gray-800/70"
          >
            <Download className="w-4 h-4 mr-2" />
            {t('analytics.export')}
          </Button>
        </div>
      </div>

      {error && (
        <GlassCard className="p-4 border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/10">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            <button
              onClick={loadData}
              className="px-3 py-1 text-sm font-medium text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/30 rounded hover:bg-red-200 transition-colors"
            >
              {t('common.retry')}
            </button>
          </div>
        </GlassCard>
      )}

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title={t('analytics.totalPatients')}
          value={loading ? '…' : formatNumber(totalUsers)}
          icon={Users}
          trend="up"
          trendValue=""
          color="blue"
        />
        <StatCard
          title={t('analytics.totalRecords')}
          value={loading ? '…' : formatNumber(totalRecords)}
          icon={FileText}
          trend="up"
          trendValue=""
          color="green"
        />
        <StatCard
          title={t('analytics.monthlyGrowth')}
          value={loading ? '…' : monthlyGrowth == null ? '0%' : `${monthlyGrowth.toFixed(1)}%`}
          icon={TrendingUp}
          trend={monthlyGrowth != null && monthlyGrowth > 0 ? 'up' : 'down'}
          trendValue={monthlyGrowth == null ? '' : `${monthlyGrowth >= 0 ? '+' : ''}${monthlyGrowth.toFixed(1)}%`}
          color="purple"
        />
        <StatCard
          title={t('analytics.activeCases')}
          value={loading ? '…' : formatNumber(activeUsers)}
          icon={Activity}
          trend="up"
          trendValue=""
          color="orange"
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Trends - Area Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('analytics.monthlyTrends')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : monthlyData.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={monthlyData}>
                <defs>
                  <linearGradient id="colorPatients" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorRecords" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
                <XAxis dataKey="month" stroke="#9ca3af" />
                <YAxis stroke="#9ca3af" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    border: 'none',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                  }}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="patients"
                  name={t('analytics.totalPatients')}
                  stroke="#3b82f6"
                  fillOpacity={1}
                  fill="url(#colorPatients)"
                />
                <Area
                  type="monotone"
                  dataKey="records"
                  name={t('analytics.totalRecords')}
                  stroke="#10b981"
                  fillOpacity={1}
                  fill="url(#colorRecords)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Users by Role - Pie Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('analytics.departmentDistribution')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : departmentData.every((d) => d.value === 0) ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={departmentData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {departmentData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </GlassCard>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Staff Activity - Bar Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('analytics.weeklyActivity')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : staffActivityData.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={staffActivityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
                <XAxis dataKey="name" stroke="#9ca3af" />
                <YAxis stroke="#9ca3af" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    border: 'none',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                  }}
                />
                <Legend />
                <Bar dataKey="managedUsers" name={t('analytics.activeCases')} fill="#3b82f6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Records by Month - Bar Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('analytics.monthlyTrends')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : recordsByMonthData.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={recordsByMonthData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
                <XAxis dataKey="name" stroke="#9ca3af" />
                <YAxis stroke="#9ca3af" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    border: 'none',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
                  }}
                />
                <Bar dataKey="records" name={t('analytics.totalRecords')} fill="#8b5cf6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </GlassCard>
      </div>

      {/* Performance Metrics */}
      <GlassCard className="p-6">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6">
          {t('analytics.performanceMetrics')}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">{t('analytics.patientSatisfaction')}</span>
              <Calendar className="w-5 h-5 text-blue-500" />
            </div>
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">94.5%</div>
            <div className="w-full bg-blue-200 dark:bg-blue-900/40 rounded-full h-2">
              <div className="bg-blue-500 h-2 rounded-full" style={{ width: '94.5%' }}></div>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">{t('analytics.treatmentSuccess')}</span>
              <Activity className="w-5 h-5 text-green-500" />
            </div>
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">87.2%</div>
            <div className="w-full bg-green-200 dark:bg-green-900/40 rounded-full h-2">
              <div className="bg-green-500 h-2 rounded-full" style={{ width: '87.2%' }}></div>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">{t('analytics.avgWaitTime')}</span>
              <TrendingUp className="w-5 h-5 text-purple-500" />
            </div>
            <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">12 min</div>
            <div className="w-full bg-purple-200 dark:bg-purple-900/40 rounded-full h-2">
              <div className="bg-purple-500 h-2 rounded-full" style={{ width: '75%' }}></div>
            </div>
          </div>
        </div>
      </GlassCard>
    </div>
  );
};

export default AnalyticsPage;

