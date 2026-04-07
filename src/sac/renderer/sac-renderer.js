/**
 * SaCRenderer — Independent, reusable renderer for SaC-generated TSX code.
 *
 * Usage:
 *   const renderer = new SaCRenderer(iframeElement, {
 *     previewUrl: '/renderer/preview.html',
 *     designSystem: '/renderer/design-systems/default/shim.js',
 *   });
 *
 *   // One-shot render
 *   renderer.render(tsxCode);
 *
 *   // Streaming render
 *   const stream = renderer.createStream();
 *   stream.push(token);
 *   stream.end();
 *
 *   // Events
 *   renderer.on('render', () => console.log('rendered'));
 *   renderer.on('error', (err) => console.error(err));
 */

export class SaCRenderer {
  constructor(iframeElement, options = {}) {
    this._iframe = iframeElement;
    this._previewUrl = options.previewUrl || '/renderer/preview.html';
    this._designSystem = options.designSystem || '/renderer/design-systems/default/shim.js';
    this._listeners = { render: [], error: [] };
    this._iframeReady = null; // Promise that resolves when iframe is loaded

    // Listen for messages from iframe
    this._messageHandler = (ev) => {
      if (!ev.data || !ev.data.type) return;
      if (ev.data.type === 'render-success') {
        this._emit('render');
      } else if (ev.data.type === 'render-error') {
        this._emit('error', ev.data.error);
      }
    };
    window.addEventListener('message', this._messageHandler);
  }

  // ─── One-shot render ──────────────────────────────────────────

  render(tsxCode) {
    const processed = this._processCode(tsxCode);
    this._ensureIframe(() => {
      this._sendToIframe(processed);
    });
  }

  // ─── Streaming render ─────────────────────────────────────────

  createStream() {
    let buffer = '';
    let debounceTimer = null;
    let lastTranspiledCode = null;
    const self = this;

    this._ensureIframe();

    const stream = {
      push(token) {
        buffer += token;
        // Accumulate only — rendering happens at end() when code is complete.
        // Intermediate TSX is almost never valid, so attempting render mid-stream
        // just produces noisy errors.
      },

      end() {
        const processed = self._processCode(buffer);
        self._sendToIframe(processed);
      },

      abort() {
        if (debounceTimer) {
          clearTimeout(debounceTimer);
          debounceTimer = null;
        }
        buffer = '';
        lastTranspiledCode = null;
        self._iframe.contentWindow?.postMessage({ type: 'abort' }, '*');
      },

      getCode() {
        return buffer;
      }
    };

    return stream;
  }

  // ─── Events ───────────────────────────────────────────────────

  on(event, callback) {
    if (this._listeners[event]) {
      this._listeners[event].push(callback);
    }
  }

  off(event, callback) {
    if (this._listeners[event]) {
      this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
    }
  }

  destroy() {
    window.removeEventListener('message', this._messageHandler);
    this._listeners = { render: [], error: [] };
  }

  // ─── Internal ─────────────────────────────────────────────────

  _emit(event, data) {
    for (const cb of this._listeners[event] || []) {
      cb(data);
    }
  }

  _processCode(code) {
    // Strip markdown fences (LLM may wrap code in ```tsx ... ```)
    let processed = code;
    const fenceMatch = processed.match(/```(?:tsx|jsx)?\s*\n([\s\S]*?)```/);
    if (fenceMatch) {
      processed = fenceMatch[1];
    } else if (processed.startsWith('```')) {
      // Streaming: opening fence seen but no closing fence yet — strip opening
      processed = processed.replace(/^```(?:tsx|jsx)?\s*\n/, '');
      // Also strip trailing ``` if present
      processed = processed.replace(/\n```\s*$/, '');
    }

    // Rewrite @/components/ui/* and @/lib/utils imports
    return processed
      .replace(/from\s+["']@\/components\/ui\/[^"']+["']/g, 'from "__ui_shim__"')
      .replace(/from\s+["']@\/lib\/utils["']/g, 'from "__ui_shim__"');
  }

  _ensureIframe(onReady) {
    if (this._iframeReady) {
      if (onReady) this._iframeReady.then(onReady);
      return;
    }
    this._iframeReady = new Promise((resolve) => {
      this._iframe.onload = () => resolve();
      this._iframe.src = this._previewUrl;
    });
    if (onReady) this._iframeReady.then(onReady);
  }

  async _sendToIframe(code) {
    if (this._iframeReady) await this._iframeReady;
    this._iframe.contentWindow?.postMessage({
      type: 'render',
      code: code,
      shimUrl: this._designSystem,
    }, '*');
  }

  _tryTranspile(code) {
    try {
      if (typeof Babel === 'undefined') {
        // Babel not loaded in parent — can't pre-check, let iframe handle it
        return { success: true, code: code };
      }
      const result = Babel.transform(code, {
        presets: ['react', 'typescript'],
        filename: 'App.tsx',
      });
      return { success: true, code: result.code };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }
}
