/**
 * SaC Default Design System — UI Component Shim
 *
 * Lightweight implementations of shadcn/ui components for browser rendering.
 * These are simplified HTML wrappers with Tailwind classes, not full Radix UI components.
 *
 * To create a custom design system, provide your own shim.js that exports
 * the same component names with your own implementations.
 */

import React from "react";

const e = React.createElement;

// Props that are valid in shadcn/Radix but not on DOM elements
const _strip = new Set(['asChild', 'onValueChange', 'onCheckedChange', 'onSelect', 'onOpenChange', 'sideOffset', 'align', 'collapsible', 'defaultValue', 'orientation', 'decorative', 'variant', 'size']);

// ─── Tailwind class smart-merge (lightweight tailwind-merge stand-in) ─
//
// Problem: Tailwind JIT doesn't respect class-string order when two
// utilities from the same category appear together (e.g. `bg-orange-500`
// and `bg-white`). The one that ends up later in the compiled CSS wins,
// which is often NOT the call site's class. This silently caused contrast
// bugs whenever a shim component's variant defaults conflicted with the
// generated code's overrides.
//
// Fix: a minimal, regex-driven last-wins merger. Only the utility groups
// that actually bite are handled — everything else passes through
// untouched, so unknown/unusual classes are never dropped.

const TW_HUE = "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const TW_SPECIAL = "white|black|transparent|current|inherit";
const TW_COLOR = `(?:${TW_SPECIAL}|(?:${TW_HUE})(?:-\\d{2,3})?)`;
const TW_TEXT_SIZE = "(?:xs|sm|base|lg|[2-9]xl|\\[[^\\]]+\\])";
const TW_SPACING = "(?:\\d+(?:\\.\\d+)?|px|auto|full|screen|min|max|fit|\\[[^\\]]+\\])";

const CONFLICT_GROUPS = [
  { key: "bg",               re: new RegExp(`^bg-${TW_COLOR}$`) },
  { key: "text-color",       re: new RegExp(`^text-${TW_COLOR}$`) },
  { key: "text-size",        re: new RegExp(`^text-${TW_TEXT_SIZE}$`) },
  { key: "border-color",     re: new RegExp(`^border-${TW_COLOR}$`) },
  { key: "hover-bg",         re: new RegExp(`^hover:bg-${TW_COLOR}$`) },
  { key: "hover-text-color", re: new RegExp(`^hover:text-${TW_COLOR}$`) },
  { key: "h",                re: new RegExp(`^h-${TW_SPACING}$`) },
  { key: "w",                re: new RegExp(`^w-${TW_SPACING}$`) },
];

function smartMerge(tokens) {
  const groupIdx = new Map();
  const result = [];
  for (const token of tokens) {
    let matchedKey = null;
    for (const { key, re } of CONFLICT_GROUPS) {
      if (re.test(token)) { matchedKey = key; break; }
    }
    if (matchedKey) {
      if (groupIdx.has(matchedKey)) {
        result[groupIdx.get(matchedKey)] = null;
      }
      result.push(token);
      groupIdx.set(matchedKey, result.length - 1);
    } else {
      result.push(token);
    }
  }
  return result.filter((t) => t !== null).join(" ");
}

// ─── Utility ──────────────────────────────────────────────────────

export function cn(...classes) {
  const tokens = classes
    .flat(Infinity)
    .filter(Boolean)
    .join(" ")
    .split(/\s+/)
    .filter(Boolean);
  return smartMerge(tokens);
}

const fwd = (tag, base) =>
  React.forwardRef(({ className, ...p }, ref) => {
    const clean = {};
    for (const k in p) { if (!_strip.has(k)) clean[k] = p[k]; }
    return e(tag, { ref, className: cn(base, className), ...clean });
  });

// ─── Button ───────────────────────────────────────────────────────

// Detect "SaC action" buttons — those whose onClick triggers the
// `window.__sac_action` bridge back to the agent. We stringify the handler
// and look for the literal `__sac_action` token. This covers arrow
// functions (`() => window.__sac_action(...)`), wrapped handlers, and
// function declarations. The detected flag flows to the DOM as
// `data-sac-action="true"` so CSS in preview.html can show the indicator.
function _isSacActionHandler(fn) {
  if (typeof fn !== "function") return false;
  try {
    return /__sac_action/.test(Function.prototype.toString.call(fn));
  } catch {
    return false;
  }
}

