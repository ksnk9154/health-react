import { useState } from 'react';
import { Activity, AlertTriangle, FileText, Moon, Scale, Save, LineChart as LineChartIcon, History } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import GlassCard from './GlassCard';
import { weightGoalService } from '../services/api';

const Metric = ({ icon: Icon, label, value }) => (
  <div className="rounded-xl border border-slate-100 p-3 dark:border-slate-700">
    <div className="flex items-center gap-2 text-xs text-slate-500"><Icon className="size-4 text-blue-500" />{label}</div>
    <p className="mt-1 font-semibold text-slate-900 dark:text-white">{value ?? '—'}</p>
  </div>
);
export default function HealthOverview({ data, loading, onRefresh }) {
  const [target, setTarget] = useState('');
  const [saving, setSaving] = useState(false);
  if (loading) return <GlassCard className="p-6">Loading health overview…</GlassCard>;
  if (!data) return null;
  const m = data.metrics;
  const g = data.weight_goal;
  const attention = data.alerts?.length ?? 0;
  const trendEntries = Object.entries(data.trends || {}).filter(([, pts]) => Array.isArray(pts) && pts.length >= 2);
  const comparisons = data.comparisons || [];
  const save = async () => {
    if (!target || Number(target) <= 0) return;
    setSaving(true);
    try { await weightGoalService.save({ target_weight_kg: Number(target) }); onRefresh?.(); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6">
      <GlassCard className="p-6">
        <div className="mb-4 flex items-center gap-2">
          <Activity className="size-5 text-blue-500" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Health Overview</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Metric icon={Scale} label="Latest weight" value={m.latest_weight != null ? `${m.latest_weight} kg` : '—'} />
          <Metric icon={Activity} label="Weight progress" value={m.weight_change != null ? `${m.weight_change > 0 ? '+' : ''}${m.weight_change} kg` : '—'} />
          <Metric icon={Scale} label="Weight goal" value={g ? `${g.target_weight_kg} kg (${g.remaining_kg ?? '—'} kg remaining)` : 'Not set'} />
          <Metric icon={Moon} label="Avg. sleep" value={m.average_sleep != null ? `${m.average_sleep} h` : '—'} />
          <Metric icon={FileText} label="Verified observations" value={m.observation_count} />
          <Metric icon={AlertTriangle} label="Needs attention" value={attention > 0 ? attention : 'None'} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); save(); }} className="mt-4 flex gap-2">
          <input aria-label="Target weight in kilograms" type="number" min="1" max="500" step="0.1" value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={g ? `Update goal (${g.target_weight_kg} kg)` : 'Set target weight (kg)'}
            className="h-9 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-800" />
          <button disabled={saving} className="inline-flex items-center rounded-md bg-blue-600 px-3 text-sm font-medium text-white">
            <Save className="mr-1 size-4" />Save goal
          </button>
        </form>
      </GlassCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <GlassCard className="p-6">
          <h3 className="font-semibold text-slate-900 dark:text-white">Weight trend</h3>
          {data.weight_trend?.length ? (
            <div className="mt-4 h-48">
              <ResponsiveContainer>
                <LineChart data={data.weight_trend}>
                  <XAxis dataKey="date" hide />
                  <YAxis width={35} />
                  <Tooltip />
                  <Line dataKey="value" stroke="#3b82f6" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="py-12 text-center text-sm text-slate-500">Add health records to see weight progress.</p>}
        </GlassCard>

        <GlassCard className="p-6">
          <h3 className="font-semibold text-slate-900 dark:text-white">Report-reference alerts</h3>
          {data.alerts?.length ? (
            <div className="mt-3 space-y-2">
              {data.alerts.map((a) => (
                <div key={a.observation_id} className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                  <AlertTriangle className="mr-2 inline size-4" />{a.title}
                  <p className="mt-1 text-xs">Reported by document{a.document_name ? ` · ${a.document_name}` : ''}{a.source_page ? ` · p. ${a.source_page}` : ''}</p>
                </div>
              ))}
            </div>
          ) : <p className="py-12 text-center text-sm text-slate-500">No report-provided out-of-range flags.</p>}
        </GlassCard>
      </div>
<GlassCard className="p-6">
          <h3 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white"><LineChartIcon className="size-4 text-blue-500" />Verified observation trends</h3>
          {trendEntries.length ? (
            <div className="mt-4 space-y-6">
              {trendEntries.slice(0, 5).map(([name, pts]) => (
                <div key={name} className="rounded-xl border border-slate-100 p-4 dark:border-slate-700">
                  <p className="mb-2 text-sm font-medium text-slate-900 dark:text-white">
                    {name} <span className="text-xs text-slate-500">({pts[0].unit}) · {pts.length} results · {pts[pts.length - 1].document_name || `document ${pts[pts.length - 1].document_id}`}</span>
                  </p>
                  <div className="h-40">
                    <ResponsiveContainer>
                      <LineChart data={pts}>
                        <XAxis dataKey="date" hide />
                        <YAxis width={35} />
                        <Tooltip />
                        <Line dataKey="value" stroke="#0ea5e9" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="py-10 text-center text-sm text-slate-500">Repeated lab values will be charted here once a metric has at least two observations.</p>}
        </GlassCard>

        {comparisons.length ? (
          <GlassCard className="p-6">
            <h3 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white"><History className="size-4 text-blue-500" />Historical comparison</h3>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr><th className="pb-2">Metric</th><th>Previous</th><th>Current</th><th>Change</th><th>Source</th></tr>
                </thead>
                <tbody>
                  {comparisons.map((c, i) => (
                    <tr key={`${c.name}-${i}`} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-2 font-medium text-slate-900 dark:text-white">{c.name}</td>
                      <td>{c.previous} {c.unit}</td>
                      <td>{c.current} {c.unit}</td>
                      <td className={c.change > 0 ? 'text-amber-600' : 'text-emerald-600'}>{c.change > 0 ? '+' : ''}{c.change} {c.unit}</td>
                      <td className="text-xs">{c.document_name || `document ${c.document_id}`}{c.date ? ` · ${c.date}` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        ) : null}
      </div>
  );
}