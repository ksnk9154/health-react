import { useEffect, useMemo, useState } from 'react';
import GlassCard from '../components/GlassCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { Badge } from '../components/ui/badge';
import { Search, Filter, Download, Eye, RefreshCw, Inbox } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { recordsService, staffService, exportsService } from '../services/api';

// Fallback for browsers that don't trigger download via anchor click for blob responses
const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const StaffRecordsPage = () => {
  const { t } = useLanguage();
  const [searchTerm, setSearchTerm] = useState('');

  // Backend-driven state
  const [records, setRecords] = useState([]);
  const [assignedUsers, setAssignedUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);

  // Map user_id -> username from /admin/staff/assigned
  const userMap = useMemo(() => {
    const map = {};
    (Array.isArray(assignedUsers) ? assignedUsers : []).forEach((u) => {
      map[u.id] = u.username;
    });
    return map;
  }, [assignedUsers]);

  const loadData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [recordsResult, assignedResult] = await Promise.allSettled([
        recordsService.getAll({ search: searchTerm }),
        staffService.getAssignedUsers(),
      ]);
      if (recordsResult.status === 'fulfilled') {
        setRecords(Array.isArray(recordsResult.value) ? recordsResult.value : []);
      } else {
        setLoadError(recordsResult.reason?.response?.data?.detail || t('records.loadFailed'));
      }
      if (assignedResult.status === 'fulfilled') {
        setAssignedUsers(Array.isArray(assignedResult.value) ? assignedResult.value : []);
      }
    } catch (err) {
      setLoadError(err.response?.data?.detail || t('records.loadFailed'));
      console.error('Failed to load staff records', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    loadData();
  };

  const handleExport = async () => {
    try {
      const blob = await exportsService.recordsCSV();
      downloadBlob(blob, 'records.csv');
    } catch (err) {
      console.error('Failed to export records', err);
    }
  };

  const getStatusBadge = (status) => {
    const styles = {
      completed: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
      'in-progress': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
    };
    return styles[status] || styles.pending;
  };

  const getStatusLabel = (status) => {
    if (status === 'completed') return t('staffRecords.completed');
    if (status === 'pending') return t('staffRecords.pending');
    if (status === 'in-progress') return t('staffRecords.inProgress');
    return status;
  };

  // Derive "status" from record content: has data -> active, otherwise pending
  const getRecordStatus = (record) => {
    const hasData =
      record.weight_kg != null ||
      record.height_cm != null ||
      record.calories != null ||
      record.water_liters != null ||
      record.sleep_hours != null ||
      record.food ||
      record.exercise;
    return hasData ? 'completed' : 'pending';
  };

  const enrichedRecords = records.map((r) => ({
    ...r,
    patientName: userMap[r.user_id] || `User #${r.user_id}`,
    status: getRecordStatus(r),
  }));

  const filteredRecords = enrichedRecords.filter((record) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      String(record.id).includes(term) ||
      String(record.user_id).includes(term) ||
      (record.patientName || '').toLowerCase().includes(term) ||
      (record.record_date || '').toLowerCase().includes(term) ||
      (record.food || '').toLowerCase().includes(term) ||
      (record.exercise || '').toLowerCase().includes(term)
    );
  });

  const totalRecords = records.length;
  const completedCount = records.filter((r) => getRecordStatus(r) === 'completed').length;
  const pendingCount = records.filter((r) => getRecordStatus(r) === 'pending').length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('staffRecords.title')}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {t('staffRecords.subtitle')}
          </p>
        </div>
        <Button
          onClick={handleExport}
          className="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white shadow-lg"
        >
          <Download className="w-4 h-4 mr-2" />
          {t('staffRecords.exportRecords')}
        </Button>
      </div>

      {/* Search and Filters */}
      <GlassCard className="p-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <Input
              placeholder={t('staffRecords.searchPlaceholder')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
            />
          </div>
          <Button
            variant="outline"
            onClick={loadData}
            disabled={isLoading}
            className="backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            {t('common.retry')}
          </Button>
          <Button variant="outline" className="backdrop-blur-sm bg-white/50 dark:bg-gray-800/50">
            <Filter className="w-4 h-4 mr-2" />
            {t('common.filters')}
          </Button>
        </div>
      </GlassCard>

      {/* Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <GlassCard className="p-6">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{t('staffRecords.totalRecords')}</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {isLoading ? '…' : totalRecords}
          </p>
        </GlassCard>
        <GlassCard className="p-6">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{t('staffRecords.completed')}</p>
          <p className="text-3xl font-bold text-green-600">
            {isLoading ? '…' : completedCount}
          </p>
        </GlassCard>
        <GlassCard className="p-6">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{t('staffRecords.pending')}</p>
          <p className="text-3xl font-bold text-yellow-600">
            {isLoading ? '…' : pendingCount}
          </p>
        </GlassCard>
        <GlassCard className="p-6">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{t('staffRecords.inProgress')}</p>
          <p className="text-3xl font-bold text-blue-600">
            {isLoading ? '…' : 0}
          </p>
        </GlassCard>
      </div>

      {/* Records Table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-gray-200/50 dark:border-gray-700/50">
                <TableHead>{t('staffRecords.recordId')}</TableHead>
                <TableHead>{t('staffRecords.patientId')}</TableHead>
                <TableHead>{t('staffRecords.patientName')}</TableHead>
                <TableHead>{t('staffRecords.type')}</TableHead>
                <TableHead>{t('staffRecords.date')}</TableHead>
                <TableHead>{t('staffRecords.assignedTo')}</TableHead>
                <TableHead>{t('staffRecords.status')}</TableHead>
                <TableHead className="text-right">{t('staffRecords.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-gray-500 dark:text-gray-400">
                    {t('common.loading')}
                  </TableCell>
                </TableRow>
              ) : loadError ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10">
                    <p className="text-red-600 dark:text-red-400 mb-3">{loadError}</p>
                    <Button variant="outline" onClick={loadData} className="mx-auto">
                      {t('common.retry')}
                    </Button>
                  </TableCell>
                </TableRow>
              ) : filteredRecords.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-gray-500 dark:text-gray-400">
                    <Inbox className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    {t('records.noRecords')}
                  </TableCell>
                </TableRow>
              ) : (
                filteredRecords.map((record) => (
                  <TableRow key={record.id} className="border-gray-200/50 dark:border-gray-700/50">
                    <TableCell className="font-medium">REC{String(record.id).padStart(3, '0')}</TableCell>
                    <TableCell>P{String(record.user_id).padStart(3, '0')}</TableCell>
                    <TableCell>{record.patientName}</TableCell>
                    <TableCell>{record.food || record.exercise || '—'}</TableCell>
                    <TableCell>{new Date(record.record_date).toLocaleDateString()}</TableCell>
                    <TableCell>{userMap[record.user_id] ? 'Assigned' : '—'}</TableCell>
                    <TableCell>
                      <Badge className={getStatusBadge(record.status)}>
                        {getStatusLabel(record.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0"
                        aria-label={t('common.view')}
                      >
                        <Eye className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </GlassCard>
    </div>
  );
};

export default StaffRecordsPage;

