# Components Documentation

This file contains documentation for the reusable UI components available in `src/components/ui/`.

---

## Design Thinking

Before coding, understand the context and commit to a BOLD aesthetic direction:

- **Purpose**: What problem does this interface solve? Who uses it?
- **Constraints**: Technical requirements (framework, performance, accessibility).
- **Differentiation**: What makes this UNFORGETTABLE? What's the one thing someone will remember?

**CRITICAL**: Choose a clear conceptual direction and execute it with precision. Bold maximalism and refined minimalism both work — the key is intentionality, not intensity.

## Design Tokens & Theme Guidelines

### Color Palette

**Main page background: ALWAYS pure white (`bg-white` / `#ffffff`).** Never use dark backgrounds (gray-800, slate-900, zinc-900, black, etc.) for the page or large sections. Never use `stone-50` or any tinted color for the top-level page / app container background — the app must read as a clean white surface.

**Base (Stone)** — warm gray tones for text and subtle contrast:
`stone-100` hover · `stone-200` border · `stone-400` placeholder · `stone-500` muted · `stone-700` body · `stone-900` heading.

**Accent (Orange)** — primary actions, links, focus rings:
`orange-500` primary · `orange-600` hover · `orange-700` active.

**Semantic**: `green-500/600` success · `amber-500/600` warning · `red-500/600` error · `blue-500/600` info.

**Contrast Rules**:
- Every text/background pair should have clear visual contrast. On light backgrounds use `text-stone-700`+ for body, `text-stone-900` for headings. On dark backgrounds use `text-white` or `text-stone-100`.
- Avoid mid-on-mid combinations (e.g. `text-stone-400` on `bg-stone-200`, or `text-gray-500` on `bg-gray-700`).
- These stone/orange defaults apply when no specific style is requested. If the user asks for a dark theme, neon style, etc., adapt colors accordingly while maintaining readable contrast.

### Typography
Font: Inter, system-ui, sans-serif. Headings `font-semibold text-stone-900`. Body `text-stone-700`. Muted `text-stone-500`. Captions `text-xs text-stone-500`.

### Spacing & Radius
Radius: `rounded-sm` (small) · `rounded-md` (default) · `rounded-lg` (large). Padding & gaps use Tailwind's standard scale (`p-2`, `p-3`, `p-4`, `gap-2`, `gap-3`, `gap-4`).

### Component Usage Rule

**ALWAYS use the components documented below** (`Button`, `Card`, `Input`, `Select`, etc.) from `@/components/ui/*`. Do NOT write raw `<button>`, `<input>`, `<select>` with inline Tailwind classes — the design system components already encapsulate the correct styling, variants, and interaction states. Raw HTML is only acceptable for layout primitives (`<div>`, `<section>`, `<nav>`, etc.).

**Interaction states**: focus with `focus:ring-2 focus:ring-orange-500 focus:border-transparent`. Hover darkens by one shade (`hover:bg-orange-600`) for buttons, lightens (`hover:bg-stone-50`) for cards. Always add `transition-colors`.

---

## Accordion
```tsx
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

<Accordion type="single" collapsible>
  <AccordionItem value="item-1">
    <AccordionTrigger>Question</AccordionTrigger>
    <AccordionContent>Answer</AccordionContent>
  </AccordionItem>
</Accordion>
```

## Alert Dialog
```tsx
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog"

<AlertDialog>
  <AlertDialogTrigger>Open</AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Are you sure?</AlertDialogTitle>
      <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction>Continue</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

## Alert
```tsx
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

// variants: default | destructive
<Alert>
  <AlertTitle>Heads up!</AlertTitle>
  <AlertDescription>Info message.</AlertDescription>
</Alert>
```

## Avatar
```tsx
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

<Avatar>
  <AvatarImage src="https://..." />
  <AvatarFallback>CN</AvatarFallback>
</Avatar>
```

## Badge
```tsx
import { Badge } from "@/components/ui/badge"

