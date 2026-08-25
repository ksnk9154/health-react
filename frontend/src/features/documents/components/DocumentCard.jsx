import { FileText, Trash2, Eye, RefreshCw } from 'lucide-react';

/**
 * DocumentCard - Individual document display card
 *
 * Features:
 * - File type icon (color-coded)
 * - File name, size, upload date
 * - Status badge
 * - Action buttons (view, extract, delete)
 * - Hover effects
 * - Keyboard accessible
 */
export default function DocumentCard({
  document,
  onSelect,
  onDelete,
  onExtract,
}) {
  const getFileIcon = () => {
    const ext = document.original_filename?.split('.').pop()?.toLowerCase();
    const iconColor = {
      pdf: 'text-red-500',
      docx: 'text-blue-500',
      doc: 'text-blue-500',
      xlsx: 'text-green-500',
      xls: 'text-green-500',
      csv: 'text-orange-500',
      txt: 'text-gray-500',
    }[ext] || 'text-gray-400';

    return <FileText className={`w-8 h-8 ${iconColor}`} />;
  };

  const getStatusBadge = () => {
    const statusConfig = {
      UPLOADED: { color: 'bg-gray-100 text-gray-700', label: 'Uploaded' },
      EXTRACTING: { color: 'bg-blue-100 text-blue-700', label: 'Extracting' },
      READY: { color: 'bg-green-100 text-green-700', label: 'Ready' },
      FAILED: { color: 'bg-red-100 text-red-700', label: 'Failed' },
    };

    const config = statusConfig[document.status] || statusConfig.UPLOADED;

    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${config.color}`}>
        <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
        {config.label}
      </span>
    );
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect?.(document);
    }
  };

  return (
    <div
      className="group cursor-pointer rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-900"
      onClick={() => onSelect?.(document)}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="button"
      aria-label={`View document: ${document.original_filename}`}
    >
      {/* Header: Icon + Status */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {getFileIcon()}
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white truncate" title={document.original_filename}>
              {document.original_filename}
            </h3>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {formatFileSize(document.file_size)}
            </p>
          </div>
        </div>
        {getStatusBadge()}
      </div>

      {/* Meta */}
      <div className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        Uploaded {formatDate(document.upload_time)}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect?.(document);
          }}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 rounded hover:bg-blue-100 transition-colors"
          aria-label={`View ${document.original_filename}`}
        >
          <Eye className="w-3 h-3 inline mr-1" />
          View
        </button>

        {document.status !== 'EXTRACTING' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onExtract?.(document.id);
            }}
            className={`flex-1 px-3 py-1.5 text-xs font-medium ${document.status === 'READY' ? 'text-blue-600 bg-blue-50 hover:bg-blue-100' : 'text-green-600 bg-green-50 hover:bg-green-100'} rounded hover:opacity-80 transition-colors`}
            aria-label={`${document.status === 'READY' ? 'Re-extract observations from' : 'Extract'} ${document.original_filename}`}
          >
            <RefreshCw className="w-3 h-3 inline mr-1" />
            {document.status === 'READY' ? 'Re-extract' : 'Extract'}
          </button>
        )}

        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete?.(document.id);
          }}
          className="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded hover:bg-red-100 transition-colors"
          aria-label={`Delete ${document.original_filename}`}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
