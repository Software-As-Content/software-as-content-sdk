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

export { autoClose };

export class SaCRenderer {
  constructor(iframeElement, options = {}) {
    this._iframe = iframeElement;
    this._previewUrl = options.previewUrl || '/renderer/preview.html';
    this._designSystem = options.designSystem || '/renderer/design-systems/default/shim.js';
    this._listeners = { render: [], error: [], action: [] };
    this._iframeReady = null;

    this._messageHandler = (ev) => {
      if (!ev.data || !ev.data.type) return;
      if (ev.data.type === 'render-success') {
        this._emit('render');
      } else if (ev.data.type === 'render-error') {
        this._emit('error', ev.data.error);
      } else if (ev.data.type === 'sac-action') {
        this._emit('action', { intent: ev.data.intent, context: ev.data.context || null });
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
    let renderTimer = null;
    let lastRenderedCode = null;  // last code sent to iframe
    let lastValidCode = null;     // last code that passed Babel transpile
    const self = this;

    this._ensureIframe();

    const RENDER_INTERVAL = 1500; // Send to iframe at most every 1.5s

    const stream = {
      push(token) {
        buffer += token;

        // Try autoClose + Babel transpile in parent (cheap, no iframe involved)
        const processed = self._processCode(buffer);
        const closed = autoClose(processed);
        if (closed) {
          const result = self._tryTranspile(closed);
          if (result.success) {
            lastValidCode = closed;
          }
        }

        // Throttle actual iframe renders to every 1.5s
        if (!renderTimer && lastValidCode) {
          renderTimer = setTimeout(() => {
            renderTimer = null;
            if (lastValidCode && lastValidCode !== lastRenderedCode) {
              lastRenderedCode = lastValidCode;
              self._sendToIframe(lastValidCode, true); // silent
            }
          }, RENDER_INTERVAL);
        }
      },

      end() {
        if (renderTimer) {
          clearTimeout(renderTimer);
          renderTimer = null;
        }
        // Final render with real complete code (no autoClose)
        const processed = self._processCode(buffer);
        self._sendToIframe(processed);
      },

      abort() {
        if (renderTimer) {
          clearTimeout(renderTimer);
          renderTimer = null;
        }
        buffer = '';
        lastRenderedCode = null;
        lastValidCode = null;
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
    this._listeners = { render: [], error: [], action: [] };
  }

  // ─── Internal ─────────────────────────────────────────────────

  _emit(event, data) {
    for (const cb of this._listeners[event] || []) {
      cb(data);
    }
  }

  _processCode(code, { skipAutoImport = false } = {}) {
    // Extract code from LLM response.
    // Evolve responses contain ```json (decision) + ```tsx (code).
    // Generate responses contain ```tsx (code) only.
    let processed = code;

    // Try to extract the last tsx/jsx fenced block (handles both generate and evolve)
    const tsxMatches = [...processed.matchAll(/```(?:tsx|jsx)\s*\n([\s\S]*?)```/g)];
    if (tsxMatches.length > 0) {
      processed = tsxMatches[tsxMatches.length - 1][1];
    } else {
      // No closed tsx fence — try any fenced block
      const anyMatch = processed.match(/```(?:tsx|jsx)?\s*\n([\s\S]*?)```/);
      if (anyMatch) {
        processed = anyMatch[1];
      } else if (processed.includes('```tsx')) {
        // Streaming: tsx fence opened but not closed yet
        processed = processed.split(/```tsx\s*\n/).pop() || processed;
        processed = processed.replace(/\n```\s*$/, '');
      } else if (processed.startsWith('```')) {
        processed = processed.replace(/^```(?:tsx|jsx)?\s*\n/, '');
        processed = processed.replace(/\n```\s*$/, '');
      }
    }

    processed = this._rewriteLucideImports(processed);

    // Rewrite @/components/ui/* and @/lib/utils imports
    processed = processed
      .replace(/from\s+["']@\/components\/ui\/[^"']+["']/g, 'from "__ui_shim__"')
      .replace(/from\s+["']@\/lib\/utils["']/g, 'from "__ui_shim__"');

    // Auto-import missing shim components (skip during streaming).
    // LLMs frequently use a shadcn component in JSX but forget the import.
    // During streaming, partial code may be missing its own imports that
    // haven't arrived yet — patching would cause duplicate-identifier errors.
    if (!skipAutoImport) {
      processed = _autoImportMissingShimComponents(processed);
    }

    return processed;
  }

  _rewriteLucideImports(code) {
    let importIndex = 0;
    return code.replace(
      /import\s*\{([\s\S]*?)\}\s*from\s*["']lucide-react["'];?/g,
      (_match, specifiers) => {
        const ns = `__SaCLucide${importIndex++}`;
        const bindings = specifiers
          .split(',')
          .map((part) => part.trim())
          .filter(Boolean)
          .map((part) => {
            const cleaned = part.replace(/^type\s+/, '').trim();
            const aliasMatch = cleaned.match(/^([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)$/);
            const exported = aliasMatch ? aliasMatch[1] : cleaned;
            const local = aliasMatch ? aliasMatch[2] : cleaned;
            if (!/^[A-Za-z_$][\w$]*$/.test(exported) || !/^[A-Za-z_$][\w$]*$/.test(local)) {
              return '';
            }
            return `const ${local} = ${ns}.${exported} || ${ns}.ShieldCheck || ${ns}.Circle;`;
          })
          .filter(Boolean)
          .join('\n');
        return `import * as ${ns} from "lucide-react";\n${bindings}`;
      }
    );
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

  _tryTranspile(code) {
    try {
      if (typeof Babel === 'undefined') {
        return { success: false, error: 'Babel not loaded' };
      }
      Babel.transform(code, {
        presets: ['react', 'typescript'],
        filename: 'App.tsx',
      });
      return { success: true };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async _sendToIframe(code, silent = false) {
    if (this._iframeReady) await this._iframeReady;
    this._iframe.contentWindow?.postMessage({
      type: 'render',
      code: code,
      shimUrl: this._designSystem,
      silent: silent, // iframe won't report errors for silent renders
    }, '*');
  }
}


// ─── Auto-import missing shim components ────────────────────────────
//
// LLMs occasionally use a shadcn component (<Table>, <Dialog>, ...) in JSX
// but forget to write the matching import statement. At runtime the module
// lookup fails with "X is not defined".
//
// This whitelist is the set of component names that shim.js exports.
// `_autoImportMissingShimComponents` scans the code for capital-letter JSX
// tags that aren't already in scope, and if any match the whitelist, prepends
// a consolidated import line. Only runs on final (non-streaming) code.

const _SHIM_COMPONENTS = new Set([
  "Accordion", "AccordionContent", "AccordionItem", "AccordionTrigger",
  "Alert", "AlertDescription", "AlertTitle",
  "AlertDialog", "AlertDialogAction", "AlertDialogCancel", "AlertDialogContent",
  "AlertDialogDescription", "AlertDialogFooter", "AlertDialogHeader",
  "AlertDialogTitle", "AlertDialogTrigger",
  "Avatar", "AvatarFallback", "AvatarImage",
  "Badge",
  "Breadcrumb", "BreadcrumbItem", "BreadcrumbLink",
  "BreadcrumbList", "BreadcrumbPage", "BreadcrumbSeparator",
  "Button",
  "Card", "CardContent", "CardDescription", "CardFooter", "CardHeader", "CardTitle",
  "Checkbox",
  "Collapsible", "CollapsibleContent", "CollapsibleTrigger",
  "Dialog", "DialogClose", "DialogContent", "DialogDescription",
  "DialogHeader", "DialogTitle", "DialogTrigger",
  "Drawer", "DrawerClose", "DrawerContent", "DrawerDescription",
  "DrawerFooter", "DrawerHeader", "DrawerTitle", "DrawerTrigger",
  "DropdownMenu", "DropdownMenuContent", "DropdownMenuGroup", "DropdownMenuItem",
  "DropdownMenuLabel", "DropdownMenuSeparator", "DropdownMenuTrigger",
  "HoverCard", "HoverCardContent", "HoverCardTrigger",
  "Input", "Label",
  "Menubar", "MenubarContent", "MenubarItem", "MenubarMenu",
  "MenubarSeparator", "MenubarTrigger",
  "NavigationMenu", "NavigationMenuContent", "NavigationMenuItem",
  "NavigationMenuLink", "NavigationMenuList", "NavigationMenuTrigger",
  "Pagination", "PaginationContent", "PaginationItem",
  "PaginationLink", "PaginationNext", "PaginationPrevious",
  "Popover", "PopoverContent", "PopoverTrigger",
  "Progress",
  "RadioGroup", "RadioGroupItem",
  "ResizableHandle", "ResizablePanel", "ResizablePanelGroup",
  "ScrollArea",
  "Select", "SelectContent", "SelectItem", "SelectTrigger", "SelectValue",
  "Separator",
  "Sheet", "SheetClose", "SheetContent", "SheetDescription",
  "SheetHeader", "SheetTitle", "SheetTrigger",
  "Skeleton", "Slider", "Spinner", "Switch",
  "Table", "TableBody", "TableCell", "TableHead", "TableHeader", "TableRow",
  "Tabs", "TabsContent", "TabsList", "TabsTrigger",
  "Textarea",
  "Toggle", "ToggleGroup",
  "Tooltip", "TooltipContent", "TooltipProvider", "TooltipTrigger",
]);

function _autoImportMissingShimComponents(code) {
  // 1. Collect capital-letter JSX tag names used in the code.
  const usedTags = new Set();
  const jsxRegex = /<\s*([A-Z][A-Za-z0-9_]*)/g;
  let m;
  while ((m = jsxRegex.exec(code)) !== null) {
    usedTags.add(m[1]);
  }
  if (usedTags.size === 0) return code;

  // 2. Collect names already in scope: named imports, default/namespace
  //    imports, and top-level const/let/var/function/class declarations.
  const inScope = new Set();

  // Named imports: `import { A, B as Alias } from "..."`
  const namedImportRegex = /import\s+\{([^}]+)\}\s*from\s*["'][^"']+["']/g;
  while ((m = namedImportRegex.exec(code)) !== null) {
    for (const raw of m[1].split(",")) {
      const trimmed = raw.trim();
      if (/^type\s+/.test(trimmed)) continue;
      const parts = trimmed.split(/\s+as\s+/i);
      const name = parts[parts.length - 1].trim();
      if (name) inScope.add(name);
    }
  }

  // Default / namespace imports
  const defaultImportRegex = /import\s+(?:\*\s+as\s+)?([A-Z][A-Za-z0-9_]*)\s*(?:,|from)/g;
  while ((m = defaultImportRegex.exec(code)) !== null) {
    inScope.add(m[1]);
  }

  // Local top-level declarations
  const localDeclRegex = /\b(?:const|let|var|function|class)\s+([A-Z][A-Za-z0-9_]*)/g;
  while ((m = localDeclRegex.exec(code)) !== null) {
    inScope.add(m[1]);
  }

  // 3. Diff: usedTags - inScope, filtered by shim whitelist
  const missing = [];
  for (const name of usedTags) {
    if (inScope.has(name)) continue;
    if (_SHIM_COMPONENTS.has(name)) missing.push(name);
  }
  if (missing.length === 0) return code;

  // 4. Inject a consolidated import at the top
  const importLine = `import { ${missing.join(", ")} } from "__ui_shim__";\n`;
  console.debug("[SaCRenderer] auto-imported missing shim components:", missing);
  return importLine + code;
}


// ─── autoClose: Smart JSX/JS bracket completion ──────────────────
//
// Takes partial TSX code and appends closing tags/brackets to make it
// syntactically valid. Used during streaming to render intermediate states.
//
// Strategy: scan through code tracking a stack of open constructs.
// At the end, close everything in reverse order.

function autoClose(code) {
  // Must have at least a function body started to attempt render
  if (!code.includes('export default function') && !code.includes('export default')) {
    return null; // Too early — haven't seen the component definition yet
  }

  const stack = []; // Stack of { type: 'jsx'|'paren'|'brace', tag?: string }
  let i = 0;
  const len = code.length;
  let inString = false;
  let stringChar = '';
  let inComment = false;
  let inLineComment = false;
  let inTemplateLiteral = false;

  while (i < len) {
    const ch = code[i];
    const next = i + 1 < len ? code[i + 1] : '';

    // Handle string literals
    if (inString) {
      if (ch === '\\') { i += 2; continue; }
      if (ch === stringChar) { inString = false; }
      i++; continue;
    }

    // Handle template literals
    if (inTemplateLiteral) {
      if (ch === '\\') { i += 2; continue; }
      if (ch === '`') { inTemplateLiteral = false; }
      i++; continue;
    }

    // Handle comments
    if (inLineComment) {
      if (ch === '\n') { inLineComment = false; }
      i++; continue;
    }
    if (inComment) {
      if (ch === '*' && next === '/') { inComment = false; i += 2; continue; }
      i++; continue;
    }

    // Enter string/comment
    if (ch === '"' || ch === "'") { inString = true; stringChar = ch; i++; continue; }
    if (ch === '`') { inTemplateLiteral = true; i++; continue; }
    if (ch === '/' && next === '/') { inLineComment = true; i += 2; continue; }
    if (ch === '/' && next === '*') { inComment = true; i += 2; continue; }

    // Track braces and parens
    if (ch === '{') { stack.push({ type: 'brace' }); i++; continue; }
    if (ch === '}') {
      // Pop last brace
      for (let j = stack.length - 1; j >= 0; j--) {
        if (stack[j].type === 'brace') { stack.splice(j, 1); break; }
      }
      i++; continue;
    }
    if (ch === '(') { stack.push({ type: 'paren' }); i++; continue; }
    if (ch === ')') {
      for (let j = stack.length - 1; j >= 0; j--) {
        if (stack[j].type === 'paren') { stack.splice(j, 1); break; }
      }
      i++; continue;
    }

    // Track JSX tags
    if (ch === '<') {
      // Check for closing tag
      if (next === '/') {
        // Find tag name: </TagName>
        const closeMatch = code.slice(i).match(/^<\/\s*([A-Za-z][A-Za-z0-9.]*)\s*>/);
        if (closeMatch) {
          const tagName = closeMatch[1];
          // Pop matching open tag from stack
          for (let j = stack.length - 1; j >= 0; j--) {
            if (stack[j].type === 'jsx' && stack[j].tag === tagName) {
              stack.splice(j, 1);
              break;
            }
          }
          i += closeMatch[0].length;
          continue;
        }
      }

      // Check for opening tag (not a comparison operator)
      const openMatch = code.slice(i).match(/^<\s*([A-Z][A-Za-z0-9.]*)/);
      if (openMatch) {
        const tagName = openMatch[1];
        // Check if self-closing: find the > and see if preceded by /
        const restFromTag = code.slice(i);
        const tagEndMatch = restFromTag.match(/^<[^>]*?(\/?)>/);
        if (tagEndMatch) {
          if (tagEndMatch[1] !== '/') {
            // Opening tag, not self-closing
            stack.push({ type: 'jsx', tag: tagName });
          }
          i += tagEndMatch[0].length;
          continue;
        } else {
          // Tag not closed yet (mid-stream) — assume it will be opening
          // Don't add to stack since tag itself isn't complete
          i++;
          continue;
        }
      }
    }

    i++;
  }

  // If stack is empty, code is already balanced
  if (stack.length === 0) return code;

  // Build closing sequence in reverse
  let closing = '\n';
  for (let j = stack.length - 1; j >= 0; j--) {
    const item = stack[j];
    if (item.type === 'jsx') {
      closing += `</${item.tag}>`;
    } else if (item.type === 'paren') {
      closing += ')';
    } else if (item.type === 'brace') {
      closing += '}';
    }
  }

  return code + closing;
}
