import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

/**
 * MetadataTab - Display document metadata and properties
 *
 * Features:
 * - Read-only metadata display
 * - Copy checksum
 * - Analysis history is available in the Ask AI tab (History count)
 */
export default function MetadataTab({ document }) {
  const [copiedField, setCopiedField] = useState(null);

  const copyToClipboard = async (text, field) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleString();
  };

  const formatBytes = (bytes) => {
    if (!bytes) return 'Unknown';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* File Properties */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">File Properties</h3>
        <div className="bg-gray-50 rounded-lg p-4 space-y-3">
          <MetadataRow label="File Name" value={document.original_filename} />
          <MetadataRow label="Stored Name" value={document.stored_filename} mono />
          <MetadataRow label="MIME Type" value={document.mime_type} />
          <MetadataRow label="File Size" value={formatBytes(document.file_size)} />
          <MetadataRow label="Checksum (SHA-256)" value={document.checksum} mono copyable onCopy={() => copyToClipboard(document.checksum, 'checksum')} copied={copiedField === 'checksum'} />
          <MetadataRow label="Version" value={document.version?.toString()} />
        </div>
      </div>

      {/* Timestamps */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Timestamps</h3>
        <div className="bg-gray-50 rounded-lg p-4 space-y-3">
          <MetadataRow label="Uploaded" value={formatDate(document.upload_time)} />
          <MetadataRow label="Created" value={formatDate(document.created_at)} />
          <MetadataRow label="Last Updated" value={formatDate(document.updated_at)} />
          <MetadataRow label="Last Accessed" value={formatDate(document.last_accessed)} />
        </div>
      </div>

      {/* Processing Info */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Processing Information</h3>
        <div className="bg-gray-50 rounded-lg p-4 space-y-3">
          <MetadataRow label="Parser Used" value={document.parser_used || 'N/A'} />
          <MetadataRow label="Processing Time" value={document.processing_time_ms ? `${document.processing_time_ms.toFixed(0)}ms` : 'N/A'} />
          <MetadataRow label="Status" value={document.status} />
          {document.error_code && <MetadataRow label="Error Code" value={document.error_code} />}
          {document.error_message && <MetadataRow label="Error Message" value={document.error_message} />}
        </div>
      </div>

      {/* Analysis History */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">AI Analysis History</h3>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
          <p className="text-sm text-blue-800 mb-2">
            AI analysis history is available in the Ask AI tab.
          </p>
          <p className="text-xs text-blue-600">
            Open the Ask AI tab and click the History button to view past
            summaries, explanations, and Q&amp;A results for this document.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * MetadataRow - Single metadata field display
 */
function MetadataRow({ label, value, mono, copyable, onCopy, copied }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <label className="text-sm font-medium text-gray-700 flex-shrink-0">{label}</label>
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <p className={`text-sm text-gray-900 break-all ${mono ? 'font-mono text-xs' : ''}`}>
          {value || 'N/A'}
        </p>
        {copyable && (
          <button
            onClick={onCopy}
            className="flex-shrink-0 p-1 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label={`Copy ${label}`}
          >
            {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
          </button>
        )}
      </div>
    </div>
  );
}