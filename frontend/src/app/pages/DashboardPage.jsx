import { useEffect, useState } from 'react';
import GlassCard from '../components/GlassCard';
import StatCard from '../components/StatCard';
import { Users, FileText, Activity, TrendingUp, Calendar, Clock, RefreshCw } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useLanguage } from '../i18n/LanguageContext';
import { adminAnalyticsService } from '../services/api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'];

const DashboardPage = () => {
  const { t } = useLanguage();
  const [timeRange, setTimeRange] = useState('week');

  // Backend-driven data
  const [kpis, setKpis] = useState(null);
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashResult, statsResult, analyticsResult, activityResult] = await Promise.all([
        adminAnalyticsService.getDashboard(),
        adminAnalyticsService.getStats(),
        adminAnalyticsService.getAnalytics(),
        adminAnalyticsService.getRecentActivity(),
      ]);
      setKpis(dashResult?.kpis || null);
      setStats(statsResult || null);
      setAnalytics(analyticsResult || null);
      setRecentActivity(Array.isArray(activityResult) ? activityResult : []);
    } catch (err) {
      setError(err.response?.data?.detail || t('dashboard.loadFailed'));
      console.error('Failed to load dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatNumber = (n) => (n == null ? '0' : Number(n).toLocaleString());

  // Derive chart data from backend stats/analytics
  const lineChartData = (analytics?.user_growth || []).map((item) => ({
    name: item.month || '',
    patients: item.active_users || 0,
    records: 0,
  })) || [];

  const barChartData = (stats?.records_by_month || []).map((item) => ({
    name: item.month || '',
    value: item.count || 0,
  }));

  // Pie chart: users by role (fallback to a generic breakdown if unavailable)
  const pieChartData = Object.entries(stats?.users_by_role || {}).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: Number(value) || 0,
  }));
  const pieChartDataSafe = pieChartData.length > 0
    ? pieChartData
    : [
        { name: t('dashboard.totalPatients'), value: kpis?.total_users || 0 },
        { name: t('dashboard.activeRecords'), value: kpis?.total_records || 0 },
      ];

  const timeRangeLabels = {
    day: t('dashboard.day'),
    week: t('dashboard.week'),
    month: t('dashboard.month'),
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('dashboard.title')}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {t('dashboard.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-2">
            {['day', 'week', 'month'].map((range) => (
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

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title={t('dashboard.totalPatients')}
          value={loading ? '…' : formatNumber(kpis?.total_users)}
          icon={Users}
          trend="up"
          trendValue=""
          color="blue"
        />
        <StatCard
          title={t('dashboard.activeRecords')}
          value={loading ? '…' : formatNumber(kpis?.total_records)}
          icon={FileText}
          trend="up"
          trendValue=""
          color="green"
        />
        <StatCard
          title={t('dashboard.activeUsers')}
          value={loading ? '…' : formatNumber(kpis?.active_users)}
          icon={Activity}
          trend="up"
          trendValue=""
          color="purple"
        />
        <StatCard
          title={t('dashboard.totalStaff')}
          value={loading ? '…' : formatNumber(kpis?.total_staff)}
          icon={Calendar}
          trend="up"
          trendValue=""
          color="orange"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* User Growth / Records Trend - Line Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('dashboard.weeklyTrends')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : lineChartData.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={lineChartData}>
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
                <Line type="monotone" dataKey="patients" stroke="#3b82f6" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Users by Role - Pie Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('dashboard.departmentDistribution')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : pieChartDataSafe.every((d) => d.value === 0) ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={pieChartDataSafe}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {pieChartDataSafe.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Records by Month - Bar Chart */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('dashboard.monthlyRecords')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : barChartData.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barChartData}>
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
                <Bar dataKey="value" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Recent Activity */}
        <GlassCard className="p-6">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            {t('dashboard.recentActivity')}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('common.loading')}
            </div>
          ) : recentActivity.length === 0 ? (
            <div className="flex items-center justify-center h-[300px] text-gray-500 dark:text-gray-400">
              {t('dashboard.noData')}
            </div>
          ) : (
            <div className="space-y-4">
              {recentActivity.map((activity) => (
                <div
                  key={activity.record_id}
                  className="flex items-start gap-3 p-3 rounded-lg hover:bg-white/50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <div className="w-2 h-2 mt-2 rounded-full bg-blue-500"></div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 dark:text-white font-medium truncate">
                      {activity.username}
                    </p>
                    <p className="text-xs text-gray-600 dark:text-gray-400">
                      {t('dashboard.recordAdded')}
                      {activity.weight_kg != null ? ` · ${activity.weight_kg} kg` : ''}
                      {activity.bmi != null ? ` · BMI ${activity.bmi}` : ''}
                    </p>
                    <div className="flex items-center gap-1 mt-1">
                      <Clock className="w-3 h-3 text-gray-400" />
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {activity.record_date}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {/* Quick Actions */}
      <GlassCard className="p-6">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
          {t('dashboard.quickActions')}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { title: t('dashboard.addPatient'), icon: Users, color: 'blue' },
            { title: t('dashboard.newRecord'), icon: FileText, color: 'green' },
            { title: t('dashboard.schedule'), icon: Calendar, color: 'purple' },
            { title: t('dashboard.reports'), icon: TrendingUp, color: 'orange' }
          ].map((action) => {
            const colorClasses = {
              blue: 'from-blue-500 to-blue-600',
              green: 'from-green-500 to-green-600',
              purple: 'from-purple-500 to-purple-600',
              orange: 'from-orange-500 to-orange-600'
            };

            return (
              <button
                key={action.title}
                className="p-4 rounded-xl backdrop-blur-md bg-white/50 dark:bg-gray-800/50 hover:bg-white/70 dark:hover:bg-gray-800/70 transition-all hover:scale-105"
              >
                <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${colorClasses[action.color]} flex items-center justify-center mb-3 mx-auto`}>
                  <action.icon className="w-6 h-6 text-white" />
                </div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {action.title}
                </p>
              </button>
            );
          })}
        </div>
      </GlassCard>
    </div>
  );
};

export default DashboardPage;

