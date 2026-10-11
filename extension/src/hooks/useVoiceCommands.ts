import { useState, useEffect, useRef, useCallback } from 'react';


export type VoiceState = 'UNSUPPORTED' | 'IDLE' | 'LISTENING' | 'PROCESSING' | 'ERROR';

export interface VoiceCommandResult {
  command: string;
  arg?: string;
  rawTranscript: string;
}

// Fallback for TypeScript
const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export function useVoiceCommands(
  onCommand: (result: VoiceCommandResult) => void,
  language: string = 'en-US'
) {
  const [voiceState, setVoiceState] = useState<VoiceState>(SpeechRecognition ? 'IDLE' : 'UNSUPPORTED');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  
  const recognitionRef = useRef<any>(null);
  const shouldListenRef = useRef<boolean>(false);

  useEffect(() => {
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();
    recognition.continuous = true; // Support continuous listening
    recognition.interimResults = false;
    recognition.lang = language;

    recognition.onstart = () => {
      setVoiceState('LISTENING');
      setErrorMessage(null);
    };

    recognition.onresult = async (event: any) => {
      setVoiceState('PROCESSING');
      
      const lastResultIndex = event.results.length - 1;
      const rawTranscript = event.results[lastResultIndex][0].transcript.trim();
      
      if (rawTranscript) {
        onCommand({ command: 'VOICE_INPUT', rawTranscript });
      }

      // Return to LISTENING if we still want to be listening, otherwise IDLE.
      setVoiceState(shouldListenRef.current ? 'LISTENING' : 'IDLE');
    };

    recognition.onerror = (event: any) => {
      if (event.error === 'not-allowed') {
        shouldListenRef.current = false;
        setErrorMessage('Microphone access denied. Grant permission and try again.');
        setVoiceState('ERROR');
        return;
      }
      
      // For network or no-speech errors, we log them but don't stop the continuous loop
      if (event.error === 'no-speech' || event.error === 'network') {
        // We just let onend restart it naturally
        return;
      }
      
      if (!shouldListenRef.current) {
        setErrorMessage('Voice recognition error: ' + event.error);
        setVoiceState('ERROR');
      }
    };

    recognition.onend = () => {
      // Chrome stops recognition automatically after silence or some errors.
      // If we still want to listen, restart it!
      if (shouldListenRef.current) {
        setTimeout(() => {
          if (shouldListenRef.current) {
            try {
              recognition.start();
            } catch (e) {
              // Ignore restart collision errors
            }
          }
        }, 100);
      } else {
        setVoiceState(prev => prev === 'ERROR' ? 'ERROR' : 'IDLE');
      }
    };

    recognitionRef.current = recognition;

    return () => {
      shouldListenRef.current = false;
      recognition.abort();
    };
  }, [onCommand, language]);

  const startListening = useCallback(() => {
    if (recognitionRef.current && voiceState !== 'LISTENING') {
      shouldListenRef.current = true;
      try {
        recognitionRef.current.start();
      } catch (e) {
        // Already started
      }
    }
  }, [voiceState]);

  const stopListening = useCallback(() => {
    shouldListenRef.current = false;
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setVoiceState('IDLE');
  }, []);

  return {
    voiceState,
    errorMessage,
    startListening,
    stopListening
  };
}
