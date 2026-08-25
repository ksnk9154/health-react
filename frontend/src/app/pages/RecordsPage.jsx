import { useEffect, useMemo, useRef, useState } from 'react';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Search, Plus, Edit, Trash2, Eye, RefreshCw, Inbox } from 'lucide-react';
import { toast } from 'sonner';
import { useLanguage } from '../i18n/LanguageContext';
import { recordsService } from '../services/api';

const EMPTY_FORM = {
  record_date: '',
  height_cm: '',
  weight_kg: '',
  food: '',
  calories: '',
  water_liters: '',
  sleep_hours: '',
  exercise: '',
};

const RecordsPage = () => {
  const { t } = useLanguage();
  const [searchTerm, setSearchTerm] = useState('');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [isViewMode, setIsViewMode] = useState(false);

  // Backend-driven state
  const [records, setRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const [formData, setFormData] = useState(EMPTY_FORM);

  // Ref to hold the search debounce timer so it can be cleared on unmount/re-run
  const searchTimerRef = useRef(null);

  const loadRecords = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const resp = await recordsService.getAll({ search: searchTerm });
      // Backend returns an array of records directly
      setRecords(Array.isArray(resp) ? resp : []);
    } catch (err) {
      setLoadError(err.response?.data?.detail || t('records.loadFailed'));
      console.error('Failed to load records', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadRecords();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Clear pending search timer when the component unmounts
  useEffect(() => {
    return () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    };
  }, []);

  const handleSearch = (e) => {
    const value = e.target.value;
    setSearchTerm(value);
    // Debounce search to avoid spamming the API
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchTimerRef.current = setTimeout(() => loadRecords(), 300);
  };

  const handleEdit = (record) => {
    setSelectedRecord(record);
    setFormData({
      record_date: record.record_date || '',
      height_cm: record.height_cm ?? '',
      weight_kg: record.weight_kg ?? '',
      food: record.food || '',
      calories: record.calories ?? '',
      water_liters: record.water_liters ?? '',
      sleep_hours: record.sleep_hours ?? '',
      exercise: record.exercise || '',
    });
    setIsViewMode(false);
    setIsDialogOpen(true);
  };

  const handleView = (record) => {
    setSelectedRecord(record);
    setFormData({
      record_date: record.record_date || '',
      height_cm: record.height_cm ?? '',
      weight_kg: record.weight_kg ?? '',
      food: record.food || '',
      calories: record.calories ?? '',
      water_liters: record.water_liters ?? '',
      sleep_hours: record.sleep_hours ?? '',
      exercise: record.exercise || '',
    });
    setIsViewMode(true);
    setIsDialogOpen(true);
  };

  const handleDelete = async (id) => {
    try {
      await recordsService.delete(id);
      toast.success(t('records.deleted'));
      setRecords((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      toast.error(err.response?.data?.detail || t('records.deleteFailed'));
      console.error('Failed to delete record', err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        record_date: formData.record_date,
        height_cm: formData.height_cm === '' ? null : Number(formData.height_cm),
        weight_kg: formData.weight_kg === '' ? null : Number(formData.weight_kg),
        food: formData.food || null,
        calories: formData.calories === '' ? null : Number(formData.calories),
        water_liters: formData.water_liters === '' ? null : Number(formData.water_liters),
        sleep_hours: formData.sleep_hours === '' ? null : Number(formData.sleep_hours),
        exercise: formData.exercise || null,
      };

      if (selectedRecord) {
        await recordsService.update(selectedRecord.id, payload);
        toast.success(t('records.updated'));
      } else {
        await recordsService.create(payload);
        toast.success(t('records.created'));
      }
      handleCloseDialog();
      await loadRecords();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('records.saveFailed'));
      console.error('Failed to save record', err);
    }
  };

  const handleCloseDialog = () => {
    setIsDialogOpen(false);
    setSelectedRecord(null);
    setIsViewMode(false);
    setFormData(EMPTY_FORM);
  };

  const filteredRecords = useMemo(() => {
    if (!searchTerm.trim()) return records;
    const term = searchTerm.toLowerCase();
    return records.filter((r) => {
      const food = (r.food || '').toLowerCase();
      const exercise = (r.exercise || '').toLowerCase();
      const date = (r.record_date || '').toLowerCase();
      return food.includes(term) || exercise.includes(term) || date.includes(term);
    });
  }, [records, searchTerm]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('records.title')}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            {t('records.subtitle')}
          </p>
        </div>
        <Button
          onClick={() => setIsDialogOpen(true)}
          className="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white shadow-lg"
        >
          <Plus className="w-4 h-4 mr-2" />
          {t('records.addRecord')}
        </Button>
      </div>

      {/* Search and Filters */}
      <GlassCard className="p-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <Input
              placeholder={t('records.searchPlaceholder')}
              value={searchTerm}
              onChange={handleSearch}
              className="pl-10 backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
            />
          </div>
          <Button
            variant="outline"
            onClick={loadRecords}
            disabled={isLoading}
            className="backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            {t('common.retry')}
          </Button>
        </div>
      </GlassCard>

      {/* Records Table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-gray-200/50 dark:border-gray-700/50">
                <TableHead>{t('records.date')}</TableHead>
                <TableHead>{t('records.weight')}</TableHead>
                <TableHead>{t('records.height')}</TableHead>
                <TableHead>{t('records.food')}</TableHead>
                <TableHead>{t('records.calories')}</TableHead>
                <TableHead>{t('records.water')}</TableHead>
                <TableHead>{t('records.sleep')}</TableHead>
                <TableHead>{t('records.exercise')}</TableHead>
                <TableHead className="text-right">{t('records.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-10 text-gray-500 dark:text-gray-400">
                    {t('common.loading')}
                  </TableCell>
                </TableRow>
              ) : loadError ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-10">
                    <p className="text-red-600 dark:text-red-400 mb-3">{loadError}</p>
                    <Button variant="outline" onClick={loadRecords} className="mx-auto">
                      {t('common.retry')}
                    </Button>
                  </TableCell>
                </TableRow>
              ) : filteredRecords.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="py-14 text-center">
                    <Inbox className="mx-auto mb-4 size-11 text-blue-500/60" />
                    <p className="text-base font-semibold text-slate-900 dark:text-white">No health records yet</p>
                    <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">Add your first health record to start tracking your health data.</p>
                    <Button onClick={() => setIsDialogOpen(true)} className="mt-5 bg-gradient-to-r from-blue-500 to-indigo-600 text-white">
                      <Plus className="mr-2 size-4" /> {t('records.addRecord')}
                    </Button>
                  </TableCell>
                </TableRow>
              ) : (
                filteredRecords.map((record) => (
                  <TableRow key={record.id} className="border-gray-200/50 dark:border-gray-700/50">
                    <TableCell className="font-medium">{record.record_date || '—'}</TableCell>
                    <TableCell>{record.weight_kg != null ? `${record.weight_kg} kg` : '—'}</TableCell>
                    <TableCell>{record.height_cm != null ? `${record.height_cm} cm` : '—'}</TableCell>
                    <TableCell>{record.food || '—'}</TableCell>
                    <TableCell>{record.calories != null ? record.calories : '—'}</TableCell>
                    <TableCell>{record.water_liters != null ? `${record.water_liters} L` : '—'}</TableCell>
                    <TableCell>{record.sleep_hours != null ? `${record.sleep_hours} h` : '—'}</TableCell>
                    <TableCell>{record.exercise || '—'}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleView(record)}
                          className="h-8 w-8 p-0"
                          aria-label={t('common.view')}
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEdit(record)}
                          className="h-8 w-8 p-0"
                          aria-label={t('common.edit')}
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDelete(record.id)}
                          className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                          aria-label={t('common.delete')}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </GlassCard>

      {/* Add/Edit Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="backdrop-blur-md bg-white/95 dark:bg-gray-800/95 sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {isViewMode ? t('records.viewRecord') : selectedRecord ? t('records.editRecord') : t('records.addNewRecord')}
            </DialogTitle>
            <DialogDescription>
              {isViewMode
                ? t('records.viewRecordDesc')
                : selectedRecord
                ? t('records.editRecordDesc')
                : t('records.addRecordDesc')}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="record_date">{t('records.date')}</Label>
                <Input
                  id="record_date"
                  type="date"
                  value={formData.record_date}
                  onChange={(e) => setFormData({ ...formData, record_date: e.target.value })}
                  disabled={isViewMode}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="weight_kg">{t('records.weight')}</Label>
                  <Input
                    id="weight_kg"
                    type="number"
                    step="0.1"
                    value={formData.weight_kg}
                    onChange={(e) => setFormData({ ...formData, weight_kg: e.target.value })}
                    disabled={isViewMode}
                    placeholder="70.5"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="height_cm">{t('records.height')}</Label>
                  <Input
                    id="height_cm"
                    type="number"
                    step="0.1"
                    value={formData.height_cm}
                    onChange={(e) => setFormData({ ...formData, height_cm: e.target.value })}
                    disabled={isViewMode}
                    placeholder="175"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="calories">{t('records.calories')}</Label>
                  <Input
                    id="calories"
                    type="number"
                    value={formData.calories}
                    onChange={(e) => setFormData({ ...formData, calories: e.target.value })}
                    disabled={isViewMode}
                    placeholder="2100"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="water_liters">{t('records.water')}</Label>
                  <Input
                    id="water_liters"
                    type="number"
                    step="0.1"
                    value={formData.water_liters}
                    onChange={(e) => setFormData({ ...formData, water_liters: e.target.value })}
                    disabled={isViewMode}
                    placeholder="2.0"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="sleep_hours">{t('records.sleep')}</Label>
                  <Input
                    id="sleep_hours"
                    type="number"
                    step="0.5"
                    value={formData.sleep_hours}
                    onChange={(e) => setFormData({ ...formData, sleep_hours: e.target.value })}
                    disabled={isViewMode}
                    placeholder="7.5"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="food">{t('records.food')}</Label>
                  <Input
                    id="food"
                    value={formData.food}
                    onChange={(e) => setFormData({ ...formData, food: e.target.value })}
                    disabled={isViewMode}
                    placeholder={t('records.foodPlaceholder')}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="exercise">{t('records.exercise')}</Label>
                <Input
                  id="exercise"
                  value={formData.exercise}
                  onChange={(e) => setFormData({ ...formData, exercise: e.target.value })}
                  disabled={isViewMode}
                  placeholder={t('records.exercisePlaceholder')}
                />
              </div>
            </div>
            <DialogFooter>
              {!isViewMode && (
                <>
                  <Button type="button" variant="outline" onClick={handleCloseDialog}>
                    {t('common.cancel')}
                  </Button>
                  <Button type="submit" className="bg-gradient-to-r from-blue-500 to-indigo-600 text-white">
                    {selectedRecord ? t('common.update') : t('common.create')}
                  </Button>
                </>
              )}
              {isViewMode && (
                <Button type="button" onClick={handleCloseDialog}>
                  {t('common.close')}
                </Button>
              )}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RecordsPage;

