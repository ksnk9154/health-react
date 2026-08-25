import { useState, useEffect, useRef, useCallback } from 'react';
import GlassCard from '../components/GlassCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import {
  Bot,
  Send,
  RefreshCw,
  Activity,
  Lightbulb,
  AlertCircle,
  CheckCircle,
  XCircle,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { llmService } from '../services/api';
import VoiceButton from '../../features/voice/components/VoiceButton';
import AutoSpeakToggle from '../../features/voice/components/AutoSpeakToggle';
import useSpeechSynthesis from '../../features/voice/hooks/useSpeechSynthesis';
import { useLanguage } from '../i18n/LanguageContext';
import MarkdownContent from '../components/MarkdownContent';
import HealthOverview from '../components/HealthOverview';
import HealthHistory from '../components/HealthHistory';
import { healthOverviewService } from '../services/api';
import { useNavigate } from 'react-router';

const LLMAssistantPage = () => {
  const { t, language } = useLanguage();
  const navigate = useNavigate();
  // Health status
  const [healthStatus, setHealthStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);

  // Chat
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Voice (STT) feedback
  const [voiceInterim, setVoiceInterim] = useState('');
  const [voiceError, setVoiceError] = useState('');

  // Analyze
  const [analyzeResult, setAnalyzeResult] = useState('');
  const [analyzeLoading, setAnalyzeLoading] = useState(false);

  // Suggestions
  const [suggestionsResult, setSuggestionsResult] = useState('');
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  // Disclaimer
  const [disclaimer, setDisclaimer] = useState('');

  // Voice — auto-speak state (persisted in localStorage)
  const [autoSpeakEnabled, setAutoSpeakEnabled] = useState(() => {
    return localStorage.getItem('autoSpeak') === 'true';
  });

  const { speak, cancel: cancelSpeech, isSpeaking } = useSpeechSynthesis({
    rate: 1.0,
    pitch: 1.0,
  });

  const handleAutoSpeakToggle = useCallback((enabled) => {
    setAutoSpeakEnabled(enabled);
    localStorage.setItem('autoSpeak', enabled ? 'true' : 'false');
  }, []);

  // Voice transcript handler — fills input and auto-sends
  const handleVoiceTranscript = useCallback((transcript) => {
    if (!transcript.trim()) return;
    setVoiceInterim('');
    setVoiceError('');
    setChatInput(transcript);
    // Auto-send after a brief delay so user sees the text
    setTimeout(() => {
      if (transcript.trim()) {
        // We need to trigger send with the transcript directly
        // since setChatInput is async
        setChatInput('');
        const userMessage = { role: 'user', content: transcript.trim() };
        setMessages((prev) => [...prev, userMessage]);
        setChatLoading(true);
        llmService.chat(transcript.trim(), messages, language)
          .then((response) => {
            const assistantMessage = { role: 'assistant', content: response.reply };
            setMessages((prev) => [...prev, assistantMessage]);
            if (response.disclaimer) {
              setDisclaimer(response.disclaimer);
            }
            if (autoSpeakEnabled && response.reply) {
              speak(response.reply);
            }
          })
          .catch((error) => {
            const errorMsg = error.response?.data?.detail || t('llm.errorSend');
            toast.error(errorMsg);
          })
          .finally(() => {
            setChatLoading(false);
          });
      }
    }, 300);
  }, [messages, autoSpeakEnabled, speak, t, language]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load health status on mount
  const loadHealthStatus = async () => {
    setHealthLoading(true);
    try {
      const result = await llmService.checkHealth();
      setHealthStatus(result);
    } catch (error) {
      const errorMsg =
        error.response?.data?.detail || t('llm.errorHealth');
      toast.error(errorMsg);
      setHealthStatus({ status: 'error', detail: errorMsg });
    } finally {
      setHealthLoading(false);
    }
  };

  useEffect(() => {
    loadHealthStatus();
    healthOverviewService.get().then(setOverview).catch(() => setOverview(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Chat handlers
  const handleSendMessage = async () => {
    if (!chatInput.trim() || chatLoading) return;

    const message = chatInput.trim();
    setChatInput('');

    // Cancel any ongoing speech when user sends a new message
    if (isSpeaking) {
      cancelSpeech();
    }

    // Add user message to UI
    const userMessage = { role: 'user', content: message };
    setMessages((prev) => [...prev, userMessage]);

    setChatLoading(true);
    try {
      // Pass current messages as history (backend appends current message)
      const response = await llmService.chat(message, messages, language);
      const assistantMessage = { role: 'assistant', content: response.reply };
      setMessages((prev) => [...prev, assistantMessage]);
      if (response.disclaimer) {
        setDisclaimer(response.disclaimer);
      }
      // Auto-speak the response if enabled
      if (autoSpeakEnabled && response.reply) {
        speak(response.reply);
      }
    } catch (error) {
      const errorMsg =
        error.response?.data?.detail || t('llm.errorSend');
      toast.error(errorMsg);
    } finally {
      setChatLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const useSuggestedQuestion = (question) => {
    setChatInput(question);
  };

  // Analyze handler
  const handleAnalyze = async () => {
    setAnalyzeLoading(true);
    setAnalyzeResult('');
    try {
      const response = await llmService.analyze(10, language);
      setAnalyzeResult(response.analysis);
      if (response.disclaimer) {
        setDisclaimer(response.disclaimer);
      }
    } catch (error) {
      const errorMsg =
        error.response?.data?.detail || t('llm.errorAnalyze');
      toast.error(errorMsg);
    } finally {
      setAnalyzeLoading(false);
    }
  };

  // Suggestions handler
  const handleSuggestions = async () => {
    setSuggestionsLoading(true);
    setSuggestionsResult('');
    try {
      const response = await llmService.suggestions(10, language);
      setSuggestionsResult(response.suggestions);
      if (response.disclaimer) {
        setDisclaimer(response.disclaimer);
      }
    } catch (error) {
      const errorMsg =
        error.response?.data?.detail || t('llm.errorSuggestions');
      toast.error(errorMsg);
    } finally {
      setSuggestionsLoading(false);
    }
  };

  // Health status display helpers
  // NOTE: the backend returns status "healthy" (llm_service.LLMService.check_health),
  // so we treat both "ok" and "healthy" as healthy.
  const isHealthy = (s) =>
    (s?.status === 'ok' || s?.status === 'healthy') && s?.model_available;

  const getHealthStatusIcon = () => {
    if (healthLoading)
      return <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />;
    if (!healthStatus)
      return <AlertCircle className="w-5 h-5 text-gray-400" />;
    if (isHealthy(healthStatus))
      return <CheckCircle className="w-5 h-5 text-green-500" />;
    if (healthStatus.status === 'model_not_found')
      return <XCircle className="w-5 h-5 text-yellow-500" />;
    return <XCircle className="w-5 h-5 text-red-500" />;
  };

  const getHealthStatusText = () => {
    if (healthLoading) return t('llm.checking');
    if (!healthStatus) return t('llm.notChecked');
    if (isHealthy(healthStatus))
      return t('llm.running', { model: healthStatus.model });
    if (healthStatus.status === 'model_not_found')
      return t('llm.modelNotFound', { model: healthStatus.model });
    return healthStatus.detail || t('llm.unavailable');
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <HealthOverview data={overview} loading={!overview} onRefresh={() => healthOverviewService.get().then(setOverview)} />
      <HealthHistory />
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          {t('llm.title')}
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          {t('llm.subtitle')}
        </p>
      </div>

      {/* Health Status */}
      <GlassCard className="p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getHealthStatusIcon()}
            <div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                {t('llm.healthStatus')}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {getHealthStatusText()}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={loadHealthStatus}
            disabled={healthLoading}
            className="backdrop-blur-sm bg-white/50 dark:bg-gray-800/50"
          >
            <RefreshCw
              className={`w-4 h-4 ${healthLoading ? 'animate-spin' : ''}`}
            />
          </Button>
        </div>
      </GlassCard>

      {/* Main Content */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Chat Section */}
        <div className="lg:col-span-3">
          <GlassCard className="p-6 flex flex-col h-[500px]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                {t('llm.chatTitle')}
              </h3>
              <AutoSpeakToggle
                enabled={autoSpeakEnabled}
                onToggle={handleAutoSpeakToggle}
                isSpeaking={isSpeaking}
                onStop={cancelSpeech}
              />
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto space-y-4 mb-4">
              {messages.length === 0 ? (
                <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center py-8 text-center text-slate-500 dark:text-slate-400">
                  <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400"><Bot className="size-7" /></div>
                  <p className="text-base font-semibold text-slate-900 dark:text-white">Ask your AI Health Assistant</p>
                  <p className="mt-2 text-sm leading-6">Get insights about your health records, documents, wellness, and general health questions.</p>
                  <div className="mt-5 flex flex-wrap justify-center gap-2">
                    {['What trends do you see in my weight?', 'Explain my latest health report', 'What should I track regularly?'].map((question) => (
                      <button key={question} type="button" onClick={() => useSuggestedQuestion(question)} className="rounded-full border border-blue-100 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-blue-300 dark:hover:bg-slate-700">
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`p-3 rounded-lg ${
                      msg.role === 'user'
                        ? 'bg-blue-50 dark:bg-blue-900/20 ml-auto max-w-[80%]'
                        : 'bg-gray-50 dark:bg-gray-800/50 mr-auto max-w-[80%]'
                    }`}
                  >
                    <p className="text-sm text-gray-900 dark:text-white whitespace-pre-wrap">
                      {msg.content}
                    </p>
                    {msg.role === 'assistant' && msg.content ? (
                      <button
                        type="button"
                        onClick={() => (isSpeaking ? cancelSpeech() : speak(msg.content))}
                        className="mt-2 inline-flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
                        aria-label={isSpeaking ? t('llm.stop') : t('llm.speak')}
                        title={isSpeaking ? t('llm.stop') : t('llm.speak')}
                      >
                        {isSpeaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
                        <span>{isSpeaking ? t('llm.stop') : t('llm.speak')}</span>
                      </button>
                    ) : null}
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="flex gap-2">
              <Input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('llm.inputPlaceholder')}
                disabled={chatLoading}
                className="backdrop-blur-sm bg-white/50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700"
              />
              <VoiceButton
                onTranscript={handleVoiceTranscript}
                onInterim={setVoiceInterim}
                onError={(msg) => setVoiceError(msg)}
                disabled={chatLoading}
                size="md"
              />
              <Button
                onClick={handleSendMessage}
                disabled={!chatInput.trim() || chatLoading}
                className="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white"
              >
                {chatLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </Button>
            </div>
            {voiceInterim ? (
              <div className="mt-2 text-xs text-blue-500 dark:text-blue-400">
                🎤 {voiceInterim}
              </div>
            ) : null}
            {voiceError ? (
              <div className="mt-2 text-xs text-red-500 dark:text-red-400">
                Mic error: {voiceError}
              </div>
            ) : null}
          </GlassCard>
        </div>

        {/* Analyze & Suggestions */}
        <div className="space-y-6 lg:col-span-2">
          {/* Analyze */}
          <GlassCard className="p-6">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-500" />
              {t('llm.healthAnalysis')}
            </h3>
            <Button
              onClick={handleAnalyze}
              disabled={analyzeLoading}
              className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white mb-4"
            >
              {analyzeLoading ? (
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  {t('llm.analyzing')}
                </div>
              ) : (
                t('llm.analyze')
              )}
            </Button>
            {analyzeResult ? (
              analyzeResult.toLowerCase().includes('no health records available') ? (
                <div className="rounded-xl border border-blue-100 bg-white p-6 text-center shadow-sm dark:border-slate-700 dark:bg-slate-900">
                  <div className="mx-auto mb-3 flex size-11 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400"><Bot className="size-5" /></div>
                  <p className="font-semibold text-slate-900 dark:text-white">No health records available</p>
                  <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-600 dark:text-slate-300">We don't have enough health-record data to generate a personalized analysis yet. Add a health record to get personalized insights.</p>
                  <Button onClick={() => navigate('/records')} className="mt-5 bg-gradient-to-r from-blue-500 to-indigo-600 text-white">Add Health Record</Button>
                </div>
              ) : (
              <div className="rounded-xl border border-blue-100 bg-white p-5 text-sm text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
                  <Bot className="size-4" /> AI-generated analysis
                </div>
                <div className="max-h-96 overflow-y-auto pr-2 leading-7 [scrollbar-color:theme(colors.slate.300)_transparent] dark:[scrollbar-color:theme(colors.slate.600)_transparent]">
                  <MarkdownContent content={analyzeResult} />
                </div>
                <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">Generated just now</p>
              </div>
              )
            ) : (
              <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
                {t('llm.analyzeHint')}
              </div>
            )}
          </GlassCard>

          {/* Suggestions */}
          <GlassCard className="p-6">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-yellow-500" />
              {t('llm.wellnessSuggestions')}
            </h3>
            <Button
              onClick={handleSuggestions}
              disabled={suggestionsLoading}
              className="w-full bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-600 hover:to-orange-600 text-white mb-4"
            >
              {suggestionsLoading ? (
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  {t('llm.generating')}
                </div>
              ) : (
                t('llm.getSuggestions')
              )}
            </Button>
            {suggestionsResult ? (
              <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 max-h-60 overflow-y-auto">
                {suggestionsResult}
              </div>
            ) : (
              <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
                {t('llm.suggestionsHint')}
              </div>
            )}
          </GlassCard>
        </div>
      </div>

      {/* Medical Disclaimer */}
      {disclaimer ? (
        <GlassCard className="p-4 bg-yellow-50/50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-yellow-800 dark:text-yellow-300 whitespace-pre-wrap">
              {disclaimer}
            </p>
          </div>
        </GlassCard>
      ) : null}
    </div>
  );
};

export default LLMAssistantPage;
