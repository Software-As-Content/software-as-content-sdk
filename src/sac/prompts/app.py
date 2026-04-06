"""
App Prompts

Base generation prompts, system prompt construction, and model definitions.
Ported from: src/lib/app-prompts.ts
"""

from __future__ import annotations

from pathlib import Path

from sac.types import ModelOption

# ─── Available Models ──────────────────────────────────────────────

AVAILABLE_MODELS: list[ModelOption] = [
    # Google Gemini
    ModelOption(id="google/gemini-3-flash-preview", name="Gemini 3 Flash", provider="google"),
    ModelOption(id="google/gemini-3-pro-preview", name="Gemini 3 Pro", provider="google"),
    # Anthropic Claude
    ModelOption(id="anthropic/claude-opus-4.5", name="Claude Opus 4.5", provider="anthropic"),
    ModelOption(id="anthropic/claude-sonnet-4.5", name="Claude Sonnet 4.5", provider="anthropic"),
    ModelOption(id="anthropic/claude-haiku-4.5", name="Claude Haiku 4.5", provider="anthropic"),
    # OpenAI GPT
    ModelOption(id="openai/gpt-5.1", name="GPT-5.1", provider="openai"),
    ModelOption(id="openai/gpt-5.1-codex", name="GPT-5.1 Codex", provider="openai"),
    ModelOption(id="openai/gpt-5.1-codex-mini", name="GPT-5.1 Codex Mini", provider="openai"),
    # xAI Grok
    ModelOption(id="x-ai/grok-4", name="Grok 4", provider="xai"),
    ModelOption(id="x-ai/grok-4-fast", name="Grok 4 Fast", provider="xai"),
    # DeepSeek
    ModelOption(id="deepseek/deepseek-v3.2", name="DeepSeek V3.2", provider="deepseek"),
]

DEFAULT_MODEL = "google/gemini-3-flash-preview"

# ─── Base System Prompt ────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """You are an expert React developer. Generate a complete React component based on the user's request.

BASE REQUIREMENTS:
1. Make multi-pages with navigations for the app for better UX if necessary
2. Connect to the real links if any, but do not make fake buttons that have no effects.
3. DO NOT make up image urls!!! ONLY use the provided images IF NECESSARY (no need to use them all).

RESPONSE FORMAT REQUIREMENTS:
1. Output ONLY a single code block with valid TSX/JSX React code
2. The component MUST have a default export
3. Prefer using design system components via imports from "@/components/ui/*" whenever possible
4. Use Tailwind classes ONLY for layout tweaks and spacing; do NOT add custom CSS
5. Do NOT use <style> tags, styled-jsx, or any extra CSS files
6. Use lucide-react for icons (import from "lucide-react")
7. Include ALL necessary useState/useEffect hooks for interactivity
8. Allowed imports: React, lucide-react, recharts, pigeon-maps, and "@/components/ui/*" (and "@/lib/utils" only if needed for cn)
9. Do NOT include any explanation, just the code

MAP USAGE (pigeon-maps):
- Use pigeon-maps when the intent involves locations, addresses, routes, geospatial data, or anything map-related
- Import as: import { Map, Marker, ZoomControl } from "pigeon-maps"
- Basic usage: <Map center={[lat, lng]} zoom={13} height={400}>
- Add pins: <Marker anchor={[lat, lng]} color="red" width={40} />
- Always set an explicit pixel height on <Map> (e.g. height={400})
- Uses OpenStreetMap tiles by default — no API key required
- Example with multiple markers:
  import { Map, Marker } from "pigeon-maps"
  <Map center={[40.7128, -74.006]} zoom={12} height={500}>
    <Marker anchor={[40.7128, -74.006]} color="#f97316" width={36} />
  </Map>

EXAMPLE FORMAT:
```tsx
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function ComponentName() {
  return (
    <Card>
      <CardContent className="p-4">
        <Button>Action</Button>
      </CardContent>
    </Card>
  );
}
```"""

DEFAULT_CUSTOM_INSTRUCTIONS = "Create a modern, clean UI with good UX practices, keep the page always in full width."

# ─── Design System ─────────────────────────────────────────────────

_DESIGN_SYSTEM_DIR = Path(__file__).parent / "templates"


def get_design_system_content() -> str:
    """Load the design system reference document."""
    path = _DESIGN_SYSTEM_DIR / "design-system.md"
    return path.read_text(encoding="utf-8")


# ─── Prompt Builders ───────────────────────────────────────────────


def build_final_system_prompt(
    custom_instructions: str = "",
    include_design_system: bool = True,
) -> str:
    """
    Build the final system prompt by combining:
    1. Base system prompt (hidden, format requirements)
    2. Custom instructions (user-provided)
    3. Design system reference (optional)
    """
    prompt = BASE_SYSTEM_PROMPT

    if custom_instructions.strip():
        prompt += f"""

<custom-instructions>
{custom_instructions.strip()}
</custom-instructions>"""

    if include_design_system:
        design_system = get_design_system_content()
        prompt += f"""
<design-system-reference>
The following is the design system source.

DESIGN SYSTEM USAGE GUIDELINES:
- Prefer directly importing (from "@/components/ui/*") to use the existing components first (Button, Card, Dialog, Tabs, Table, Select, etc.)
- Only add Tailwind classes for composition/layout (spacing, flex/grid, width/height)
- Do NOT add custom CSS or style tags
- Keep the generated code concise; avoid duplicating component implementations

{design_system}
</design-system-reference>
"""

    return prompt


def build_generation_prompt(user_intent: str, system_prompt: str) -> str:
    """Build the final user prompt for generation."""
    return f"{system_prompt}\n\nUSER REQUEST: {user_intent}"
