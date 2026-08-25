import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * useSpeechRecognition
 *
 * Wraps the browser Web Speech API (SpeechRecognition) into a React hook.
 * Designed for future replacement: a backend Whisper-based recognizer can
 * swap in by implementing the same interface { startListening, stopListening,
 * isListening, isSupported, transcript, interimTranscript, error }.
 *
 * @param {Object} options
 * @param {string}  [options.language='en-US']  BCP 47 language tag
 * @param {boolean} [options.continuous=false]  Keep listening after first result
 * @param {boolean} [options.interimResults=true] Return partial results
 * @returns {{
 *   isListening: boolean,
 *   isSupported: boolean,
 *   transcript: string,
 *   interimTranscript: string,
 *   startListening: () => void,
 *   stopListening: () => void,
 *   resetTranscript: () => void,
 *   error: string | null,
 * }}
 */
export default function useSpeechRecognition(options = {}) {
  const {
    language = 'en-US',
    continuous = false,
    interimResults = true,
  } = options;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [error, setError] = useState(null);
  const [isSupported, setIsSupported] = useState(false);

  const recognitionRef = useRef(null);
  const finalTranscriptRef = useRef('');
  const interimTranscriptRef = useRef('');

  // Detect browser support once on mount
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    setIsSupported(Boolean(SpeechRecognition));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore abort errors on unmount
        }
      }
    };
  }, []);

  const startListening = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError('Speech recognition is not supported in this browser.');
      return;
    }

    // Abort any existing session before starting a new one
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language;
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.maxAlternatives = 1;

    // Nothing to emit until we have real text
    setTranscript('');
    setInterimTranscript('');
    finalTranscriptRef.current = '';
    interimTranscriptRef.current = '';

    // Silence / safety timers so recognition can never hang in "loading".
    let silenceTimer = null;
    let maxDurationTimer = null;
    const clearTimers = () => {
      if (silenceTimer) clearTimeout(silenceTimer);
      if (maxDurationTimer) clearTimeout(maxDurationTimer);
      silenceTimer = null;
      maxDurationTimer = null;
    };

    const scheduleSilenceStop = () => {
      if (silenceTimer) clearTimeout(silenceTimer);
      // ~3.5s with no new audio/result => user has finished speaking, so stop
      // so onend() finalizes the result. (Long enough to allow natural pauses
      // between words/sentences without turning the mic off mid-speech.)
      silenceTimer = setTimeout(() => {
        try {
          recognition.stop();
        } catch {
          // ignore
        }
      }, 3500);
    };

    const finalizeOnStop = () => {
      clearTimers();
      // If the engine never delivered a final result (happens on some
      // browsers/Android), promote the latest interim text so we don't lose it.
      if (!finalTranscriptRef.current && interimTranscriptRef.current) {
        finalTranscriptRef.current = interimTranscriptRef.current.trim();
        setTranscript(finalTranscriptRef.current);
      }
      setInterimTranscript('');
      interimTranscriptRef.current = '';
    };

    recognition.onstart = () => {
      // Safety cap: never allow a single session to run longer than 15s.
      maxDurationTimer = setTimeout(() => {
        try {
          recognition.stop();
        } catch {
          // ignore
        }
      }, 15000);
      scheduleSilenceStop();
    };

    recognition.onresult = (event) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final) {
        finalTranscriptRef.current +=
          (finalTranscriptRef.current ? ' ' : '') + final;
        setTranscript(finalTranscriptRef.current);
        interimTranscriptRef.current = '';
        setInterimTranscript('');

        // If not continuous, stop after first final result (onend will fire).
        if (!continuous) {
          try {
            recognition.stop();
          } catch {
            // ignore
          }
          return;
        }
      }

      if (interim) {
        interimTranscriptRef.current = interim;
        setInterimTranscript(interim);
      } else {
        setInterimTranscript('');
      }

      scheduleSilenceStop();
    };

    recognition.onerror = (event) => {
      if (event.error === 'no-speech') {
        // No speech detected — common, don't treat as a hard error.
        return;
      }
      if (event.error === 'aborted') {
        // User or component stopped — ignore.
        return;
      }
      setError(`Speech recognition error: ${event.error}`);
      setIsListening(false);
    };

    recognition.onend = () => {
      finalizeOnStop();
      setIsListening(false);
      recognitionRef.current = null;
    };

    recognition.onspeechend = () => {
      // If continuous, don't stop; onend fires when recognition actually stops.
      if (!continuous) {
        try {
          recognition.stop();
        } catch {
          // ignore
        }
      }
    };

    try {
      recognition.start();
      setIsListening(true);
      setError(null);
      recognitionRef.current = recognition;
    } catch (err) {
      clearTimers();
      setError(`Failed to start speech recognition: ${err.message}`);
      setIsListening(false);
    }
  }, [language, continuous, interimResults]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore if already stopped
      }
      recognitionRef.current = null;
    }
    setIsListening(false);
  }, []);

  const resetTranscript = useCallback(() => {
    finalTranscriptRef.current = '';
    interimTranscriptRef.current = '';
    setTranscript('');
    setInterimTranscript('');
    setError(null);
  }, []);

  return {
    isListening,
    isSupported,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    resetTranscript,
    error,
  };
}