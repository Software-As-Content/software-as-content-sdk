# Components Documentation

This file contains documentation for the reusable UI components available in `src/components/ui/`.

---

## Design Thinking

Before coding, understand the context and commit to a BOLD aesthetic direction:

- **Purpose**: What problem does this interface solve? Who uses it?
- **Constraints**: Technical requirements (framework, performance, accessibility).
- **Differentiation**: What makes this UNFORGETTABLE? What's the one thing someone will remember?

**CRITICAL**: Choose a clear conceptual direction and execute it with precision. Bold maximalism and refined minimalism both work - the key is intentionality, not intensity.

## Design Style Guidelines

### Colors
- **Primary text**: "#171717"
- **Secondary text**: "#737373"
- **Page background**: "#00000014" (8% black opacity)
- **Card/container background**: "#FFFFFF"
- **Borders**: "#E5E7EB" or "#0000001A"
- **Icon background**: "#F3F4F6"
- **Accent color**: "#EE5C2A" (orange-red)

### Border Radius
- **Small elements** (buttons, icons): "rounded-lg" (8px)
- **Medium elements** (icon containers): "rounded-xl" (12px)
- **Large elements** (cards, info items): "rounded-2xl" (16px)

### Typography
- **Extra small**: "text-xs" (12px) - labels, timestamps
- **Small**: "text-sm" (14px) - descriptions, secondary info
- **Base**: "text-base" (16px) - body text
- **Large**: "text-lg" (18px) - card titles
- **Font weights**: "font-medium" for emphasis, "font-semibold" for headings

### Spacing
- **Inner padding**: "px-3 py-2" (12px × 8px)
- **Section gaps**: "gap-6" (24px)
- **Sidebar width**: "w-80" (320px)
- **Max content width**: "max-w-6xl" (1152px)
- **Page horizontal padding**: "px-6" (24px)

### Avatar Sizes
- **Small**: "h-8 w-8" (32px)
- **Medium**: "h-9 w-9" (36px)
- **Large**: "h-11 w-11" (44px)

### Icon Sizes
- Standard icons: "14px - 16px"
- Icon container: "h-9 w-9" (36px) with "rounded-xl" background

### Layout Patterns
- Sidebar + main content two-column structure
- Use "Card" components for content sections
- Use "Tabs" for content switching within cards
- Info items use rounded border cards with icon + label + value pattern
- Grid layout: "grid-cols-[1fr_1fr]" for equal two-column content

### Component Styling
- **Info items**: "rounded-2xl border border-[#E5E7EB] bg-white px-3 py-2"
- **Icon containers**: "rounded-xl bg-[#F3F4F6] text-[#737373]"
- **Highlight dots**: "h-1.5 w-1.5 rounded-full bg-[#EE5C2A]"
- **Progress bars**: "w-20" (80px) width

## Design Tokens & Theme Guidelines

Before using the components, follow these theme guidelines to ensure visual consistency.

### Color Palette

