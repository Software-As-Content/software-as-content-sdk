# Frontend Integration Guide

This guide explains how to connect any frontend to the SaC SDK HTTP server.

## Overview

```
Your Frontend (React, Vue, vanilla JS, etc.)
    │
    ├── POST /generate    → one-shot generation
    ├── POST /evolve      → evolve existing app
    ├── GET  /stream      → SSE streaming (recommended)
    └── GET  /conversations → list/get history
    │
    ▼
SaC SDK HTTP Server (python -m sac.cli serve)
```

## Start the Server

```bash
python -m sac.cli serve --port 8000
```

The server runs at `http://localhost:8000` with CORS enabled for all origins.

---

## Option 1: SSE Streaming (Recommended)

Use `EventSource` for real-time streaming. The server sends typed SSE events as the pipeline progresses.

### Event Types

| Event | Payload | When |
|-------|---------|------|
| `stage` | `{ type, name, status }` | Pipeline stage changes (analyze/search/generate × running/completed/error) |
| `search` | `{ type, queries, results }` | Search completed — contains real-time data before code generation starts |
| `chunk` | `{ type, data }` | Each LLM token during code generation |
| `complete` | `{ type, app, conversation_id }` | Generation finished — contains full App object |
| `error` | `{ type, error }` | Pipeline error |

### Example: React

```tsx
function useGenerate() {
  const [status, setStatus] = useState('idle');
  const [code, setCode] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [app, setApp] = useState(null);
  const [conversationId, setConversationId] = useState(null);

  const generate = useCallback((intent: string) => {
    setStatus('generating');
    setCode('');
    setSearchResults([]);

    const params = new URLSearchParams({ intent });
    if (conversationId) params.set('conversation_id', conversationId);

    const es = new EventSource(`http://localhost:8000/stream?${params}`);

    es.addEventListener('stage', (e) => {
      const { name, status } = JSON.parse(e.data);
      setStatus(`${name}: ${status}`);
    });

    es.addEventListener('search', (e) => {
      const { results } = JSON.parse(e.data);
      setSearchResults(results);
    });

    es.addEventListener('chunk', (e) => {
      const { data } = JSON.parse(e.data);
      setCode(prev => prev + data);
    });

    es.addEventListener('complete', (e) => {
      const payload = JSON.parse(e.data);
      setApp(payload.app);
      setConversationId(payload.conversation_id);
      setStatus('done');
      es.close();
    });

    es.addEventListener('error', (e) => {
      try {
        const { error } = JSON.parse(e.data);
        setStatus(`error: ${error}`);
      } catch {
        setStatus('connection error');
      }
      es.close();
    });

    return () => es.close(); // cleanup
  }, [conversationId]);

  return { generate, status, code, searchResults, app, conversationId };
}
```

### Example: Vanilla JS

```js
function streamGenerate(intent, conversationId, callbacks) {
  const params = new URLSearchParams({ intent });
  if (conversationId) params.set('conversation_id', conversationId);

  const es = new EventSource(`http://localhost:8000/stream?${params}`);

  es.addEventListener('stage', (e) => {
    callbacks.onStage?.(JSON.parse(e.data));
  });

  es.addEventListener('search', (e) => {
    callbacks.onSearch?.(JSON.parse(e.data));
  });

  es.addEventListener('chunk', (e) => {
    callbacks.onChunk?.(JSON.parse(e.data).data);
  });

  es.addEventListener('complete', (e) => {
    callbacks.onComplete?.(JSON.parse(e.data));
    es.close();
  });

  es.addEventListener('error', (e) => {
    callbacks.onError?.(e);
    es.close();
  });

  return () => es.close();
}

// Usage
streamGenerate('today news', null, {
  onStage: ({ name, status }) => console.log(`${name}: ${status}`),
  onSearch: ({ results }) => console.log('Search results:', results),
  onChunk: (token) => process.stdout.write(token),
  onComplete: ({ app, conversation_id }) => {
    console.log('Done! Code:', app.code.length, 'chars');
    console.log('Suggestions:', app.suggestions);
    // Use conversation_id for subsequent evolve calls
  },
});
```

---

## Option 2: REST API (One-shot)

For simpler integrations where streaming isn't needed.

### POST /generate

```js
const res = await fetch('http://localhost:8000/generate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    intent: '2026 travel guide for Hangzhou',
    web_search: true,           // default: true
    custom_instructions: '',     // optional
    use_design_system: true,     // default: true
  }),
});

