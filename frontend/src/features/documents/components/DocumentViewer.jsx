import { useState, useEffect } from 'react';
import { X, Loader, AlertCircle } from 'lucide-react';
import SummaryTab from './SummaryTab';
import AskAITab from './AskAITab';
import MetadataTab from './MetadataTab';
import ObservationsTab from './ObservationsTab';
import Modal from './Modal';

/**
 * DocumentViewer - Modal/page for viewing document details
 *
 * Features:
 * - Deep-linking support (/documents/:id)
 * - Works as modal or standalone page
 * - Tab navigation (Summary | Ask AI | Metadata)
 * - Loading/error states
 * - Accessible (ARIA, keyboard)
 */
export default function DocumentViewer({
  documentId,
  isModal = false,
  onClose,
}) {
  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('summary');

  useEffect(() => {
    if (!documentId) return;

    const fetchDocument = async () => {
      try {
        setLoading(true);
        setError(null);
        const { documentService } = await import('@/app/services/api');
        const result = await documentService.get(documentId);
        if (result.success && result.data) {
          setDocument(result.data);
        } else {
          setError('Document not found');
        }
      } catch (err) {
        setError(err.message || 'Failed to load document');
      } finally {
        setLoading(false);
      }
    };

    fetchDocument();
  }, [documentId]);

  const handleClose = () => {
    if (onClose) onClose();
    // If standalone page, navigate back
    if (!isModal) {
      window.history.back();
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  // Error state
  if (error || !document) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Error</h2>
        <p className="text-gray-600 mb-4">{error || 'Document not found'}</p>
        <button
          onClick={handleClose}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Close
        </button>
      </div>
    );
  }

  // Modal wrapper
  if (isModal) {
    return (
      <Modal
        isOpen={isModal}
        onClose={handleClose}
        title={`Document viewer: ${document.original_filename}`}
        maxWidth="max-w-4xl"
      >
        <DocumentViewerContent
          document={document}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          onClose={handleClose}
        />
      </Modal>
    );
  }

  // Standalone page
  return (
    <div className="max-w-4xl mx-auto">
      <DocumentViewerContent
        document={document}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onClose={handleClose}
      />
    </div>
  );
}

/**
 * DocumentViewerContent - Shared content for modal and page
 */
function DocumentViewerContent({ document, activeTab, setActiveTab, onClose }) {
  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'askai', label: 'Ask AI' },
    { id: 'observations', label: 'Observations' },
    { id: 'metadata', label: 'Metadata' },
  ];

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b">
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-semibold text-gray-900 truncate">
            {document.original_filename}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            {document.mime_type} • {document.file_size ? `${(document.file_size / 1024).toFixed(1)} KB` : 'Unknown size'}
          </p>
        </div>
        <button
          onClick={onClose}
          className="ml-4 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="Close document viewer"
        >
          <X className="w-6 h-6" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-6 border-b" role="tablist">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tab-panel-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'summary' && (
          <div id="tab-panel-summary" role="tabpanel">
            <SummaryTab document={document} />
          </div>
        )}
        {activeTab === 'askai' && (
          <div id="tab-panel-askai" role="tabpanel">
            <AskAITab document={document} />
          </div>
        )}
        {activeTab === 'observations' && (
          <div id="tab-panel-observations" role="tabpanel">
            <ObservationsTab document={document} />
          </div>
        )}
        {activeTab === 'metadata' && (
          <div id="tab-panel-metadata" role="tabpanel">
            <MetadataTab document={document} />
          </div>
        )}
      </div>
    </>
  );
}