export function executeVoiceCommand(command: string, arg?: string): boolean {
  console.log(`[IntentLock] Executing voice command: ${command}`, arg);
  
  switch (command) {
    case 'SCROLL_DOWN':
      window.scrollBy({ top: window.innerHeight * 0.5, behavior: 'smooth' });
      return true;
    case 'SCROLL_UP':
      window.scrollBy({ top: -window.innerHeight * 0.5, behavior: 'smooth' });
      return true;
    case 'SCROLL_TOP':
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return true;
    case 'SCROLL_BOTTOM':
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      return true;
    case 'GO_BACK':
      window.history.back();
      return true;
    case 'GO_FORWARD':
      window.history.forward();
      return true;
    case 'FOCUS': {
      if (!arg) return false;
      const target = arg.toLowerCase();
      // Try to find inputs by placeholder, name, or id
      const inputs = Array.from(document.querySelectorAll('input, textarea')) as HTMLInputElement[];
      for (const input of inputs) {
        const text = `${input.placeholder} ${input.name} ${input.id}`.toLowerCase();
        if (text.includes(target)) {
          input.focus();
          return true;
        }
      }
      return false;
    }
    case 'CLICK_TEXT': {
      if (!arg) return false;
      const target = arg.toLowerCase();
      const clickables = Array.from(document.querySelectorAll('a, button, [role="button"]')) as HTMLElement[];
      for (const el of clickables) {
        if (el.innerText && el.innerText.toLowerCase().includes(target)) {
          el.click();
          return true;
        }
      }
      return false;
    }
    case 'CLICK_NUMBER': {
      if (!arg) return false;
      const num = parseInt(arg, 10);
      if (isNaN(num)) return false;
      // Just click the N-th clickable in the viewport for now
      const clickables = Array.from(document.querySelectorAll('a, button, [role="button"]')) as HTMLElement[];
      const inView = clickables.filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight && rect.height > 0;
      });
      if (num >= 1 && num <= inView.length) {
        inView[num - 1].click();
        return true;
      }
      return false;
    }
    case 'TYPE': {
      if (!arg) return false;
      const el = document.activeElement as HTMLInputElement | HTMLTextAreaElement;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) {
        if (el.isContentEditable) {
          el.textContent = (el.textContent || '') + arg;
        } else {
          el.value = (el.value || '') + arg;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
      return false;
    }
    default:
      return false;
  }
}
