import { useState, useCallback } from 'react';
import { AlertTriangle, Plus, RefreshCw, Search, Filter } from 'lucide-react';
import { useDocuments } from '../hooks/useDocuments';
import DocumentList from '../components/DocumentList';
import DocumentUploader from '../components/DocumentUploader';
import DocumentViewer from '../components/DocumentViewer';
import Modal from '../components/Modal';
import { useLanguage } from '@/app/i18n/LanguageContext';

/**
 * DocumentsPage - Main document management page
 *
 * Features:
 * - Document list with search/filter
 * - Upload modal
 * - Document viewer modal
 * - Pagination
 * - Error recovery with retry
 * - Accessible (ARIA, keyboard)
 */
export default function DocumentsPage() {
  const { t } = useLanguage();
  const {
    documents,
    loading,
    error,
    pagination,
    uploading,
    uploadProgress,
    fetchDocuments,
    uploadDocuments,
    deleteDocument,
    extractDocument,
    refresh,
    setError,
  } = useDocuments();

  const [showUploader, setShowUploader] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // Debounced search
  let searchTimeout;
  const handleSearch = (e) => {
    const value = e.target.value;
    setSearchQuery(value);
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      fetchDocuments({ search: value, type: filterType });
    }, 300);
  };

  const handleFilterChange = (e) => {
    const value = e.target.value;
    setFilterType(value);
    fetchDocuments({ search: searchQuery, type: value });
  };

  const handleUpload = async (files) => {
    try {
      await uploadDocuments(files);
      setShowUploader(false);
    } catch (err) {
      // Error handled by hook
    }
  };

  const handleDelete = async (documentId) => {
    try {
      await deleteDocument(documentId);
      setDeleteConfirm(null);
      if (selectedDocument?.id === documentId) {
        setSelectedDocument(null);
      }
    } catch (err) {
      // Error handled by hook
    }
  };

  const handleExtract = async (documentId) => {
    try {
      await extractDocument(documentId);
    } catch (err) {
      // Error handled by hook
    }
  };

  const handleRetry = () => {
    refresh();
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{t('documents.title')}</h1>
            <p className="text-gray-600 mt-1">
              {t('documents.subtitle')}
            </p>
          </div>
          <button
            onClick={() => setShowUploader(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            aria-label={t('documents.upload')}
          >
            <Plus className="w-5 h-5" />
            {t('documents.upload')}
          </button>
        </div>

        {/* Search and Filter */}
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearch}
              placeholder={t('documents.searchPlaceholder')}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label={t('documents.searchPlaceholder')}
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <select
              value={filterType}
              onChange={handleFilterChange}
              className="pl-10 pr-8 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none bg-white"
              aria-label="Filter by file type"
            >
              <option value="">{t('documents.allTypes')}</option>
              <option value="application/pdf">PDF</option>
              <option value="application/vnd.openxmlformats-officedocument.wordprocessingml.document">DOCX</option>
              <option value="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">XLSX</option>
              <option value="text/csv">CSV</option>
              <option value="text/plain">TXT</option>
            </select>
          </div>
          <button
            onClick={refresh}
            className="p-2 text-gray-600 hover:text-gray-900 transition-colors"
            aria-label="Refresh documents"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-red-500">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm text-red-800">{error}</p>
          </div>
          <button
            onClick={handleRetry}
            className="px-3 py-1 text-sm font-medium text-red-700 bg-red-100 rounded hover:bg-red-200 transition-colors"
          >
            {t('common.retry')}
          </button>
        </div>
      )}

      {/* Document List */}
      <DocumentList
        documents={documents}
        loading={loading}
        error={error}
        onSelect={setSelectedDocument}
        onDelete={(id) => setDeleteConfirm(id)}
        onExtract={handleExtract}
        onRetry={handleRetry}
      />

      {/* Pagination */}
      {pagination.total > pagination.per_page && (
        <div className="mt-6 flex items-center justify-between">
          <p className="text-sm text-gray-600">
            {t('documents.showing', {
              from: ((pagination.page - 1) * pagination.per_page) + 1,
              to: Math.min(pagination.page * pagination.per_page, pagination.total),
              total: pagination.total,
            })}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchDocuments({ page: pagination.page - 1 })}
              disabled={pagination.page === 1}
              className="px-3 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('common.previous')}
            </button>
            <span className="text-sm text-gray-600">
              {t('documents.page', {
                current: pagination.page,
                total: Math.ceil(pagination.total / pagination.per_page),
              })}
            </span>
            <button
              onClick={() => fetchDocuments({ page: pagination.page + 1 })}
              disabled={pagination.page >= Math.ceil(pagination.total / pagination.per_page)}
              className="px-3 py-1 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('common.next')}
            </button>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      <DocumentUploader
        isOpen={showUploader}
        onClose={() => setShowUploader(false)}
        onUpload={handleUpload}
        uploading={uploading}
        uploadProgress={uploadProgress}
      />

      {/* Document Viewer Modal */}
      {selectedDocument && (
        <DocumentViewer
          documentId={selectedDocument.id}
          isModal={true}
          onClose={() => setSelectedDocument(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title={t('documents.deleteConfirmation')}
        maxWidth="max-w-md"
      >
        <div className="p-6 text-center">
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400">
            <AlertTriangle className="size-6" aria-hidden="true" />
          </div>
          <h3 className="mb-2 text-xl font-semibold text-slate-900 dark:text-white">{t('documents.deleteTitle')}</h3>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
          {t('documents.deleteConfirm')}
          </p>
        </div>
        <div className="flex flex-col-reverse gap-3 border-t border-slate-200 p-5 sm:flex-row sm:justify-center dark:border-slate-700">
          <button
            onClick={() => setDeleteConfirm(null)}
            className="min-w-32 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 dark:focus-visible:ring-offset-slate-900"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={() => handleDelete(deleteConfirm)}
            className="min-w-32 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          >
            {t('common.delete')}
          </button>
        </div>
      </Modal>
    </div>
  );
}