**Base Colors (Stone)** - Use warm gray tones:
- `stone-50` (#fafaf9) - Backgrounds, cards
- `stone-100` (#f5f5f4) - Secondary backgrounds, hover states
- `stone-200` (#e7e5e4) - Borders, dividers
- `stone-300` (#d6d3d1) - Disabled states
- `stone-400` (#a8a29e) - Placeholder text
- `stone-500` (#78716c) - Muted text
- `stone-600` (#57534e) - Secondary text
- `stone-700` (#44403c) - Primary text
- `stone-800` (#292524) - Headings
- `stone-900` (#1c1917) - High contrast text

**Accent Colors (Orange)** - Use for primary actions and highlights:
- `orange-500` (#f97316) - Primary buttons, links, focus rings
- `orange-600` (#ea580c) - Hover states for primary elements
- `orange-700` (#c2410c) - Active/pressed states

**Semantic Colors:**
- Success: `green-500` / `green-600`
- Warning: `amber-500` / `amber-600`
- Error: `red-500` / `red-600`
- Info: `blue-500` / `blue-600`

### Typography

- **Font Family**: Inter, system-ui, sans-serif
- **Headings**: `font-semibold` or `font-bold`, `text-stone-900`
- **Body Text**: `font-normal`, `text-stone-700`
- **Muted Text**: `text-stone-500`
- **Small/Caption**: `text-sm` or `text-xs`, `text-stone-500`

### Spacing & Layout

- **Border Radius**: Use smaller radius for a clean look
  - Small elements: `rounded-sm` (0.125rem)
  - Medium elements: `rounded-md` (0.375rem)
  - Large elements: `rounded-lg` (0.5rem)
- **Padding**: Consistent spacing using Tailwind's scale (p-2, p-3, p-4, etc.)
- **Gaps**: Use `gap-2`, `gap-3`, `gap-4` for flex/grid layouts

### Component Styling Patterns

**Buttons:**
```tsx
// Primary button
<button className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-md font-medium transition-colors">
  Primary Action
</button>

// Secondary button
<button className="bg-stone-100 hover:bg-stone-200 text-stone-700 px-4 py-2 rounded-md font-medium transition-colors">
  Secondary
</button>

// Outline button
<button className="border border-stone-300 hover:bg-stone-50 text-stone-700 px-4 py-2 rounded-md font-medium transition-colors">
  Outline
</button>
```

**Cards:**
```tsx
<div className="bg-white border border-stone-200 rounded-lg p-6 shadow-sm">
  {/* Card content */}
</div>
```

**Inputs:**
```tsx
<input 
  className="w-full px-3 py-2 border border-stone-300 rounded-md text-stone-700 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
  placeholder="Enter text..."
/>
```

**Focus States:**
- Use `focus:ring-2 focus:ring-orange-500` for focus indicators
- Use `focus:border-transparent` when using ring

**Hover States:**
- Buttons: Darken by one shade (e.g., `hover:bg-orange-600`)
- Cards/Items: `hover:bg-stone-50` or `hover:bg-stone-100`

**Transitions:**
- Always add `transition-colors` or `transition-all` for smooth interactions

---

## Accordion

A vertically stacked set of interactive headings that each reveal a section of content.

### Import
```tsx
import { 
  Accordion, 
  AccordionContent, 
  AccordionItem, 
  AccordionTrigger 
} from "@/components/ui/accordion"
```

### Usage
```tsx
<Accordion type="single" collapsible>
  <AccordionItem value="item-1">
    <AccordionTrigger>Is it accessible?</AccordionTrigger>
    <AccordionContent>
      Yes. It adheres to the WAI-ARIA design pattern.
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

## Alert Dialog

A modal dialog that interrupts the user with important content and expects a response.

### Import
```tsx
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
```

### Usage
```tsx
<AlertDialog>
  <AlertDialogTrigger>Open</AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
      <AlertDialogDescription>
        This action cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction>Continue</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

## Alert

Displays a callout for user attention.

### Import
```tsx
import { Terminal } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
```

### Usage
```tsx
<Alert>
  <Terminal className="h-4 w-4" />
  <AlertTitle>Heads up!</AlertTitle>
  <AlertDescription>
    You can add components to your app using the cli.
  </AlertDescription>
</Alert>
```

## Avatar

An image element with a fallback for representing the user.

### Import
```tsx
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
```

### Usage
```tsx
<Avatar>
  <AvatarImage src="https://github.com/shadcn.png" />
  <AvatarFallback>CN</AvatarFallback>
</Avatar>
```

## Badge

Displays a badge or a component that looks like a badge.

### Import
```tsx
import { Badge } from "@/components/ui/badge"
```

### Usage
```tsx
<Badge>Badge</Badge>
<Badge variant="secondary">Secondary</Badge>
<Badge variant="outline">Outline</Badge>
<Badge variant="destructive">Destructive</Badge>
```

## Breadcrumb

Displays the path to the current resource using a hierarchy of links.

### Import
```tsx
import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
```

### Usage
```tsx
<Breadcrumb>
  <BreadcrumbList>
    <BreadcrumbItem>
      <BreadcrumbLink href="/">Home</BreadcrumbLink>
    </BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem>
      <BreadcrumbLink href="/components">Components</BreadcrumbLink>
    </BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem>
      <BreadcrumbPage>Breadcrumb</BreadcrumbPage>
    </BreadcrumbItem>
  </BreadcrumbList>
</Breadcrumb>
```

## Button

Displays a button or a component that looks like a button.

### Import
```tsx
import { Button } from "@/components/ui/button"
```

### Usage
```tsx
<Button variant="default">Button</Button>
<Button variant="secondary">Secondary</Button>
<Button variant="destructive">Destructive</Button>
<Button variant="outline">Outline</Button>
<Button variant="ghost">Ghost</Button>
<Button variant="link">Link</Button>
<Button size="icon"><ChevronRight /></Button>
```

## Calendar

A date field component that allows users to enter and edit date.

### Import
```tsx
import { Calendar } from "@/components/ui/calendar"
```

### Usage
```tsx
const [date, setDate] = React.useState<Date | undefined>(new Date())

<Calendar
  mode="single"
  selected={date}
  onSelect={setDate}
  className="rounded-md border"
/>
```

## Card

Displays a card with header, content, and footer.

### Import
```tsx
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
```

### Usage
```tsx
<Card>
  <CardHeader>
    <CardTitle>Card Title</CardTitle>
    <CardDescription>Card Description</CardDescription>
  </CardHeader>
  <CardContent>
    <p>Card Content</p>
  </CardContent>
  <CardFooter>
    <p>Card Footer</p>
  </CardFooter>
</Card>
```

## Checkbox

A control that allows the user to toggle between checked and not checked.

### Import
```tsx
import { Checkbox } from "@/components/ui/checkbox"
```

### Usage
```tsx
<div className="flex items-center space-x-2">
  <Checkbox id="terms" />
  <label
    htmlFor="terms"
    className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
  >
    Accept terms and conditions
  </label>
</div>
```

## Collapsible

An interactive component which expands/collapses a panel.

### Import
```tsx
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
```

### Usage
```tsx
<Collapsible>
  <CollapsibleTrigger>Can I use this in my project?</CollapsibleTrigger>
  <CollapsibleContent>
    Yes. Free to use for personal and commercial projects. No attribution
    required.
  </CollapsibleContent>
</Collapsible>
```

## Dialog

A window overlaid on either the primary window or another dialog window, rendering the content underneath inert.

### Import
```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
```

### Usage
```tsx
<Dialog>
  <DialogTrigger>Open</DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Are you absolutely sure?</DialogTitle>
      <DialogDescription>
        This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    <DialogFooter>
      <Button type="submit">Confirm</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

## Drawer

A drawer component for React, often used on mobile devices.

### Import
```tsx
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"
```

### Usage
```tsx
<Drawer>
  <DrawerTrigger>Open</DrawerTrigger>
  <DrawerContent>
    <DrawerHeader>
      <DrawerTitle>Are you absolutely sure?</DrawerTitle>
      <DrawerDescription>This action cannot be undone.</DrawerDescription>
    </DrawerHeader>
    <DrawerFooter>
      <Button>Submit</Button>
      <DrawerClose>
        <Button variant="outline">Cancel</Button>
      </DrawerClose>
    </DrawerFooter>
  </DrawerContent>
</Drawer>
```

## Dropdown Menu

Displays a menu to the user — such as a set of actions or functions — triggered by a button.

### Import
```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
```

### Usage
```tsx
<DropdownMenu>
  <DropdownMenuTrigger>Open</DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuLabel>My Account</DropdownMenuLabel>
    <DropdownMenuSeparator />
    <DropdownMenuItem>Profile</DropdownMenuItem>
    <DropdownMenuItem>Billing</DropdownMenuItem>
    <DropdownMenuItem>Team</DropdownMenuItem>
    <DropdownMenuItem>Subscription</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

## Hover Card

For sighted users to preview content available behind a link.

### Import
```tsx
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card"
```

### Usage
```tsx
<HoverCard>
  <HoverCardTrigger>Hover</HoverCardTrigger>
  <HoverCardContent>
    The React Framework – created and maintained by @vercel.
  </HoverCardContent>
</HoverCard>
```

## Input Group

A composable input component that allows adding buttons, icons, and text addons.

### Import
```tsx
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group"
```

### Usage
```tsx
<InputGroup>
  <InputGroupAddon>
    <SearchIcon />
  </InputGroupAddon>
  <InputGroupInput placeholder="Search..." />
  <InputGroupAddon>
    <InputGroupButton>Search</InputGroupButton>
  </InputGroupAddon>
</InputGroup>
```

## Input OTP

Accessible one-time password component with copy paste support.

### Import
```tsx
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/ui/input-otp"
```

### Usage
```tsx
<InputOTP maxLength={6}>
  <InputOTPGroup>
    <InputOTPSlot index={0} />
    <InputOTPSlot index={1} />
    <InputOTPSlot index={2} />
  </InputOTPGroup>
  <InputOTPSeparator />
  <InputOTPGroup>
    <InputOTPSlot index={3} />
    <InputOTPSlot index={4} />
    <InputOTPSlot index={5} />
  </InputOTPGroup>
</InputOTP>
```

## Input

Displays a form input field or a component that looks like an input field.

### Import
```tsx
import { Input } from "@/components/ui/input"
```

### Usage
```tsx
<Input type="email" placeholder="Email" />
```

## Label

Renders an accessible label associated with controls.

### Import
```tsx
import { Label } from "@/components/ui/label"
```

### Usage
```tsx
<Label htmlFor="email">Your email address</Label>
```

## Menubar

A visually persistent menu common in desktop applications that provides quick access to a consistent set of commands.

### Import
```tsx
import {
  Menubar,
  MenubarContent,
  MenubarItem,
  MenubarMenu,
  MenubarSeparator,
  MenubarShortcut,
  MenubarTrigger,
} from "@/components/ui/menubar"
```

### Usage
```tsx
<Menubar>
  <MenubarMenu>
    <MenubarTrigger>File</MenubarTrigger>
    <MenubarContent>
      <MenubarItem>
        New Tab <MenubarShortcut>⌘T</MenubarShortcut>
      </MenubarItem>
      <MenubarItem>New Window</MenubarItem>
      <MenubarSeparator />
      <MenubarItem>Share</MenubarItem>
      <MenubarSeparator />
      <MenubarItem>Print</MenubarItem>
    </MenubarContent>
  </MenubarMenu>
</Menubar>
```

## Navigation Menu

A collection of links for navigating websites.

### Import
```tsx
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu"
```

### Usage
```tsx
<NavigationMenu>
  <NavigationMenuList>
    <NavigationMenuItem>
      <NavigationMenuTrigger>Item One</NavigationMenuTrigger>
      <NavigationMenuContent>
        <NavigationMenuLink>Link</NavigationMenuLink>
      </NavigationMenuContent>
    </NavigationMenuItem>
  </NavigationMenuList>
</NavigationMenu>
```

## Pagination

Pagination with page navigation, next and previous links.

### Import
```tsx
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
```

### Usage
```tsx
<Pagination>
  <PaginationContent>
    <PaginationItem>
      <PaginationPrevious href="#" />
    </PaginationItem>
    <PaginationItem>
      <PaginationLink href="#">1</PaginationLink>
    </PaginationItem>
    <PaginationItem>
      <PaginationEllipsis />
    </PaginationItem>
    <PaginationItem>
      <PaginationNext href="#" />
    </PaginationItem>
  </PaginationContent>
</Pagination>
```

## Popover

Displays rich content in a portal, triggered by a button.

### Import
```tsx
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
```

### Usage
```tsx
<Popover>
  <PopoverTrigger>Open</PopoverTrigger>
  <PopoverContent>Place content for the popover here.</PopoverContent>
</Popover>
```

## Progress

Displays an indicator showing the completion progress of a task, typically displayed as a progress bar.

### Import
```tsx
import { Progress } from "@/components/ui/progress"
```

### Usage
```tsx
<Progress value={33} />
```

## Radio Group

A set of checkable buttons—known as radio buttons—where no more than one of the buttons can be checked at a time.

### Import
```tsx
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
```

### Usage
```tsx
<RadioGroup defaultValue="option-one">
  <div className="flex items-center space-x-2">
    <RadioGroupItem value="option-one" id="option-one" />
    <Label htmlFor="option-one">Option One</Label>
  </div>
  <div className="flex items-center space-x-2">
    <RadioGroupItem value="option-two" id="option-two" />
    <Label htmlFor="option-two">Option Two</Label>
  </div>
</RadioGroup>
```

## Resizable

Accessible resizable panel groups and layouts with keyboard support.

### Import
```tsx
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
```

### Usage
```tsx
<ResizablePanelGroup direction="horizontal">
  <ResizablePanel>One</ResizablePanel>
  <ResizableHandle />
  <ResizablePanel>Two</ResizablePanel>
</ResizablePanelGroup>
```

## Scroll Area

Augments native scroll functionality for custom, cross-browser styling.

### Import
```tsx
import { ScrollArea } from "@/components/ui/scroll-area"
```

### Usage
```tsx
<ScrollArea className="h-[200px] w-[350px] rounded-md border p-4">
  Jokester began sneaking into the castle in the middle of the night and leaving
  jokes all over the place: under the king's pillow, in his soup, even in the
  royal toilet. The king was furious, but he couldn't seem to stop Jokester. And
  then, one day, the people of the kingdom discovered that the jokes were
  actually funny, and they started laughing. And then the king started laughing,
  and then everyone was laughing.
</ScrollArea>
```

## Select

Displays a list of options for the user to pick from—triggered by a button.

### Import
```tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
```

### Usage
```tsx
<Select>
  <SelectTrigger className="w-[180px]">
    <SelectValue placeholder="Theme" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="light">Light</SelectItem>
    <SelectItem value="dark">Dark</SelectItem>
    <SelectItem value="system">System</SelectItem>
  </SelectContent>
</Select>
```

## Separator

Visually or semantically separates content.

### Import
```tsx
import { Separator } from "@/components/ui/separator"
```

### Usage
```tsx
<Separator />
```

## Sheet

Extends the Dialog component to display content that complements the main screen.

### Import
```tsx
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
```

### Usage
```tsx
<Sheet>
  <SheetTrigger>Open</SheetTrigger>
  <SheetContent>
    <SheetHeader>
      <SheetTitle>Are you absolutely sure?</SheetTitle>
      <SheetDescription>
        This action cannot be undone.
      </SheetDescription>
    </SheetHeader>
  </SheetContent>
</Sheet>
```

## Sidebar

A composable, themeable, and accessible sidebar component.

### Import
```tsx
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
```

### Usage
```tsx
<SidebarProvider>
  <AppSidebar />
  <main>
    <SidebarTrigger />
    {children}
  </main>
</SidebarProvider>
```

## Skeleton

Use to show a placeholder while content is loading.

### Import
```tsx
import { Skeleton } from "@/components/ui/skeleton"
```

### Usage
```tsx
<Skeleton className="w-[100px] h-[20px] rounded-full" />
```

## Slider

An input where the user selects a value from within a given range.

### Import
```tsx
import { Slider } from "@/components/ui/slider"
```

### Usage
```tsx
<Slider defaultValue={[33]} max={100} step={1} />
```

## Sonner

An opinionated toast component for React.

### Import
```tsx
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
```

### Usage
```tsx
// Add <Toaster /> to your app root
<Button onClick={() => toast("Event has been created")}>
  Show Toast
</Button>
```

## Source

A composable component for displaying a single source link with a hover card preview.

### Import
```tsx
import {
  Source,
  SourceContent,
  SourceTrigger,
} from "@/components/ui/source"
```

### Usage
```tsx
<Source href="https://example.com/article">
  <SourceTrigger label="Example" showFavicon />
  <SourceContent
    title="Example Article"
    description="This is an example article description that appears in the hover card."
  />
</Source>
```

## Sources

A composable component for displaying multiple sources with a hover card that shows all sources in a list.

### Import
```tsx
import {
  Sources,
  SourcesContent,
  SourcesTrigger,
  type SourcesItem,
} from "@/components/ui/sources"
```

### Usage
```tsx
const sources: SourcesItem[] = [
  {
    href: "https://example.com/article1",
    title: "First Article",
    description: "Description of the first article",
    label: "Article 1",
  },
  {
    href: "https://example.com/article2",
    title: "Second Article",
    description: "Description of the second article",
  },
];

<Sources sources={sources}>
  <SourcesTrigger label="2 sources" showFavicon maxVisible={3} />
  <SourcesContent
    title="Sources"
    description="References for this content"
    showFavicon
  />
</Sources>
```

## Spinner

A loading spinner component.

### Import
```tsx
import { Spinner } from "@/components/ui/spinner"
```

### Usage
```tsx
<Spinner />
```

## Switch

A control that allows the user to toggle between checked and not checked.

### Import
```tsx
import { Switch } from "@/components/ui/switch"
```

### Usage
```tsx
<Switch />
```

## Table

A responsive table component.

### Import
```tsx
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
```

### Usage
```tsx
<Table>
  <TableCaption>A list of your recent invoices.</TableCaption>
  <TableHeader>
    <TableRow>
      <TableHead className="w-[100px]">Invoice</TableHead>
      <TableHead>Status</TableHead>
      <TableHead>Method</TableHead>
      <TableHead className="text-right">Amount</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow>
      <TableCell className="font-medium">INV001</TableCell>
      <TableCell>Paid</TableCell>
      <TableCell>Credit Card</TableCell>
      <TableCell className="text-right">$250.00</TableCell>
    </TableRow>
  </TableBody>
</Table>
```

## Tabs

A set of layered sections of content—known as tab panels—that are displayed one at a time.

### Import
```tsx
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
```

### Usage
```tsx
<Tabs defaultValue="account" className="w-[400px]">
  <TabsList>
    <TabsTrigger value="account">Account</TabsTrigger>
    <TabsTrigger value="password">Password</TabsTrigger>
  </TabsList>
  <TabsContent value="account">Make changes to your account here.</TabsContent>
  <TabsContent value="password">Change your password here.</TabsContent>
</Tabs>
```

## Textarea

Displays a form textarea or a component that looks like a textarea.

### Import
```tsx
import { Textarea } from "@/components/ui/textarea"
```

### Usage
```tsx
<Textarea />
```

## Toggle Group

A set of two-state buttons that can be toggled on or off.


### Import
```tsx
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
```

### Usage
```tsx
<ToggleGroup type="single">
  <ToggleGroupItem value="a">A</ToggleGroupItem>
  <ToggleGroupItem value="b">B</ToggleGroupItem>
  <ToggleGroupItem value="c">C</ToggleGroupItem>
</ToggleGroup>
```

## Toggle

A two-state button that can be either on or off.

### Import
```tsx
import { Toggle } from "@/components/ui/toggle"
```

### Usage
```tsx
<Toggle>Toggle</Toggle>
```

## Tooltip

A popup that displays information related to an element when the element receives keyboard focus or the mouse hovers over it.

### Import
```tsx
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
```

### Usage
```tsx
<TooltipProvider>
  <Tooltip>
    <TooltipTrigger>Hover</TooltipTrigger>
    <TooltipContent>
      <p>Add to library</p>
    </TooltipContent>
  </Tooltip>
</TooltipProvider>
```