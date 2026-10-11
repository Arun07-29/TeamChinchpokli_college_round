import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useVoiceCommands } from '../hooks/useVoiceCommands';
import type { VoiceCommandResult } from '../hooks/useVoiceCommands';
import { GeminiPlanner } from '../services/aiPlanner';
import { validateActionPlan } from '../services/actionValidator';
import { ActionExecutor } from '../services/actionExecutor';
import importedBotAvatar from '../assets/bot-avatar.png';

const botAvatar = (typeof chrome !== 'undefined' && chrome.runtime?.getURL)
  ? chrome.runtime.getURL('bot-avatar.png')
  : importedBotAvatar;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system_event';
  content: string;
}

interface ChatInterfaceProps {
  isActive: boolean;
  geminiApiKey: string;
  activeTabId: number | null;
  autoListen?: boolean;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ isActive, geminiApiKey, activeTabId, autoListen }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [language, setLanguage] = useState<'en-US' | 'hi-IN'>('en-US');

  const [isProcessing, setIsProcessing] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Stable ref so the speech recognition engine never re-mounts due to callback changes
  const handleVoiceRef = useRef<(result: VoiceCommandResult) => void>(() => {});
  handleVoiceRef.current = (result: VoiceCommandResult) => {
    appendMessage('user', result.rawTranscript);
    handlePlan(result.rawTranscript);
  };

  const stableHandleVoice = useCallback((result: VoiceCommandResult) => {
    handleVoiceRef.current(result);
  }, []); // empty deps = never recreated

  const {
    voiceState,
    errorMessage,
    startListening,
    stopListening
  } = useVoiceCommands(stableHandleVoice, language);

  useEffect(() => {
    if (autoListen) {
      startListening();
    } else {
      stopListening();
    }
  }, [autoListen, startListening, stopListening]);

  const appendMessage = (role: 'user' | 'assistant' | 'system_event', content: string) => {
    setMessages(prev => [...prev, { id: Date.now().toString() + Math.random(), role, content }]);
    
    // Voice feedback for assistant messages
    if (role === 'assistant' && 'speechSynthesis' in window) {
      // Cancel any ongoing speech so it doesn't queue up
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content);
      utterance.lang = language;

      // Select matching voice for Hindi or English
      if (language === 'hi-IN') {
        const voices = window.speechSynthesis.getVoices();
        const hiVoice = voices.find(v => v.lang.startsWith('hi') || v.name.toLowerCase().includes('hindi'));
        if (hiVoice) {
          utterance.voice = hiVoice;
        }
      }

      window.speechSynthesis.speak(utterance);
    }
  };

  const handlePlan = async (text: string) => {
    setIsProcessing(true);
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      let plan;
      if (geminiApiKey) {
        const planner = new GeminiPlanner(geminiApiKey);
        appendMessage('system_event', language === 'hi-IN' ? 'AI योजना बना रहा है...' : 'Planning with AI...');
        plan = await planner.generatePlan(text, messages, language);
      } else {
        appendMessage('assistant', 'No Gemini API Key provided. Please add VITE_GEMINI_API_KEY to your .env.local file and restart the build.');
        setIsProcessing(false);
        abortControllerRef.current = null;
        return;
      }
      
      if (signal.aborted) throw new Error('Cancelled');

      const validation = validateActionPlan(plan);
      if (!validation.valid || !validation.plan) {
        appendMessage('assistant', `I could not understand that. ${validation.error || 'Invalid action plan.'}`);
        return;
      }

      // If Gemini returned a pure conversational reply, show it and stop
      const firstAction = validation.plan[0] as any;
      if (
        validation.plan.length === 1 &&
        (firstAction.type === 'REPLY' || firstAction.type === 'ASK_CLARIFICATION') &&
        typeof firstAction.message === 'string'
      ) {
        appendMessage('assistant', firstAction.message);
        return;
      }

      const executor = new ActionExecutor(activeTabId);
      const result = await executor.executePlan(validation.plan, (status) => {
        appendMessage('system_event', status);
      }, signal);

      if (result.success) {
        appendMessage('assistant', 'Done! Anything else?');
      } else {
        appendMessage('assistant', result.message || 'Something went wrong. Please try again.');
      }
    } catch (err: any) {
      if (err.message === 'Cancelled') {
        appendMessage('system_event', 'Execution cancelled.');
      } else {
        console.error('AI Planner Error:', err);
        const errStr = String(err?.message || '');
        const msg =
          errStr.includes('API_KEY') || errStr.includes('403')
            ? 'API key issue. Please check your VITE_GEMINI_API_KEY in .env.local and rebuild.'
            : errStr.toLowerCase().includes('quota') || errStr.includes('daily quota')
            ? 'Daily AI quota reached for all models. Please wait until tomorrow or add billing at https://ai.dev'
            : errStr.includes('404') || errStr.toLowerCase().includes('not found')
            ? 'AI model unavailable — trying next model failed. Please check aiPlanner.ts.'
            : errStr.includes('429')
            ? 'Rate limit reached. Please wait a moment and try again.'
            : 'Sorry, something went wrong. Please try again.';
        appendMessage('assistant', msg);
      }
    } finally {
      setIsProcessing(false);
      abortControllerRef.current = null;
    }
  };





  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  // Only scroll to bottom when there are actual messages (prevent panel from scrolling on open)
  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [messages]);

  return (
    <div className="section" style={{ display: 'flex', flexDirection: 'column', height: '410px', padding: '12px' }}>
      {/* Header with Bot Avatar & Language Switcher */}
      <div 
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          marginBottom: '10px',
          paddingBottom: '8px',
          borderBottom: '1px solid #f0f0f0'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '9px' }}>
          {/* Bot Avatar Icon */}
          <div 
            className={voiceState === 'LISTENING' ? 'bot-avatar-listening' : ''}
            style={{
              position: 'relative',
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              overflow: 'hidden',
              border: '1.5px solid #f9c7d8',
              backgroundColor: '#fdebf3',
              boxShadow: '0 2px 6px rgba(244, 114, 182, 0.25)',
              flexShrink: 0
            }}
          >
            <img
              src={botAvatar}
              alt="Bot Avatar"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block'
              }}
            />
            {/* Live Status indicator dot */}
            <span
              style={{
                position: 'absolute',
                bottom: '1.5px',
                right: '1.5px',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: voiceState === 'LISTENING' ? '#22c55e' : isProcessing ? '#f59e0b' : isActive ? '#3b82f6' : '#94a3b8',
                border: '1.5px solid #fff',
                boxShadow: voiceState === 'LISTENING' ? '0 0 4px #22c55e' : 'none'
              }}
            />
          </div>

          <div>
            <h2 className="section-title" style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#1f2937' }}>
              Conversational Assistant
            </h2>
            <div style={{ fontSize: '11px', color: '#6b7280', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '1px' }}>
              <span>IntentLock Bot</span>
              <span>•</span>
              <span style={{ 
                color: voiceState === 'LISTENING' ? '#16a34a' : isProcessing ? '#d97706' : '#6b7280',
                fontWeight: voiceState === 'LISTENING' ? 600 : 500
              }}>
                {voiceState === 'LISTENING' ? 'Listening...' : isProcessing ? 'Thinking...' : 'Ready'}
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '3px', backgroundColor: '#e9ecef', padding: '2px', borderRadius: '6px' }}>
          <button
            type="button"
            onClick={() => setLanguage('en-US')}
            style={{
              padding: '3px 8px',
              fontSize: '11px',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: language === 'en-US' ? '#007bff' : 'transparent',
              color: language === 'en-US' ? '#fff' : '#495057',
              cursor: 'pointer',
              fontWeight: language === 'en-US' ? 'bold' : 'normal',
              transition: 'all 0.15s ease'
            }}
          >
            🇬🇧 EN
          </button>
          <button
            type="button"
            onClick={() => setLanguage('hi-IN')}
            style={{
              padding: '3px 8px',
              fontSize: '11px',
              borderRadius: '4px',
              border: 'none',
              backgroundColor: language === 'hi-IN' ? '#007bff' : 'transparent',
              color: language === 'hi-IN' ? '#fff' : '#495057',
              cursor: 'pointer',
              fontWeight: language === 'hi-IN' ? 'bold' : 'normal',
              transition: 'all 0.15s ease'
            }}
          >
            🇮🇳 हिन्दी
          </button>
        </div>
      </div>
      
      {/* Message List */}
      <div 
        style={{ 
          flex: 1, 
          overflowY: 'auto', 
          backgroundColor: '#f8f9fa', 
          border: '1px solid #dee2e6',
          borderRadius: '8px',
          padding: '10px',
          marginBottom: '10px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}
      >
        {messages.length === 0 ? (
          <div style={{ 
            margin: 'auto', 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center',
            textAlign: 'center',
            padding: '10px'
          }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '16px',
              overflow: 'hidden',
              border: '2px solid #f9c7d8',
              backgroundColor: '#fdebf3',
              boxShadow: '0 4px 12px rgba(244, 114, 182, 0.35)',
              marginBottom: '10px'
            }}>
              <img
                src={botAvatar}
                alt="IntentLock Bot"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>
            <div style={{ fontWeight: 600, fontSize: '13px', color: '#1f2937', marginBottom: '3px' }}>
              {language === 'hi-IN' ? 'नमस्ते! मैं आपका IntentLock सहायक हूँ' : "Hi! I'm your IntentLock Bot"}
            </div>
            <div style={{ fontSize: '11px', color: '#6b7280', maxWidth: '240px', lineHeight: '1.4', marginBottom: '8px' }}>
              {language === 'hi-IN' 
                ? 'बोलें "नीचे स्क्रॉल करो", "नया टैब खोलो" या कुछ भी पूछें।'
                : 'Say "scroll down", "open new tab", "click link", or ask any question.'}
            </div>
            <span style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: '5px', 
              fontSize: '11px', 
              color: '#4b5563', 
              backgroundColor: '#ffffff', 
              padding: '3px 8px', 
              borderRadius: '12px',
              border: '1px solid #e5e7eb'
            }}>
              <span style={{ 
                width: '6px', 
                height: '6px', 
                borderRadius: '50%', 
                backgroundColor: isActive ? '#22c55e' : '#f59e0b' 
              }} />
              {isActive ? (voiceState === 'LISTENING' ? 'Listening now...' : 'Tap speak button below') : 'Start session first'}
            </span>
          </div>
        ) : (
          messages.map(msg => {
            if (msg.role === 'assistant') {
              return (
                <div 
                  key={msg.id} 
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px',
                    alignSelf: 'flex-start',
                    maxWidth: '90%'
                  }}
                >
                  <div style={{
                    width: '26px',
                    height: '26px',
                    borderRadius: '7px',
                    overflow: 'hidden',
                    border: '1px solid #f9c7d8',
                    backgroundColor: '#fdebf3',
                    flexShrink: 0,
                    marginTop: '2px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.06)'
                  }}>
                    <img 
                      src={botAvatar} 
                      alt="Bot" 
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                    />
                  </div>
                  <div style={{
                    backgroundColor: '#ffffff',
                    color: '#212529',
                    border: '1px solid #dee2e6',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    wordWrap: 'break-word',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.03)'
                  }}>
                    {msg.content}
                  </div>
                </div>
              );
            }
            if (msg.role === 'user') {
              return (
                <div 
                  key={msg.id} 
                  style={{
                    alignSelf: 'flex-end',
                    backgroundColor: '#007bff',
                    color: '#fff',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    maxWidth: '85%',
                    wordWrap: 'break-word'
                  }}
                >
                  {msg.content}
                </div>
              );
            }
            return (
              <div 
                key={msg.id} 
                style={{
                  alignSelf: 'center',
                  backgroundColor: '#e9ecef',
                  color: '#6c757d',
                  padding: '4px 10px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  fontStyle: 'italic',
                  maxWidth: '90%',
                  textAlign: 'center'
                }}
              >
                {msg.content}
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Status Bar with Cancel */}
      <div style={{ fontSize: '11px', color: '#6c757d', marginBottom: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {voiceState === 'LISTENING' ? '🎤 Listening...' : 
           voiceState === 'PROCESSING' ? '⚙️ Processing...' : 
           voiceState === 'ERROR' ? `❌ ${errorMessage}` : 
           language === 'hi-IN' ? 'आवाज़ सहायक तैयार (हिन्दी)' : 'Voice assistant ready'}
        </span>
        {isProcessing && (
          <button
            type="button"
            onClick={handleCancel}
            className="danger"
            style={{ padding: '2px 8px', fontSize: '11px', borderRadius: '4px' }}
          >
            Cancel
          </button>
        )}
      </div>

      {/* Primary Voice Action Button */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          type="button"
          onClick={voiceState === 'LISTENING' ? stopListening : startListening}
          disabled={!isActive || voiceState === 'UNSUPPORTED' || isProcessing}
          style={{
            flex: 1,
            backgroundColor: voiceState === 'LISTENING' ? '#dc3545' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            padding: '11px',
            fontSize: '13px',
            fontWeight: 'bold',
            cursor: (!isActive || voiceState === 'UNSUPPORTED' || isProcessing) ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            transition: 'all 0.2s ease'
          }}
        >
          {voiceState === 'LISTENING' ? '⏹ Stop Listening' : '🎤 Tap to Speak Command'}
        </button>
      </div>
    </div>
  );
};