// variants: default | secondary | destructive | outline
<Badge variant="secondary">New</Badge>
```

## Breadcrumb
```tsx
import { Breadcrumb, BreadcrumbEllipsis, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"

<Breadcrumb>
  <BreadcrumbList>
    <BreadcrumbItem><BreadcrumbLink href="/">Home</BreadcrumbLink></BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem><BreadcrumbPage>Current</BreadcrumbPage></BreadcrumbItem>
  </BreadcrumbList>
</Breadcrumb>
```

## Button
```tsx
import { Button } from "@/components/ui/button"

// variants: default | secondary | destructive | outline | ghost | link
// sizes:    default | sm | lg | icon
<Button variant="outline" size="sm">Click</Button>
```

## Card
```tsx
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content</CardContent>
  <CardFooter>Footer</CardFooter>
</Card>
```

## Checkbox
```tsx
import { Checkbox } from "@/components/ui/checkbox"

<div className="flex items-center space-x-2">
  <Checkbox id="terms" />
  <Label htmlFor="terms">Accept terms</Label>
</div>
```

## Collapsible
```tsx
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

<Collapsible>
  <CollapsibleTrigger>Toggle</CollapsibleTrigger>
  <CollapsibleContent>Hidden content</CollapsibleContent>
</Collapsible>
```

## Dialog
```tsx
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"

<Dialog>
  <DialogTrigger>Open</DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Title</DialogTitle>
      <DialogDescription>Description</DialogDescription>
    </DialogHeader>
    <DialogFooter><Button type="submit">Confirm</Button></DialogFooter>
  </DialogContent>
</Dialog>
```

## Drawer
```tsx
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer"

<Drawer>
  <DrawerTrigger>Open</DrawerTrigger>
  <DrawerContent>
    <DrawerHeader>
      <DrawerTitle>Title</DrawerTitle>
      <DrawerDescription>Description</DrawerDescription>
    </DrawerHeader>
    <DrawerFooter>
      <Button>Submit</Button>
      <DrawerClose><Button variant="outline">Cancel</Button></DrawerClose>
    </DrawerFooter>
  </DrawerContent>
</Drawer>
```

## Dropdown Menu
```tsx
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

<DropdownMenu>
  <DropdownMenuTrigger>Open</DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuLabel>Account</DropdownMenuLabel>
    <DropdownMenuSeparator />
    <DropdownMenuItem>Profile</DropdownMenuItem>
    <DropdownMenuItem>Billing</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

## Hover Card
```tsx
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card"

<HoverCard>
  <HoverCardTrigger>Hover</HoverCardTrigger>
  <HoverCardContent>Preview content</HoverCardContent>
</HoverCard>
```

## Input
```tsx
import { Input } from "@/components/ui/input"

<Input type="email" placeholder="Email" />
```

## Label
```tsx
import { Label } from "@/components/ui/label"

<Label htmlFor="email">Your email</Label>
```

## Menubar
```tsx
import { Menubar, MenubarContent, MenubarItem, MenubarMenu, MenubarSeparator, MenubarShortcut, MenubarTrigger } from "@/components/ui/menubar"

<Menubar>
  <MenubarMenu>
    <MenubarTrigger>File</MenubarTrigger>
    <MenubarContent>
      <MenubarItem>New <MenubarShortcut>⌘N</MenubarShortcut></MenubarItem>
      <MenubarSeparator />
      <MenubarItem>Open</MenubarItem>
    </MenubarContent>
  </MenubarMenu>
</Menubar>
```

## Navigation Menu
```tsx
import { NavigationMenu, NavigationMenuContent, NavigationMenuItem, NavigationMenuLink, NavigationMenuList, NavigationMenuTrigger } from "@/components/ui/navigation-menu"

<NavigationMenu>
  <NavigationMenuList>
    <NavigationMenuItem>
      <NavigationMenuTrigger>Item</NavigationMenuTrigger>
      <NavigationMenuContent><NavigationMenuLink>Link</NavigationMenuLink></NavigationMenuContent>
    </NavigationMenuItem>
  </NavigationMenuList>
</NavigationMenu>
```

## Pagination
```tsx
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination"

<Pagination>
  <PaginationContent>
    <PaginationItem><PaginationPrevious href="#" /></PaginationItem>
    <PaginationItem><PaginationLink href="#">1</PaginationLink></PaginationItem>
    <PaginationItem><PaginationEllipsis /></PaginationItem>
    <PaginationItem><PaginationNext href="#" /></PaginationItem>
  </PaginationContent>
</Pagination>
```

## Popover
```tsx
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

<Popover>
  <PopoverTrigger>Open</PopoverTrigger>
  <PopoverContent>Content</PopoverContent>
</Popover>
```

## Progress
```tsx
import { Progress } from "@/components/ui/progress"

<Progress value={33} />
```

## Radio Group
```tsx
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"

<RadioGroup defaultValue="a">
  <div className="flex items-center space-x-2">
    <RadioGroupItem value="a" id="a" />
    <Label htmlFor="a">Option A</Label>
  </div>
  <div className="flex items-center space-x-2">
    <RadioGroupItem value="b" id="b" />
    <Label htmlFor="b">Option B</Label>
  </div>
</RadioGroup>
```

## Resizable
```tsx
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"

<ResizablePanelGroup direction="horizontal">
  <ResizablePanel>One</ResizablePanel>
  <ResizableHandle />
  <ResizablePanel>Two</ResizablePanel>
</ResizablePanelGroup>
```

## Scroll Area
```tsx
import { ScrollArea } from "@/components/ui/scroll-area"

<ScrollArea className="h-[200px] w-[350px] rounded-md border p-4">Long content...</ScrollArea>
```

## Select
```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

<Select>
  <SelectTrigger className="w-[180px]"><SelectValue placeholder="Theme" /></SelectTrigger>
  <SelectContent>
    <SelectItem value="light">Light</SelectItem>
    <SelectItem value="dark">Dark</SelectItem>
  </SelectContent>
</Select>
```

## Separator
```tsx
import { Separator } from "@/components/ui/separator"

<Separator />
```

## Sheet
```tsx
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

<Sheet>
  <SheetTrigger>Open</SheetTrigger>
  <SheetContent>
    <SheetHeader>
      <SheetTitle>Title</SheetTitle>
      <SheetDescription>Description</SheetDescription>
    </SheetHeader>
  </SheetContent>
</Sheet>
```

## Skeleton
```tsx
import { Skeleton } from "@/components/ui/skeleton"

<Skeleton className="w-[100px] h-[20px] rounded-full" />
```

## Slider
```tsx
import { Slider } from "@/components/ui/slider"

<Slider defaultValue={[33]} max={100} step={1} />
```

## Spinner
```tsx
import { Spinner } from "@/components/ui/spinner"

<Spinner />
```

## Switch
```tsx
import { Switch } from "@/components/ui/switch"

<Switch />
```

## Table
```tsx
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

<Table>
  <TableCaption>Invoices</TableCaption>
  <TableHeader>
    <TableRow>
      <TableHead>Invoice</TableHead>
      <TableHead>Amount</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow>
      <TableCell>INV001</TableCell>
      <TableCell>$250.00</TableCell>
    </TableRow>
  </TableBody>
</Table>
```

## Tabs

**⚠️ Must be fully wired — see TAB IMPLEMENTATION in the base prompt.** Do not fake a tab bar with plain buttons. Every `TabsTrigger` needs a matching `TabsContent`, and all switchable content lives inside `TabsContent` blocks. Use React state (`value` + `onValueChange`), not `defaultValue` alone.

```tsx
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const [activeTab, setActiveTab] = React.useState("account");

<Tabs value={activeTab} onValueChange={setActiveTab}>
  <TabsList>
    <TabsTrigger value="account">Account</TabsTrigger>
    <TabsTrigger value="password">Password</TabsTrigger>
  </TabsList>
  <TabsContent value="account">Account content</TabsContent>
  <TabsContent value="password">Password content</TabsContent>
</Tabs>
```

## Textarea
```tsx
import { Textarea } from "@/components/ui/textarea"

<Textarea placeholder="Type here..." />
```

## Toggle Group
```tsx
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

<ToggleGroup type="single">
  <ToggleGroupItem value="a">A</ToggleGroupItem>
  <ToggleGroupItem value="b">B</ToggleGroupItem>
</ToggleGroup>
```

## Toggle
```tsx
import { Toggle } from "@/components/ui/toggle"

<Toggle>Toggle</Toggle>
```

## Tooltip
```tsx
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

<TooltipProvider>
  <Tooltip>
    <TooltipTrigger>Hover</TooltipTrigger>
    <TooltipContent>Info</TooltipContent>
  </Tooltip>
</TooltipProvider>
```