export const Button = React.forwardRef(({ className, variant, size, onClick, ...p }, ref) => {
  const base = "inline-flex items-center justify-center rounded-lg font-medium text-sm cursor-pointer border-none transition-colors";
  const variants = {
    default: "bg-orange-500 text-white hover:bg-orange-600",
    destructive: "bg-red-500 text-white hover:bg-red-600",
    outline: "border border-gray-200 bg-white text-gray-900 hover:bg-gray-100",
    secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",
    ghost: "hover:bg-gray-100",
    link: "text-orange-500 underline-offset-4 hover:underline",
  };
  const sizes = {
    default: "h-10 px-4 py-2",
    sm: "h-9 px-3 text-xs",
    lg: "h-11 px-8",
    icon: "h-10 w-10",
  };
  const isSacAction = _isSacActionHandler(onClick);
  return e("button", {
    ref,
    className: cn(base, variants[variant] || variants.default, sizes[size] || sizes.default, className),
    onClick,
    ...(isSacAction && { "data-sac-action": "true" }),
    ...p,
  });
});

// ─── Card ─────────────────────────────────────────────────────────

export const Card = fwd("div", "rounded-2xl border border-gray-200 bg-white shadow-sm");
export const CardHeader = fwd("div", "p-6 pb-0");
export const CardTitle = fwd("h3", "text-lg font-semibold");
export const CardDescription = fwd("p", "text-sm text-gray-600 mt-1");
export const CardContent = fwd("div", "p-6");
export const CardFooter = fwd("div", "p-6 pt-0");

// ─── Badge ────────────────────────────────────────────────────────

export const Badge = React.forwardRef(({ className, variant, ...p }, ref) => {
  const base = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";
  const variants = {
    default: "bg-orange-100 text-orange-800",
    secondary: "bg-gray-100 text-gray-800",
    destructive: "bg-red-100 text-red-800",
    outline: "border border-gray-200 text-gray-800",
  };
  return e("span", { ref, className: cn(base, variants[variant] || variants.default, className), ...p });
});

// ─── Input / Textarea ─────────────────────────────────────────────

export const Input = React.forwardRef(({ className, ...p }, ref) =>
  e("input", { ref, className: cn("flex h-10 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm", className), ...p })
);

export const Textarea = React.forwardRef(({ className, ...p }, ref) =>
  e("textarea", { ref, className: cn("flex min-h-[80px] w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm", className), ...p })
);

// ─── Label ────────────────────────────────────────────────────────

export const Label = fwd("label", "text-sm font-medium");

// ─── Separator ────────────────────────────────────────────────────

export const Separator = fwd("hr", "border-gray-200 my-4");

// ─── ScrollArea ───────────────────────────────────────────────────

export const ScrollArea = fwd("div", "overflow-auto");

// ─── Tabs ─────────────────────────────────────────────────────────
//
// Real implementation — the fwd helper strips `onValueChange` and
// `defaultValue` as invalid DOM props, which silently turns every
// <Tabs> into a stateless div (all TabsContent stacked, clicks do
// nothing). Uses React Context so TabsTrigger and TabsContent can
// coordinate active state.

const TabsContext = React.createContext({ value: "", setValue: () => {} });

export const Tabs = React.forwardRef(
  ({ className, value, defaultValue, onValueChange, children, ...p }, ref) => {
    const [internal, setInternal] = React.useState(defaultValue || "");
    const current = value !== undefined ? value : internal;
    const setValue = (next) => {
      if (value === undefined) setInternal(next);
      if (onValueChange) onValueChange(next);
    };
    return e(
      TabsContext.Provider,
      { value: { value: current, setValue } },
      e("div", { ref, className, ...p }, children)
    );
  }
);

export const TabsList = fwd("div", "inline-flex h-10 items-center rounded-lg bg-gray-100 p-1 gap-1");

export const TabsTrigger = React.forwardRef(
  ({ className, value, children, ...p }, ref) => {
    const ctx = React.useContext(TabsContext);
    const isActive = ctx.value === value;
    const base =
      "inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-md cursor-pointer border-none transition-all";
    const stateCls = isActive
      ? "bg-white text-gray-900 shadow-sm"
      : "bg-transparent text-gray-500 hover:text-gray-900";
    return e(
      "button",
      {
        ref,
        type: "button",
        role: "tab",
        "aria-selected": isActive,
        "data-state": isActive ? "active" : "inactive",
        "data-tab-value": value,
        className: cn(base, stateCls, className),
        onClick: () => ctx.setValue(value),
        ...p,
      },
      children
    );
  }
);

