import { GoogleGenerativeAI } from '@google/generative-ai';
import type { ActionPlan } from '../shared/types';
import type { ChatMessage } from '../components/ChatInterface';

const SYSTEM_INSTRUCTION = `You are an AI browser assistant built into a Chrome extension called IntentLock. The user gives voice commands to control their browser.

YOUR ONLY OUTPUT must be a raw JSON array — no markdown, no backticks, no explanation, no preamble.

Available actions (use these for ALL browser control requests):
- { "type": "NAVIGATE", "url": "https://..." }  — navigate the current tab to a URL
- { "type": "SEARCH", "query": "..." }  — search Google in current tab
- { "type": "SCROLL", "direction": "up" | "down" | "top" | "bottom" }
- { "type": "HISTORY", "direction": "back" | "forward" }
- { "type": "IDENTIFY_ELEMENTS" }  — show numbered labels on clickable elements
- { "type": "FOCUS_FIELD", "nameOrId": "..." }  — focus an input field
- { "type": "INSERT_TEXT", "text": "..." }  — type into the focused field
- { "type": "CLICK_ELEMENT", "nameOrId": "..." }  — click a button or link by name
- { "type": "CLOSE_TAB" }  — close the current tab
- { "type": "NEW_TAB" }  — open a blank new tab
- { "type": "NEXT_TAB" }  — switch to the next tab
- { "type": "PREV_TAB" }  — switch to the previous tab
- { "type": "REPLY", "message": "..." }  — ONLY use this for pure questions, greetings, or when no browser action applies

STRICT RULES:
1. When user says "go to X and search Y" or "search Y on X" (e.g., YouTube, Google, GitHub, Reddit):
   - YouTube: NAVIGATE to "https://www.youtube.com/results?search_query=Y"
   - Google: SEARCH with query "Y"
   - GitHub: NAVIGATE to "https://github.com/search?q=Y"
2. When user says "go to X", "open X", "navigate to X" → always use NAVIGATE with that website's URL.
3. When user says "search for X" without a site → always use SEARCH.
4. When user says "scroll up/down" → always use SCROLL.
5. When user says "go back/forward" → always use HISTORY.
6. Do NOT use REPLY when a browser action applies — just do the action. Ignore wake words like "jarvis", "hey jarvis", "alright jarvis".
7. Keep plans to 1–2 steps maximum.
8. Common site mappings: youtube → https://www.youtube.com, github → https://github.com, google → https://www.google.com, reddit → https://www.reddit.com, twitter → https://www.twitter.com

EXAMPLES (ALWAYS follow this exact format):
- "alright jarvis go to youtube and search jailer 2" → [{"type":"NAVIGATE","url":"https://www.youtube.com/results?search_query=jailer+2"}]
- "go to youtube" → [{"type":"NAVIGATE","url":"https://www.youtube.com"}]
- "search cats" → [{"type":"SEARCH","query":"cats"}]
- "scroll down" → [{"type":"SCROLL","direction":"down"}]
- "go back" → [{"type":"HISTORY","direction":"back"}]
- "open new tab" → [{"type":"NEW_TAB"}]
- "close tab" → [{"type":"CLOSE_TAB"}]
- "what is AI?" → [{"type":"REPLY","message":"AI is artificial intelligence — software that performs tasks that normally require human intelligence."}]
- "hello" → [{"type":"REPLY","message":"Hi! Say a command like 'go to YouTube' or 'scroll down' to get started."}]`;

/**
 * Models tried in order. If one returns 429 (quota exhausted) or 404 (unavailable),
 * the next one in the list is tried automatically.
 * Verified working as of 2026-10-11 with this API key.
 */
const MODEL_FALLBACK_CHAIN = [
  'gemini-3.7-flash',   // primary — confirmed working
  'gemini-3.6-flash',   // fallback 1
  'gemini-3.5-flash',   // fallback 2
  'gemini-flash-latest', // alias — redirects to latest available flash
  'gemini-3.1-flash-lite',
  'gemini-3.1-flash-lite-preview',
];

/**
 * Fast deterministic intent matcher for browser commands.
 * Supports both English and Hindi voice commands.
 * Runs locally in 0ms with 100% reliability, zero quota usage, and no network dependencies.
 */
