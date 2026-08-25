import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { healthObservationService } from '@/app/services/api';

const tone = (status) => {
  if (status === 'HIGH' || status === 'LOW' || status === 'ABNORMAL') return 'text-amber-600 font-medium';
  return 'text-slate-500';
};

/**
 * ObservationsTab - Lists the verified observations extracted from this document.
 *
 * Every entry is source data (value + reference range + reported status) that came
 * straight from the uploaded file. AI explanations are intentionally NOT shown here
 * (they live in the Ask AI tab) so structured source data is never confused with
 * generated text.
 */
export default function ObservationsTab({ document }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!document?.id) return;
    setLoading(true);
    setError('');
    healthObservationService.list({ document_id: document.id })
      .then(setRows)
      .catch(() => setError('Unable to load verified observations for this document.'))
      .finally(() => setLoading(false));
  }, [document?.id]);

  const flagged = rows.filter((r) => ['HIGH', 'LOW', 'ABNORMAL'].includes(r.status));

  return (
    <div>
      <div className="mb-3 text-sm text-slate-600 dark:text-slate-300">
        Structured measurements extracted deterministically from <span className="font-medium">{document.original_filename}</span>.
        {flagged.length ? ` ${flagged.length} flagged as out of range by the document.` : ' No out-of-range flags were reported by the document.'}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading verified observations…</p>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : rows.length ? (
        <div className="overflow-x-auto rounded-lg border border-slate-100 dark:border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="p-2">Test</th><th>Category</th><th>Result</th><th>Reference</th>
                <th>Status</th><th>Confidence</th><th>Page</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="p-2 font-medium text-slate-900 dark:text-white">{r.name}</td>
                  <td className="p-2">{r.category}</td>
                  <td className="p-2">{r.value_text || r.value_numeric} {r.unit}</td>
                  <td className="p-2 text-xs text-slate-500">{r.reference_text || '—'}</td>
                  <td className="p-2"><span className={tone(r.status)}>{r.status}</span></td>
                  <td className="p-2 text-xs">{r.confidence}</td>
                  <td className="p-2 text-xs">{r.source_page ? `p. ${r.source_page}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="py-10 text-center text-sm text-slate-500">
          <FlaskConical className="mx-auto size-8 text-slate-400" />
          No structured health observations were detected in this document.
        </div>
      )}
    </div>
  );
}