export const TabsContent = React.forwardRef(
  ({ className, value, children, ...p }, ref) => {
    const ctx = React.useContext(TabsContext);
    const isActive = ctx.value === value;
    return e(
      "div",
      {
        ref,
        role: "tabpanel",
        "data-state": isActive ? "active" : "inactive",
        "data-tab-value": value,
        className: cn("mt-2", className),
        style: isActive ? undefined : { display: "none" },
        ...p,
      },
      children
    );
  }
);

// ─── Avatar ───────────────────────────────────────────────────────

export const Avatar = fwd("div", "relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full bg-gray-200");
export const AvatarImage = ({ className, ...p }) =>
  e("img", { ...p, className: cn("aspect-square h-full w-full object-cover", className) });
export const AvatarFallback = fwd("span", "flex h-full w-full items-center justify-center rounded-full bg-gray-200 text-sm");

// ─── Progress ─────────────────────────────────────────────────────

export const Progress = ({ value, className, ...p }) =>
  e("div", { className: cn("relative h-2 w-full overflow-hidden rounded-full bg-gray-100", className), ...p },
    e("div", { className: "h-full bg-orange-500 transition-all rounded-full", style: { width: (value || 0) + "%" } })
  );

// ─── Select ───────────────────────────────────────────────────────

export const Select = fwd("select", "h-10 rounded-lg border border-gray-200 px-3 text-sm");
export const SelectTrigger = fwd("button", "flex h-10 w-full items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm");
export const SelectValue = fwd("span", "");
export const SelectContent = fwd("div", "");
export const SelectItem = fwd("option", "");

// ─── Switch ───────────────────────────────────────────────────────

export const Switch = ({ checked, onCheckedChange, className, ...p }) =>
  e("button", {
    role: "switch", "aria-checked": checked,
    onClick: () => onCheckedChange && onCheckedChange(!checked),
    className: cn(
      "relative inline-flex h-6 w-11 items-center rounded-full cursor-pointer border-none",
      checked ? "bg-orange-500" : "bg-gray-200",
      className
    ),
    ...p
  }, e("span", { className: "inline-block h-4 w-4 rounded-full bg-white transition-transform " + (checked ? "translate-x-6" : "translate-x-1") }));

// ─── Checkbox ─────────────────────────────────────────────────────

export const Checkbox = ({ checked, onCheckedChange, className, ...p }) =>
  e("input", { type: "checkbox", checked, onChange: (ev) => onCheckedChange && onCheckedChange(ev.target.checked), className: cn("h-4 w-4 rounded", className), ...p });

// ─── RadioGroup ───────────────────────────────────────────────────

export const RadioGroup = fwd("div", "flex flex-col gap-2");
export const RadioGroupItem = ({ value, checked, ...p }) => e("input", { type: "radio", value, checked, className: "h-4 w-4", ...p });

// ─── Slider ───────────────────────────────────────────────────────

export const Slider = ({ value, onValueChange, min = 0, max = 100, step = 1, className, ...p }) =>
  e("input", { type: "range", value: Array.isArray(value) ? value[0] : value, onChange: (ev) => onValueChange && onValueChange([Number(ev.target.value)]), min, max, step, className: cn("w-full", className), ...p });

// ─── Table ────────────────────────────────────────────────────────

export const Table = fwd("table", "w-full caption-bottom text-sm");
export const TableHeader = fwd("thead", "");
export const TableBody = fwd("tbody", "");
export const TableRow = fwd("tr", "border-b border-gray-200");
export const TableHead = fwd("th", "h-12 px-4 text-left font-medium text-gray-600");
export const TableCell = fwd("td", "p-4");
export const TableCaption = fwd("caption", "mt-4 text-sm text-gray-600");

// ─── Dialog ───────────────────────────────────────────────────────

