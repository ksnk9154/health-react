import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';
import useSpeechRecognition from '../hooks/useSpeechRecognition';

/**
 * VoiceButton — Push-to-talk microphone button
 *
 * States:
 *  - idle:       Mic icon, click to start
 *  - listening:  Red pulsing mic, capturing audio
 *  - processing: Spinner, waiting for transcript
 *  - disabled:   Grayed out, AI is responding
 *  - unsupported: Strikethrough mic, browser can't do STT
 *
 * @param {Object} props
 * @param {(transcript: string) => void} props.onTranscript  Called with final transcript
 * @param {(text: string) => void} [props.onInterim]  Called with live (partial) text while talking
 * @param {(error: string) => void} [props.onError]  Called with the STT error message
 * @param {boolean} [props.disabled=false]  Disable while AI is responding
 * @param {'sm'|'md'|'lg'} [props.size='md']  Button size
 * @param {string} [props.className='']  Additional CSS classes
 */
const VoiceButton = ({
  onTranscript,
  onInterim,
  onError,
  disabled = false,
  size = 'md',
  className = '',
}) => {
  const [processing, setProcessing] = useState(false);
  // The processing timer is tracked in refs so re-renders (e.g. setProcessing)
  // don't cancel the pending finalize timeout.
  const processingRef = useRef(false);
  const timerRef = useRef(null);

  const {
    isListening,
    isSupported,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    resetTranscript,
    error,
  } = useSpeechRecognition({
    language: 'en-US',
    // Keep listening across natural pauses. The hook stops automatically after
    // a ~3.5s silence so the mic doesn't cut off mid-sentence.
    continuous: true,
    interimResults: true,
  });

    // When a final transcript arrives, wait a short delay for the speech-end
  // event to settle, then hand the transcript up and reset. We drive this with
  // a ref guard (not `processing` in the deps) so the re-render from
  // setProcessing(true) doesn't cancel the pending timeout — otherwise the
  // effect cleanup clearTimeout's it, the re-run sees processing===true, skips
  // re-scheduling, and the loading spinner is stuck forever.
  useEffect(() => {
    if (transcript && !isListening && !processingRef.current) {
      processingRef.current = true;
      setProcessing(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        onTranscript(transcript);
        resetTranscript();
        setProcessing(false);
        processingRef.current = false;
        timerRef.current = null;
      }, 300);
    }
  }, [transcript, isListening, onTranscript, resetTranscript]);

  // Clear any pending finalize timeout on unmount.
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  // Live (partial) transcript feedback while talking
  useEffect(() => {
    if (onInterim) {
      onInterim(interimTranscript);
    }
  }, [interimTranscript, onInterim]);

  // Surface errors to the caller (so the page can show a toast) + console
  useEffect(() => {
    if (error) {
      console.warn('VoiceButton error:', error);
      onError?.(error);
    }
  }, [error, onError]);

  const handleClick = useCallback(() => {
    if (disabled || processing) return;

    if (isListening) {
      stopListening();
    } else {
      resetTranscript();
      startListening();
    }
  }, [disabled, processing, isListening, stopListening, resetTranscript, startListening]);

  // Size classes
  const sizeClasses = {
    sm: 'w-8 h-8 p-1.5',
    md: 'w-10 h-10 p-2',
    lg: 'w-12 h-12 p-2.5',
  };

  const iconSizes = {
    sm: 16,
    md: 18,
    lg: 20,
  };

  // Not supported — show disabled button
  if (!isSupported) {
    return (
      <button
        type="button"
        disabled
        title="Speech recognition is not supported in this browser"
        aria-label="Speech recognition not supported"
        className={`inline-flex items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed ${sizeClasses[size]} ${className}`}
      >
        <MicOff size={iconSizes[size]} />
      </button>
    );
  }

  // Disabled state
  if (disabled) {
    return (
      <button
        type="button"
        disabled
        title="Wait for AI response before speaking"
        aria-label="Voice input disabled"
        className={`inline-flex items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed ${sizeClasses[size]} ${className}`}
      >
        <Mic size={iconSizes[size]} />
      </button>
    );
  }

  // Processing state
  if (processing) {
    return (
      <button
        type="button"
        disabled
        title="Processing speech..."
        aria-label="Processing speech"
        className={`inline-flex items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-500 ${sizeClasses[size]} ${className}`}
      >
        <Loader2 size={iconSizes[size]} className="animate-spin" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      title={isListening ? 'Click to stop recording' : error ? `Mic error: ${error}` : 'Click to speak'}
      aria-label={isListening ? 'Stop recording' : 'Start recording'}
      aria-pressed={isListening}
      className={`
        inline-flex items-center justify-center rounded-lg transition-all duration-200
        ${sizeClasses[size]}
        ${
          isListening
            ? 'bg-red-500 text-white shadow-lg shadow-red-500/30 scale-110 animate-pulse'
            : error
              ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 ring-2 ring-red-400'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 hover:scale-105'
        }
        ${className}
      `}
    >
      {isListening ? (
        <Mic size={iconSizes[size]} className="text-white" />
      ) : error ? (
        <MicOff size={iconSizes[size]} />
      ) : (
        <Mic size={iconSizes[size]} />
      )}
    </button>
  );
};

export default VoiceButton;