const { success, conversation_id, app } = await res.json();
// app.code          — generated TSX code
// app.version       — version number (1 for first generation)
// app.suggestions   — [{label, prompt, type}, ...]
// app.search_results — [{query, answer, sources}, ...]
// app.stages        — [{name, status, duration}, ...]
```

### POST /evolve

```js
const res = await fetch('http://localhost:8000/evolve', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    intent: 'add restaurant recommendations',
    conversation_id: 'abc-123',  // from previous generate
  }),
});

const { success, conversation_id, app } = await res.json();
// app.growth_decision — { growth_type: "extend_current"|"new_page", reason }
```

---

## App Object Shape

Every generation returns an `App` object:

```ts
interface App {
  code: string;              // Generated TSX/React code
  version: number;           // 1, 2, 3, ...
  intent: string;            // The user intent that produced this
  parent_version: number | null;  // null for generate, previous version for evolve
  model: string;             // LLM model used
  search_queries: SearchQuery[];
  search_results: SearchResult[];
  suggestions: IntentSuggestion[];
  growth_decision: GrowthDecision | null;  // Only for evolve
  stages: StageSnapshot[];
  created_at: string;
}

interface SearchQuery {
  query: string;
  purpose: string;
}

interface SearchResult {
  query: string;
  answer: string | null;
  sources: { title: string; url: string; content: string }[];
  images: string[] | null;
}

interface IntentSuggestion {
  label: string;    // Short display label (2-4 words)
  prompt: string;   // Full prompt to use for next generate/evolve
  type: 'action' | 'explore' | 'refine' | 'enhance';
}

interface GrowthDecision {
  growth_type: 'extend_current' | 'new_page';
  reason: string;
}
```

---

## Rendering the Generated Code

The SDK generates TSX code that imports from `@/components/ui/*` (shadcn-style) and common libraries. To render it you need:

1. **Transpile TSX to JS** — Use Babel standalone, Sucrase, or your build tool
2. **Resolve imports** — Map `@/components/ui/*` to your component library or the SDK's shim
3. **Execute in sandbox** — Use iframe, Sandpack, or your own sandbox

### Using the SDK's Built-in Renderer

The SDK ships a standalone renderer module that handles all of this:

```html
<iframe id="preview"></iframe>

<script type="module">
import { SaCRenderer } from 'http://localhost:8000/renderer/sac-renderer.js';

const renderer = new SaCRenderer(document.getElementById('preview'), {
  previewUrl: 'http://localhost:8000/renderer/preview.html',
  designSystem: 'http://localhost:8000/renderer/design-systems/default/shim.js',
});

renderer.on('render', () => console.log('Rendered!'));
renderer.on('error', (err) => console.error('Render error:', err));

// One-shot
renderer.render(app.code);

// Or streaming
const stream = renderer.createStream();
// ... feed tokens via stream.push(token)
stream.end();
</script>
```

### Using Sandpack (Production)

For production-quality rendering, use [Sandpack](https://sandpack.codesandbox.io/):

```tsx
import { SandpackProvider, SandpackPreview } from '@codesandbox/sandpack-react';

<SandpackProvider
  template="react-ts"
  files={{ '/App.tsx': app.code }}
  customSetup={{ dependencies: { /* your design system deps */ } }}
>
  <SandpackPreview />
</SandpackProvider>
```

---

## Conversation Management

### GET /conversations

```js
const { conversations } = await fetch('http://localhost:8000/conversations').then(r => r.json());
// conversations: [{ id, title, created_at, updated_at, model, event_count, ... }]
```

### GET /conversations/:id

```js
const { conversation, events } = await fetch(`http://localhost:8000/conversations/${id}`).then(r => r.json());
// events: array of MessageEvent, GenerationEvent, GrowthEvent, ErrorEvent
```

---

## Typical Flow

```
1. User types intent
2. Frontend calls GET /stream?intent=...
3. Show "Analyzing..." on stage:analyze
4. Show "Searching..." on stage:search
5. Display search results on search event     ← user sees data before code
6. Show code streaming on chunk events
7. Render final code on complete event
8. Display suggestions from app.suggestions
9. User clicks suggestion → repeat from step 2 with conversation_id
```
