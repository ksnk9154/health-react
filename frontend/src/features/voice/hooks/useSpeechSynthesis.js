import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * useSpeechSynthesis
 *
 * Wraps the browser SpeechSynthesis API into a React hook.
 * Designed for future replacement: a backend TTS engine (gTTS, Piper) can
 * swap in by implementing the same interface { speak, cancel, isSpeaking,
 * isSupported }.
 *
 * @param {Object} options
 * @param {number} [options.rate=1.0]    Speaking rate (0.1 to 10)
 * @param {number} [options.pitch=1.0]   Voice pitch (0 to 2)
 * @param {SpeechSynthesisVoice|null} [options.voice=null]  Specific voice
 * @returns {{
 *   speak: (text: string) => void,
 *   cancel: () => void,
 *   isSpeaking: boolean,
 *   isSupported: boolean,
 *   pause: () => void,
 *   resume: () => void,
 *   setVoice: (voice: SpeechSynthesisVoice) => void,
 *   setRate: (rate: number) => void,
 *   setPitch: (pitch: number) => void,
 *   voices: SpeechSynthesisVoice[],
 *   selectedVoice: SpeechSynthesisVoice | null,
 * }}
 */
export default function useSpeechSynthesis(options = {}) {
  const { rate: initialRate = 1.0, pitch: initialPitch = 1.0, voice: initialVoice = null } = options;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [voices, setVoices] = useState([]);
  const [selectedVoice, setSelectedVoice] = useState(initialVoice);
  const [currentRate, setCurrentRate] = useState(initialRate);
  const [currentPitch, setCurrentPitch] = useState(initialPitch);

  const utteranceRef = useRef(null);
  const speakingRef = useRef(false);
  const cancelledRef = useRef(false);

  // Detect browser support and load voices (with retry).
  // On some browsers/Android WebView, getVoices() returns [] on the first call
  // and the "voiceschanged" event never fires, so we also poll a few times.
  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      'speechSynthesis' in window &&
      typeof window.SpeechSynthesisUtterance !== 'undefined';
    setIsSupported(supported);

    if (!supported) return;

    let retries = 0;
    const MAX_RETRIES = 30; // ~1.5s total of polling

    const applyVoices = (available) => {
      if (!available || available.length === 0) return;
      setVoices(available);
      // Revalidate the currently selected voice. If it no longer exists we drop
      // it so the browser falls back to its system default instead of silently
      // failing on an unavailable voice.
      setSelectedVoice((current) => {
        if (!current) return null;
        const stillExists = available.some(
          (v) => v.name === current.name && v.lang === current.lang
        );
        return stillExists ? current : null;
      });
    };

    const loadVoices = () => {
      const available = window.speechSynthesis.getVoices();
      if (available && available.length > 0) {
        applyVoices(available);
        return true;
      }
      return false;
    };

    let loaded = loadVoices();
    if (!loaded) {
      const timer = setInterval(() => {
        retries += 1;
        loaded = loadVoices();
        if (loaded || retries >= MAX_RETRIES) {
          clearInterval(timer);
        }
      }, 50);
      return () => clearInterval(timer);
    }

    // Chrome loads voices asynchronously; listen for the voiceschanged event.
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const speak = useCallback(
    (text) => {
      if (!isSupported || !text) return;

      const synth = window.speechSynthesis;
      // Cancel any ongoing speech first
      synth.cancel();
      speakingRef.current = false;
      cancelledRef.current = false;
      setIsSpeaking(false);

      // Split long text into sentences for more natural pauses
      const sentences = String(text).match(/[^.!?\n]+[.!?\n]*/g) || [String(text)];
      if (sentences.length === 0) return;

      // Only assign a voice if it is actually still available, otherwise let the
      // browser use its system default (more reliable across devices/Android).
      const voiceToUse =
        selectedVoice &&
        voices.some((v) => v.name === selectedVoice.name && v.lang === selectedVoice.lang)
          ? selectedVoice
          : null;

      const speakNext = (index) => {
        if (cancelledRef.current) return;
        if (index >= sentences.length) {
          speakingRef.current = false;
          setIsSpeaking(false);
          return;
        }

        const utterance = new SpeechSynthesisUtterance(sentences[index].trim());
        if (voiceToUse) utterance.voice = voiceToUse;
        utterance.rate = currentRate;
        utterance.pitch = currentPitch;
        utterance.lang = voiceToUse ? voiceToUse.lang : utterance.lang || 'en-US';

        utterance.onstart = () => {
          if (cancelledRef.current) return;
          speakingRef.current = true;
          setIsSpeaking(true);
        };

        utterance.onend = () => {
          if (cancelledRef.current) return;
          // Small delay between sentences avoids a known Chromium/Android bug
          // where utterances queued back-to-back (or right after cancel())
          // are silently dropped.
          setTimeout(() => speakNext(index + 1), 60);
        };

        utterance.onerror = (event) => {
          // Don't treat cancel/interrupt as a real error.
          if (event.error === 'canceled' || event.error === 'interrupted') {
            speakNext(index + 1);
            return;
          }
          console.warn('Speech synthesis error:', event.error);
          setTimeout(() => speakNext(index + 1), 60);
        };

        utteranceRef.current = utterance;
        synth.speak(utterance);
      };

      speakNext(0);
    },
    [isSupported, selectedVoice, voices, currentRate, currentPitch],
  );

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    speakingRef.current = false;
    setIsSpeaking(false);
  }, []);

  const pause = useCallback(() => {
    if (window.speechSynthesis && speakingRef.current) {
      window.speechSynthesis.pause();
    }
  }, []);

  const resume = useCallback(() => {
    if (window.speechSynthesis && speakingRef.current) {
      window.speechSynthesis.resume();
    }
  }, []);

  const setVoice = useCallback((voice) => {
    setSelectedVoice(voice);
  }, []);

  const setRate = useCallback((rate) => {
    setCurrentRate(Math.max(0.1, Math.min(10, rate)));
  }, []);

  const setPitch = useCallback((pitch) => {
    setCurrentPitch(Math.max(0, Math.min(2, pitch)));
  }, []);

  return {
    speak,
    cancel,
    isSpeaking,
    isSupported,
    pause,
    resume,
    setVoice,
    setRate,
    setPitch,
    voices,
    selectedVoice,
  };
}