export function matchFastIntent(prompt: string, _language: string = 'en-US'): ActionPlan | null {
  let p = prompt.trim();
  // Strip wake words and conversational filler (English & Hindi)
  p = p.replace(/^(?:alright|hey|ok|okay|arrey|bhai|sun)?\s*(?:jarvis|intentlock|assistant|computer)?\s*,?\s*/i, '');
  p = p.replace(/^(?:can\s+you|could\s+you|please|would\s+you|kripya|zara)\s+/i, '');
  p = p.trim();
  const lower = p.toLowerCase();

  // ── 1. Tab Management (English & Hindi) ──────────────────────────────────
  if (/^(?:open\s+)?new\s+tab/i.test(lower) || /^naya\s+tab(?:\s+kholo)?/i.test(lower) || /नया\s+टैब/i.test(p)) {
    return [{ type: 'NEW_TAB' }];
  }
  if (/^close\s+(?:this\s+)?tab/i.test(lower) || /^tab\s+band\s+karo/i.test(lower) || /टैब\s+बंद\s+करो/i.test(p)) {
    return [{ type: 'CLOSE_TAB' }];
  }
  if (/^next\s+tab/i.test(lower) || /^agla\s+tab/i.test(lower) || /अगला\s+टैब/i.test(p)) {
    return [{ type: 'NEXT_TAB' }];
  }
  if (/^(?:previous|prev)\s+tab/i.test(lower) || /^pichhla\s+tab/i.test(lower) || /पिछला\s+टैब/i.test(p)) {
    return [{ type: 'PREV_TAB' }];
  }

  // ── 2. History Navigation (English & Hindi) ──────────────────────────────
  if (/^(?:go\s+)?back/i.test(lower) || /^(?:piche|peeche|wapas)\s+jao/i.test(lower) || /पीछे\s+जाओ|वापस\s+जाओ/i.test(p)) {
    return [{ type: 'HISTORY', direction: 'back' }];
  }
  if (/^(?:go\s+)?forward/i.test(lower) || /^aage\s+jao/i.test(lower) || /आगे\s+जाओ/i.test(p)) {
    return [{ type: 'HISTORY', direction: 'forward' }];
  }

  // ── 3. Scrolling (English & Hindi) ───────────────────────────────────────
  if (/^scroll\s+down/i.test(lower) || /^(?:niche|neeche)\s+(?:scroll|jao|scroll\s+karo)/i.test(lower) || /नीचे\s+(?:स्क्रॉल|जाओ)/i.test(p)) {
    return [{ type: 'SCROLL', direction: 'down' }];
  }
  if (/^scroll\s+up/i.test(lower) || /^(?:upar)\s+(?:scroll|jao|scroll\s+karo)/i.test(lower) || /ऊपर\s+(?:स्क्रॉल|जाओ)/i.test(p)) {
    return [{ type: 'SCROLL', direction: 'up' }];
  }
  if (/^(?:scroll\s+to\s+)?top/i.test(lower) || /^(?:sabse\s+)?upar\s+jao/i.test(lower) || /सबसे\s+ऊपर/i.test(p)) {
    return [{ type: 'SCROLL', direction: 'top' }];
  }
  if (/^(?:scroll\s+to\s+)?bottom/i.test(lower) || /^(?:sabse\s+)?(?:niche|neeche)\s+jao/i.test(lower) || /सबसे\s+नीचे/i.test(p)) {
    return [{ type: 'SCROLL', direction: 'bottom' }];
  }

  // ── 4. Element targeting (English & Hindi) ───────────────────────────────
  if (/^(?:identify|highlight|target|show)\s+elements/i.test(lower) || /elements\s+(?:dikhao|identify\s+karo)/i.test(lower) || /एलिमेंट्स\s+दिखाओ/i.test(p)) {
    return [{ type: 'IDENTIFY_ELEMENTS' }];
  }

  // ── 5. YouTube Search (English & Hindi) ──────────────────────────────────
  let m = lower.match(/^(?:go\s+to|open)\s+youtube\s+(?:and\s+)?search\s+(?:for\s+)?(.+)$/i) ||
          lower.match(/^search\s+(?:for\s+)?(.+?)\s+on\s+youtube$/i) ||
          lower.match(/^youtube\s+(?:par|me|mein)\s+(.+?)\s+(?:search\s+karo|dhundo)$/i) ||
          lower.match(/^(?:youtube\s+kholo\s+aur\s+)(.+?)\s+(?:search\s+karo|dhundo)$/i) ||
          p.match(/^(?:यूट्यूब|युट्यूब)\s+(?:पर|में)\s+(.+?)\s+(?:सर्च\s+करो|ढूंढो|सर्च)$/i);
  if (m && m[1]?.trim()) {
    return [{ type: 'NAVIGATE', url: `https://www.youtube.com/results?search_query=${encodeURIComponent(m[1].trim())}` }];
  }

  // ── 6. Navigation (English & Hindi) ──────────────────────────────────────
  m = lower.match(/^(?:go\s+to|open|navigate\s+to)\s+(.+)$/i) ||
      lower.match(/^(.+?)\s+(?:kholo|open\s+karo|par\s+jao)$/i) ||
      p.match(/^(.+?)\s+(?:खोलो|पर\s+जाओ)$/i);
  if (m && m[1]?.trim()) {
    let siteRaw = m[1].trim();
    // Normalize Hindi site names
    if (/^(?:यूट्यूब|युट्यूब)$/i.test(siteRaw)) siteRaw = 'youtube';
    if (/^(?:गूगल)$/i.test(siteRaw)) siteRaw = 'google';

    if (
      siteRaw.startsWith('http://') ||
      siteRaw.startsWith('https://') ||
      siteRaw.startsWith('chrome://') ||
      siteRaw.startsWith('about:') ||
      siteRaw.startsWith('file://')
    ) {
      return [{ type: 'NAVIGATE', url: siteRaw }];
    }
    const domainMap: Record<string, string> = {
      'youtube': 'https://www.youtube.com',
      'google': 'https://www.google.com',
      'github': 'https://github.com',
      'reddit': 'https://www.reddit.com',
      'twitter': 'https://x.com',
      'x': 'https://x.com',
      'facebook': 'https://www.facebook.com',
      'instagram': 'https://www.instagram.com',
      'netflix': 'https://www.netflix.com',
      'amazon': 'https://www.amazon.com',
      'chatgpt': 'https://chatgpt.com',
      'wikipedia': 'https://www.wikipedia.org',
      'extensions': 'chrome://extensions',
      'chrome extensions': 'chrome://extensions',
      'downloads': 'chrome://downloads',
      'history': 'chrome://history',
      'settings': 'chrome://settings',
      'bookmarks': 'chrome://bookmarks',
      'new tab': 'chrome://newtab',
    };
    if (domainMap[siteRaw]) {
      return [{ type: 'NAVIGATE', url: domainMap[siteRaw] }];
    }
    if (siteRaw.includes('.')) {
      return [{ type: 'NAVIGATE', url: `https://${siteRaw}` }];
    }
    return [{ type: 'SEARCH', query: siteRaw }];
  }

  // ── 7. Google Search & General Search (English & Hindi) ───────────────────
  m = lower.match(/^search\s+(?:for\s+)?(.+?)\s+on\s+google$/i) ||
      lower.match(/^google\s+(?:par|me|mein)\s+(.+?)\s+(?:search\s+karo|dhundo)$/i) ||
      lower.match(/^(.+?)\s+(?:search\s+karo|dhundo)$/i) ||
      lower.match(/^(?:search|google)\s+(?:for\s+)?(.+)$/i) ||
      p.match(/^(.+?)\s+(?:सर्च\s+करो|ढूंढो)$/i);
  if (m && m[1]?.trim()) {
    return [{ type: 'SEARCH', query: m[1].trim() }];
  }

  // ── 8. Simple Greetings (English & Hindi) ─────────────────────────────────
  if (/^(?:hello|hi|hey)$/i.test(lower)) {
    return [{ type: 'REPLY', message: "Hello! Say a command like 'go to YouTube and search jailer 2', 'scroll down', or ask me any question." }] as unknown as ActionPlan;
  }
  if (/^(?:namaste|namaskar|kaise ho|kya haal hai)$/i.test(lower) || /^(?:नमस्ते|नमस्कार|कैसे हो)$/i.test(p)) {
    return [{ type: 'REPLY', message: "नमस्ते! मैं आपका IntentLock AI सहायक हूँ। आप कह सकते हैं 'YouTube खोलो', 'नीचे स्क्रॉल करो' या कोई भी सवाल पूछ सकते हैं।" }] as unknown as ActionPlan;
  }

  return null;
}