export const Dialog = ({ children, open }) => open ? e("div", { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/50" }, children) : null;
export const DialogContent = fwd("div", "bg-white rounded-2xl p-6 shadow-lg max-w-lg w-full mx-4");
export const DialogHeader = fwd("div", "mb-4");
export const DialogFooter = fwd("div", "flex justify-end gap-2 mt-4");
export const DialogTitle = fwd("h2", "text-lg font-semibold");
export const DialogDescription = fwd("p", "text-sm text-gray-600");
export const DialogTrigger = fwd("button", "");
export const DialogClose = fwd("button", "");

// ─── Alert ────────────────────────────────────────────────────────

export const Alert = React.forwardRef(({ className, variant, ...p }, ref) => {
  const base = "relative w-full rounded-lg border p-4";
  const variants = {
    default: "bg-white text-gray-900 border-gray-200",
    destructive: "bg-red-50 text-red-900 border-red-200",
  };
  return e("div", { ref, role: "alert", className: cn(base, variants[variant] || variants.default, className), ...p });
});
export const AlertTitle = fwd("h5", "mb-1 font-medium leading-none");
export const AlertDescription = fwd("p", "text-sm text-gray-600");

// ─── AlertDialog ──────────────────────────────────────────────────

export const AlertDialog = Dialog;
export const AlertDialogContent = DialogContent;
export const AlertDialogHeader = DialogHeader;
export const AlertDialogTitle = DialogTitle;
export const AlertDialogDescription = DialogDescription;
export const AlertDialogTrigger = DialogTrigger;
export const AlertDialogAction = fwd("button", "px-4 py-2 rounded-lg bg-orange-500 text-white");
export const AlertDialogCancel = fwd("button", "px-4 py-2 rounded-lg border border-gray-200");
export const AlertDialogFooter = fwd("div", "flex justify-end gap-2 mt-4");

// ─── Sheet ────────────────────────────────────────────────────────

export const Sheet = Dialog;
export const SheetContent = fwd("div", "fixed inset-y-0 right-0 z-50 w-80 bg-white shadow-lg p-6");
export const SheetHeader = DialogHeader;
export const SheetTitle = DialogTitle;
export const SheetDescription = DialogDescription;
export const SheetTrigger = fwd("button", "");
export const SheetClose = fwd("button", "");

// ─── Tooltip ──────────────────────────────────────────────────────

export const Tooltip = ({ children }) => children;
export const TooltipContent = fwd("div", "");
export const TooltipProvider = ({ children }) => children;
export const TooltipTrigger = fwd("div", "");

// ─── Popover ──────────────────────────────────────────────────────

export const Popover = ({ children }) => children;
export const PopoverTrigger = fwd("button", "");
export const PopoverContent = fwd("div", "bg-white border border-gray-200 rounded-lg shadow-lg p-4");

// ─── Accordion ────────────────────────────────────────────────────

export const Accordion = fwd("div", "");
export const AccordionItem = fwd("div", "border-b border-gray-200");
export const AccordionTrigger = fwd("button", "flex w-full items-center justify-between py-4 font-medium cursor-pointer border-none bg-transparent text-left");
export const AccordionContent = fwd("div", "pb-4 text-sm");

// ─── DropdownMenu ─────────────────────────────────────────────────

export const DropdownMenu = ({ children }) => children;
export const DropdownMenuTrigger = fwd("button", "");
export const DropdownMenuContent = fwd("div", "bg-white border border-gray-200 rounded-lg shadow-lg p-1");
export const DropdownMenuItem = fwd("div", "px-3 py-2 text-sm cursor-pointer hover:bg-gray-100 rounded");
export const DropdownMenuSeparator = () => e("hr", { className: "my-1 border-gray-200" });
export const DropdownMenuLabel = fwd("div", "px-3 py-2 text-sm font-semibold");
export const DropdownMenuGroup = fwd("div", "");

// ─── Breadcrumb ───────────────────────────────────────────────────

export const Breadcrumb = fwd("nav", "");
export const BreadcrumbList = fwd("ol", "flex items-center gap-1.5 text-sm text-gray-600");
export const BreadcrumbItem = fwd("li", "inline-flex items-center gap-1.5");
export const BreadcrumbLink = fwd("a", "hover:text-gray-900 cursor-pointer");
export const BreadcrumbPage = fwd("span", "text-gray-900 font-medium");
export const BreadcrumbSeparator = () => e("span", { className: "text-gray-400" }, "/");
export const BreadcrumbEllipsis = () => e("span", { className: "text-gray-400" }, "…");

// ─── Skeleton ─────────────────────────────────────────────────────

export const Skeleton = fwd("div", "animate-pulse rounded-md bg-gray-200");

// ─── Spinner ──────────────────────────────────────────────────────

export const Spinner = ({ className, ...p }) =>
  e("div", { className: cn("h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-orange-500", className), ...p });

// ─── Toggle ───────────────────────────────────────────────────────

export const Toggle = fwd("button", "inline-flex items-center justify-center rounded-md text-sm font-medium h-10 px-3 bg-transparent hover:bg-gray-100 cursor-pointer border-none");
export const ToggleGroup = fwd("div", "flex items-center gap-1");
export const ToggleGroupItem = fwd("button", "inline-flex items-center justify-center rounded-md text-sm font-medium h-10 px-3 bg-transparent hover:bg-gray-100 cursor-pointer border-none");

// ─── Collapsible ──────────────────────────────────────────────────

export const Collapsible = fwd("div", "");
export const CollapsibleTrigger = fwd("button", "cursor-pointer border-none bg-transparent");
export const CollapsibleContent = fwd("div", "");

// ─── HoverCard ────────────────────────────────────────────────────

export const HoverCard = ({ children }) => children;
export const HoverCardTrigger = fwd("div", "cursor-pointer");
export const HoverCardContent = fwd("div", "bg-white border border-gray-200 rounded-lg shadow-lg p-4");

// ─── Pagination ───────────────────────────────────────────────────

export const Pagination = fwd("nav", "flex justify-center");
export const PaginationContent = fwd("ul", "flex items-center gap-1");
export const PaginationItem = fwd("li", "");
export const PaginationLink = fwd("button", "h-10 w-10 inline-flex items-center justify-center rounded-lg border border-gray-200 text-sm cursor-pointer bg-white hover:bg-gray-100");
export const PaginationPrevious = fwd("button", "h-10 px-3 inline-flex items-center gap-1 rounded-lg border border-gray-200 text-sm cursor-pointer bg-white hover:bg-gray-100");
export const PaginationNext = fwd("button", "h-10 px-3 inline-flex items-center gap-1 rounded-lg border border-gray-200 text-sm cursor-pointer bg-white hover:bg-gray-100");
export const PaginationEllipsis = () => e("span", { className: "h-10 w-10 inline-flex items-center justify-center text-gray-400" }, "…");

// ─── Drawer ───────────────────────────────────────────────────────

export const Drawer = Dialog;
export const DrawerContent = fwd("div", "fixed inset-x-0 bottom-0 z-50 bg-white rounded-t-2xl shadow-lg p-6");
export const DrawerHeader = DialogHeader;
export const DrawerTitle = DialogTitle;
export const DrawerDescription = DialogDescription;
export const DrawerTrigger = fwd("button", "");
export const DrawerClose = fwd("button", "");
export const DrawerFooter = fwd("div", "flex justify-end gap-2 mt-4");

// ─── NavigationMenu ───────────────────────────────────────────────

export const NavigationMenu = fwd("nav", "relative");
export const NavigationMenuList = fwd("ul", "flex items-center gap-2");
export const NavigationMenuItem = fwd("li", "");
export const NavigationMenuTrigger = fwd("button", "px-3 py-2 text-sm font-medium rounded-md hover:bg-gray-100 cursor-pointer border-none bg-transparent");
export const NavigationMenuContent = fwd("div", "absolute top-full left-0 bg-white border border-gray-200 rounded-lg shadow-lg p-4 mt-1");
export const NavigationMenuLink = fwd("a", "block px-3 py-2 text-sm hover:bg-gray-100 rounded cursor-pointer");

// ─── Menubar ──────────────────────────────────────────────────────

export const Menubar = fwd("div", "flex items-center gap-1 border border-gray-200 rounded-lg p-1");
export const MenubarMenu = ({ children }) => children;
export const MenubarTrigger = fwd("button", "px-3 py-1.5 text-sm rounded-md hover:bg-gray-100 cursor-pointer border-none bg-transparent");
export const MenubarContent = fwd("div", "absolute bg-white border border-gray-200 rounded-lg shadow-lg p-1 mt-1");
export const MenubarItem = fwd("div", "px-3 py-2 text-sm cursor-pointer hover:bg-gray-100 rounded");
export const MenubarSeparator = () => e("hr", { className: "my-1 border-gray-200" });
export const MenubarShortcut = fwd("span", "ml-auto text-xs text-gray-600");

// ─── Resizable ────────────────────────────────────────────────────

export const ResizablePanelGroup = fwd("div", "flex h-full w-full");
export const ResizablePanel = fwd("div", "flex-1 overflow-auto");
export const ResizableHandle = fwd("div", "w-1 bg-gray-200 cursor-col-resize hover:bg-gray-400");
