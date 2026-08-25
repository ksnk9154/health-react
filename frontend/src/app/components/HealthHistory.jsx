import { useEffect, useMemo, useState } from 'react';
import { Filter, FlaskConical } from 'lucide-react';
import GlassCard from './GlassCard';
import { healthObservationService } from '../services/api';

const STATUS_OPTIONS = ['HIGH', 'LOW', 'ABNORMAL', 'NORMAL', 'UNKNOWN'];

// Highlight statuses reported by the source document as out of range.
const tone = (status) => {
  if (status === 'HIGH' || status === 'LOW' || status === 'ABNORMAL') return 'font-medium text-amber-600';
  return 'text-slate-500';
};

export default function HealthHistory() {
  const [rows, setRows] = useState([]);
  const [category, setCategory] = useState('');
  const [test, setTest] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    healthObservationService.list({
      ...(category && { category }),
      ...(test && { name: test }),
      ...(status && { status }),
    }).then(setRows).catch(() => setError('Unable to load verified health data.'));
  }, [category, test, status]);

  const categories = useMemo(() => [...new Set(rows.map((r) => r.category))], [rows]);

  return (
    <GlassCard className="p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-white">
            <FlaskConical className="size-5 text-blue-500" />Health History
          </h2>
          <p className="mt-1 text-xs text-slate-500">Verified values extracted from uploaded documents.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={test} onChange={(e) => setTest(e.target.value)} placeholder="Filter test"
            className="w-28 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800" />
          <label className="flex items-center gap-2 text-sm">
            <Filter className="size-4" />
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800">
              <option value="">All categories</option>
              {categories.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter status"
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800">
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr><th className="pb-2">Test</th><th>Result</th><th>Status</th><th>Date</th><th>Source</th></tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-medium text-slate-900 dark:text-white">
                    {r.name}
                    <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] dark:bg-slate-800">{r.category}</span>
                  </td>
                  <td>
                    {r.value_text || r.value_numeric} {r.unit}
                    <div className="text-xs text-slate-500">{r.reference_text || 'No reported reference'}</div>
                  </td>
                  <td><span className={tone(r.status)}>{r.status}</span></td>
                  <td>{r.observation_date || '—'}</td>
                  <td className="text-xs">
                    {r.document_name || `Document ${r.document_id}`}{r.source_page ? `, p. ${r.source_page}` : ''}
                    <div className="text-slate-500">{r.confidence} confidence</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="py-10 text-center text-sm text-slate-500">No structured health data was detected in your documents yet.</div>
      )}
    </GlassCard>
  );
}