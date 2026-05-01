# Embedding SaC Apps in Your UI

You generated an app with the SaC SDK. Now you want to show it to your user
inside your own product. This doc covers the practical paths.

## Path 1 — Iframe a hosted share URL (zero infra)

The hosted product at [sac.dynsoft.ai](https://sac.dynsoft.ai) gives every app
a public read-only share URL. If your conversation lives on the hosted product,
just iframe it:

```html
<iframe
  src="https://sac.dynsoft.ai/share/HD0ypluRqNwZn2mh"
  width="100%"
  height="800"
  style="border:none;border-radius:12px"
  allow="clipboard-write"
></iframe>
```

Pros: nothing to host. Cons: requires the conversation to live on the hosted
product, not your own SaC SDK instance.

## Path 2 — Iframe your local `sac serve`

If you're running `sac serve` (e.g. as a backend for your own product), the
playground at `/` is iframe-friendly:

```html
<iframe src="http://your-sac-host/c/{conversation_id}" />
```

The HTTP server has CORS open by default — if you embed cross-origin, no
additional config needed.

## Path 3 — Bring your own renderer (full control)

If you want SaC code rendered inside _your_ React app (not iframed), you have
two layers:

### 3a. Reuse the bundled renderer

The SDK ships a vanilla-JS renderer at `src/sac/renderer/sac-renderer.js`. It
takes care of partial TSX repair, lucide-icon shimming, and `@/components/ui/*`
import resolution. Import it as an ES module from your `sac serve`:

```html
<iframe id="preview"></iframe>

<script type="module">
import { SaCRenderer } from 'http://your-sac-host/renderer/sac-renderer.js';

const renderer = new SaCRenderer(document.getElementById('preview'));
renderer.on('render', () => console.log('rendered'));
renderer.on('error', (e) => console.error(e));
renderer.render(appCode);   // app.code from /generate or /stream
</script>
```

See [`docs/frontend-integration.md`](./frontend-integration.md) for the full
contract (streaming, action callbacks, custom design system).

### 3b. Render with Sandpack or your own sandbox

For production-grade integration in a React app you control, transpile and
sandbox the TSX yourself. [Sandpack](https://sandpack.codesandbox.io/) is the
common choice:

```tsx
import { SandpackProvider, SandpackPreview } from '@codesandbox/sandpack-react';

<SandpackProvider
  template="react-ts"
  files={{ '/App.tsx': app.code }}
  customSetup={{
    dependencies: {
      'lucide-react': 'latest',
      recharts: 'latest',
      // ...your design system deps
    },
  }}
>
  <SandpackPreview />
</SandpackProvider>
```

You're now responsible for: import resolution, design-system shim, partial-TSX
repair (during streaming), and lucide-icon fallbacks. The bundled renderer
already handles all of these — only go this route if you have a hard
requirement to avoid iframes.

## Picking a path

| You... | Use |
|---|---|
| just want an SaC app visible somewhere | Path 1 (hosted iframe) |
| run your own SaC backend, want quick embedding | Path 2 (local iframe) |
| want SaC inside your own React app, no iframe | Path 3b (Sandpack) |
| want SaC inside an iframe, but use the SDK's renderer | Path 3a |

The default recommendation is **Path 1 or 2** — iframes solve real problems
(sandboxing, dependency isolation) for free. Reach for Path 3 only when iframes
are a non-starter (e.g. native UI shells, deeply integrated UX).