export class GeminiPlanner {
  private genAI: GoogleGenerativeAI;

  constructor(apiKey: string) {
    // Strip any accidental surrounding quotes or spaces Vite may have left
    const cleanKey = apiKey.trim().replace(/^["']|["']$/g, '');
    this.genAI = new GoogleGenerativeAI(cleanKey);
  }

  async generatePlan(
    prompt: string, 
    context: ChatMessage[] = [],
    language: 'en-US' | 'hi-IN' = 'en-US'
  ): Promise<ActionPlan> {
    // Step 1: Check fast local intent matcher (0ms latency, zero quota, 100% reliability)
    const fastPlan = matchFastIntent(prompt, language);
    if (fastPlan) {
      return fastPlan;
    }

    // Step 2: Use Gemini LLM for conversational questions or complex queries
    const historyString = context
      .slice(-6)
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(msg => `[${msg.role.toUpperCase()}]: ${msg.content}`)
      .join('\n');

    const langInstruction = language === 'hi-IN'
      ? `\n[IMPORTANT: The user has selected Hindi. If replying conversationally with 'REPLY', write your response in natural Hindi (Devanagari script).]`
      : '';

    const fullPrompt = historyString
      ? `Recent context:\n${historyString}\n\nCurrent Request:\n[USER]: ${prompt}${langInstruction}\n\nGenerate JSON plan:`
      : `Current Request:\n[USER]: ${prompt}${langInstruction}\n\nGenerate JSON plan:`;

    let lastError: Error = new Error('No models available.');

    for (const modelName of MODEL_FALLBACK_CHAIN) {
      try {
        const model = this.genAI.getGenerativeModel({
          model: modelName,
          systemInstruction: SYSTEM_INSTRUCTION,
        });

        const result = await model.generateContent(fullPrompt);
        const responseText = result.response.text().trim();

        // Strip markdown fences if the model wrapped the JSON anyway
        let cleanText = responseText;
        if (cleanText.startsWith('```json')) cleanText = cleanText.substring(7);
        if (cleanText.startsWith('```'))     cleanText = cleanText.substring(3);
        if (cleanText.endsWith('```'))       cleanText = cleanText.substring(0, cleanText.length - 3);
        cleanText = cleanText.trim();

        try {
          const plan = JSON.parse(cleanText);
          return plan as ActionPlan;
        } catch {
          // If the model returned natural language instead of JSON, treat as conversational reply
          if (cleanText.length > 0) {
            return [{ type: 'REPLY', message: cleanText }] as unknown as ActionPlan;
          }
          throw new Error('AI returned an empty response.');
        }

      } catch (err: any) {
        const errMsg = String(err?.message || err);
        const isQuotaError = errMsg.includes('429') || errMsg.toLowerCase().includes('quota') || errMsg.toLowerCase().includes('exhausted');
        const isNotFound = errMsg.includes('404') || errMsg.toLowerCase().includes('not found') || errMsg.toLowerCase().includes('no longer available');
        const isOverloaded = errMsg.includes('503') || errMsg.includes('500') || errMsg.toLowerCase().includes('overloaded');

        if (isQuotaError || isNotFound || isOverloaded) {
          // Try next model in chain
          lastError = new Error(`${modelName} unavailable (${isQuotaError ? '429 quota' : isNotFound ? '404 not found' : '503 overloaded'})`);
          console.warn(`[GeminiPlanner] ${lastError.message} — trying next model`);
          continue;
        }

        // For other errors (auth, network, etc.) fail immediately
        throw err;
      }
    }

    throw new Error(`All Gemini models exhausted their daily quota. Please wait and try again tomorrow, or add billing at https://ai.dev. Last error: ${lastError.message}`);
  }
}
