import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useFocusTrap } from '../hooks/useFocusTrap';

/**
 * Modal - Accessible modal dialog with focus trap
 *
 * Features:
 * - Focus trap (Tab/Shift+Tab cycle within modal)
 * - Escape to close
 * - Focus restoration on close
 * - ARIA attributes
 * - Backdrop click to close (optional)
 */
export default function Modal({
  isOpen,
  onClose,
  children,
  title,
  maxWidth = 'max-w-2xl',
  closeOnBackdrop = true,
}) {
  const modalRef = useRef(null);

  // Focus trap
  useFocusTrap(modalRef, isOpen, onClose);

  // Handle backdrop click
  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget && closeOnBackdrop) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4 backdrop-blur-sm transition-opacity duration-200"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className={`w-full ${maxWidth} max-h-[90vh] flex flex-col rounded-2xl border border-white/50 bg-white shadow-2xl shadow-slate-950/15 dark:border-slate-700 dark:bg-slate-900 motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-95 duration-200`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * ModalHeader - Standard modal header with close button
 */
export function ModalHeader({ title, onClose, children }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-200 p-6 dark:border-slate-700">
      <h2 className="text-xl font-semibold text-slate-900 dark:text-white">{title}</h2>
      <button
        onClick={onClose}
        className="rounded-md text-slate-400 transition-colors hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:hover:text-slate-200"
        aria-label="Close modal"
      >
        <X className="w-6 h-6" />
      </button>
    </div>
  );
}

/**
 * ModalBody - Scrollable modal body
 */
export function ModalBody({ children, className = '' }) {
  return (
    <div className={`flex-1 overflow-y-auto p-6 ${className}`}>
      {children}
    </div>
  );
}

/**
 * ModalFooter - Modal footer with actions
 */
export function ModalFooter({ children, className = '' }) {
  return (
    <div className={`flex items-center justify-end gap-3 border-t border-slate-200 p-6 dark:border-slate-700 ${className}`}>
      {children}
    </div>
  );
}
