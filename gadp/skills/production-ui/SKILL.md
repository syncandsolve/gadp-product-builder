---
name: production-ui
description: Structural and functional requirements for production-grade UI contracts in GADP. Read alongside frontend-design/SKILL.md for every UI contract. Covers the four mandatory states, design token compliance, accessibility, responsive implementation, and state wiring to API calls. Does not cover aesthetic direction — that is frontend-design's domain.
---

Read this skill fully before writing any UI component code. It covers **structural and functional requirements** — what must be true for a UI contract to pass, independent of how it looks. `frontend-design/SKILL.md` covers aesthetic direction. Both are required. Neither substitutes for the other.

---

## The four mandatory states

Every UI contract implements exactly four states. Not three. Not "the main one plus error." All four. A UI contract is not passing until all four states are implemented and tested.

The four states are not optional features — they are the minimum viable implementation. A screen that shows only the populated state is incomplete software, not a complete feature with edge cases deferred.

### Loading state

The user must see something meaningful while data is fetching. Requirements:

- **Appears before data arrives, not after.** Set loading state on component mount, before the fetch is issued. Do not flash empty content while the first request is in flight.
- **Matches the populated state's layout.** A skeleton loader is correct: same number of rows, same column widths, same card dimensions as the populated view. A generic centered spinner is only acceptable for very fast operations (sub-200ms expected). Never a blank container.
- **Does not flash for instant loads.** If data resolves in under 100ms (e.g. from cache), the loading state should not flash. Use a minimum display duration of 150ms or suppress it with a short delay before showing loading UI.

Implementation pattern:
```typescript
const [status, setStatus] = useState<'loading' | 'empty' | 'populated' | 'error'>('loading');

useEffect(() => {
  setStatus('loading');
  fetchData()
    .then(data => setStatus(data.length === 0 ? 'empty' : 'populated'))
    .catch(() => setStatus('error'));
}, []);
```

**Test assertion required:** loading state renders on mount before the fetch resolves. Mock the fetch with a delayed response and assert the skeleton/spinner is present before the delay completes.

### Empty state

When the data set is legitimately empty — new account, no results, nothing created yet. Requirements:

- **Icon** — relevant to the context, not a generic placeholder. A task list uses a checkbox icon. A file manager uses a folder icon. A search result uses a magnifying glass.
- **Headline** — explains the situation in human terms. "No tasks yet" not "Empty". "Nothing here" is not acceptable.
- **Primary call-to-action** — gives the user somewhere to go. "Create your first task", "Upload a file", "Run your first search". The CTA maps to the primary action on this screen.
- **Never:** raw "No data" text, an empty box, silence, or an error message that implies something went wrong.

**Test assertion required:** empty state renders with icon, headline, and CTA when API returns an empty array. The CTA navigates or opens the correct action.

### Populated state

The primary operating state. Requirements:

- Built to the screen's `single_job` from `design-language.yaml`. Not a generic CRUD table unless the single job is genuinely "manage a list".
- Uses real data from the API or a realistic fixture — not placeholder text, not `Lorem ipsum`, not `Item 1 / Item 2`.
- Pagination, infinite scroll, or "load more" implemented if the data set can exceed one screen.
- All interactive elements (buttons, links, dropdowns) are functional — no dead UI.

**Test assertion required:** populated state renders with fixture data matching the API contract's response shape. At minimum one interactive element is tested for its intended action.

### Error state

When the API call fails or returns unexpected data. Requirements:

- **Human-readable message** — written for the user, not the developer. "Something went wrong — please try again" is acceptable. "Error 503" is not. "TypeError: Cannot read properties of undefined" is never acceptable in production UI.
- **Recovery path** — at minimum a retry button. If retry is not appropriate: a "Go back" link, a "Contact support" link, or a specific next step.
- **Never:** a raw error string, an HTTP status code displayed to the user, an unhandled exception that leaves the screen blank or frozen, or an alert() call.

**Test assertion required:** error state renders with recovery action when the API call rejects. The recovery action is testable (retry triggers a new fetch, back link navigates correctly).

---

## State wiring — implementation guide

### The state machine pattern

Use a single `status` discriminant, not multiple boolean flags. Boolean flags (`isLoading`, `hasError`, `isEmpty`) produce impossible states (`isLoading: true, hasError: true`). A discriminant enum makes each state exclusive and exhaustive.

```typescript
type ScreenStatus = 'loading' | 'empty' | 'populated' | 'error';

// Render by switching on status — not by combining boolean conditions
switch (status) {
  case 'loading': return <SkeletonLoader />;
  case 'empty': return <EmptyState onAction={handlePrimary} />;
  case 'populated': return <DataView data={data} />;
  case 'error': return <ErrorState onRetry={handleRetry} />;
}
```

### Loading state must precede the fetch

Set `'loading'` before issuing the fetch call, not after. The following is wrong:

```typescript
// WRONG — empty state flashes while fetch is in flight
const data = await fetchData();
setStatus(data.length === 0 ? 'empty' : 'populated');
```

The following is correct:

```typescript
// CORRECT — loading state appears immediately
setStatus('loading');
const data = await fetchData();
setStatus(data.length === 0 ? 'empty' : 'populated');
```

### Transition rules

- `loading` → `empty` | `populated` | `error` (never directly to `loading` again without a user action)
- `error` → `loading` (when the user retries) → `empty` | `populated` | `error`
- `populated` → `loading` (when the user refreshes or changes filter) → `empty` | `populated` | `error`
- Never `empty` → `error` or `error` → `empty` directly — always go through `loading`

### Skeleton loader implementation

The skeleton must match the populated layout — same row count, same column proportions. Do not use a generic full-page spinner when the populated state is a list or table.

```typescript
function SkeletonRow() {
  return (
    <div className="flex gap-3 items-center p-4 border-b border-border animate-pulse">
      <div className="h-8 w-8 rounded-full bg-muted" />
      <div className="flex-1 space-y-1">
        <div className="h-3 w-48 rounded bg-muted" />
        <div className="h-3 w-32 rounded bg-muted" />
      </div>
    </div>
  );
}
```

`bg-muted` is a Tailwind theme token — not `bg-gray-200`. See Design Token Compliance below.

---

## Design token compliance

### The rule

Zero hardcoded values in any UI component. Every color, spacing value, border radius, font size, and shadow must reference a Tailwind theme token or CSS variable from the design language. This is enforced by INV-DQ-001 at every audit.

### Pre-flight checklist — run after every UI file you write

Run these before marking a contract in_review. Do not wait for the Auditor.

```bash
# Hardcoded hex values (catches #fff, #000, #1a2b3c, etc.)
grep -rn '#[0-9a-fA-F]\{3,6\}' src/ --include="*.tsx" --include="*.ts" --include="*.css"

# Inline style with color (catches style={{ color: '...' }})
grep -rn 'style={{' src/ --include="*.tsx" | grep -i 'color\|background\|border'

# RGB/HSL color functions in component files
grep -rn 'rgb(\|rgba(\|hsl(\|hsla(' src/ --include="*.tsx" --include="*.ts"

# Hardcoded pixel values in className that should be tokens
grep -rn 'p-\[' src/ --include="*.tsx"   # arbitrary Tailwind values — use scale instead
```

If any of these produce matches, fix them before proceeding. The Auditor will catch them, but fixing them proactively costs one minute; fixing them after an audit violation costs a contract regression.

### Correct and incorrect patterns

| Wrong | Correct |
|---|---|
| `style={{ color: '#3b82f6' }}` | `className="text-primary"` |
| `style={{ backgroundColor: 'white' }}` | `className="bg-background"` |
| `style={{ padding: '12px' }}` | `className="p-3"` |
| `className="text-gray-500"` | `className="text-muted-foreground"` |
| `className="border-gray-200"` | `className="border-border"` |
| `className="bg-gray-100"` | `className="bg-muted"` |

The correct token names come from the project's `design-language.yaml` → `design_tokens` block. Read it before writing any component. The tokens are the contract — not the Tailwind defaults.

### CSS variables

If the design language specifies custom tokens beyond standard Tailwind semantics, they are expressed as CSS variables:

```css
/* globals.css */
:root {
  --color-brand: 221 83% 53%;   /* hsl format for Tailwind compatibility */
}
```

```typescript
// Use as Tailwind arbitrary value only if the token is not in the standard semantic set
className="text-[hsl(var(--color-brand))]"
```

Prefer the semantic token over the CSS variable reference wherever the semantic token expresses the intent.

---

## Accessibility

Every UI contract meets WCAG AA. These are not aspirational — they are testable requirements enforced by INV-A-* invariants and the accessibility test suite wired at project setup.

### Accessible names — every interactive element

Every button, link, input, and interactive element must have an accessible name. In priority order:

1. **Visible text** — the button label is the accessible name. Preferred.
2. **`aria-label`** — use when visible text is absent or insufficient (icon buttons, close buttons).
3. **`aria-labelledby`** — use when the label is a visible element elsewhere in the DOM.

```typescript
// Icon-only button — requires aria-label
<button aria-label="Close dialog" onClick={onClose}>
  <XIcon className="h-4 w-4" />
</button>

// Button with visible text — no aria-label needed
<button onClick={onSave}>Save changes</button>

// Input — always paired with a label
<label htmlFor="email">Email address</label>
<input id="email" type="email" />
```

Never: `<button onClick={fn}><XIcon /></button>` without an accessible name. The Playwright accessibility test will catch this.

### Focus management

- **Modal / dialog:** when opened, move focus to the first interactive element inside. When closed, return focus to the trigger element.
- **Drawer / sheet:** same as modal.
- **Toast / notification:** do not move focus — toasts are non-modal. Use `role="status"` and `aria-live="polite"`.
- **Dynamic content insertion:** if content is inserted into the DOM in response to a user action, ensure the new content is reachable by keyboard without requiring the user to navigate backward.

```typescript
// Modal focus management
useEffect(() => {
  if (isOpen) {
    firstFocusableRef.current?.focus();
  } else {
    triggerRef.current?.focus();
  }
}, [isOpen]);
```

### Keyboard navigation

- All interactive elements reachable and operable by keyboard alone.
- Tab order follows visual reading order.
- Custom interactive components (dropdowns, date pickers, comboboxes) implement the correct ARIA pattern from the ARIA Authoring Practices Guide.
- `Escape` closes modals, drawers, dropdowns, and popovers.
- No keyboard traps — the user can always tab out of any component.

### Colour contrast

All text meets WCAG AA contrast ratios:
- Normal text (< 18px regular or < 14px bold): minimum 4.5:1
- Large text (≥ 18px regular or ≥ 14px bold): minimum 3:1
- UI component boundaries and focus indicators: minimum 3:1

Tailwind's semantic token system (via the design language) is pre-configured for AA compliance. Violations occur when arbitrary hex values are introduced — which is why the design token rule exists.

---

## Responsive implementation

### Breakpoints

Use only the breakpoints defined in the design language. Do not add breakpoints that are not in `design-language.yaml → responsive_strategy`. The standard GADP breakpoints are Tailwind's defaults unless overridden:

| Prefix | Minimum width |
|---|---|
| `sm:` | 640px |
| `md:` | 768px |
| `lg:` | 1024px |
| `xl:` | 1280px |

Mobile-first: write the base style for the smallest viewport, then add breakpoint prefixes for larger viewports.

### All four states at all breakpoints

Each of the four mandatory states must be tested at mobile (375px) and desktop (1280px) widths minimum. A loading skeleton that works at desktop and collapses to a broken layout on mobile is not passing.

### Images

Every `<img>` requires explicit `width` and `height` attributes (or equivalent via `aspect-ratio` CSS) to prevent Cumulative Layout Shift. This is enforced by INV-P-002.

```typescript
// Correct — explicit dimensions
<img src={src} alt={alt} width={400} height={300} className="w-full h-auto" />

// Correct — aspect ratio container
<div className="aspect-video">
  <img src={src} alt={alt} className="w-full h-full object-cover" />
</div>

// Wrong — no dimensions, causes CLS
<img src={src} alt={alt} />
```

### Touch targets

All interactive elements have a minimum touch target size of 44×44px on mobile. Small elements (icons, close buttons) use padding to expand the touch area without changing the visual size:

```typescript
<button
  aria-label="Remove item"
  className="p-3 -m-3"  // visually same size, touch target expanded
>
  <XIcon className="h-4 w-4" />
</button>
```

---

## abandonment_recovery and error_recovery

If the screen's entry in `design-language.yaml` defines `abandonment_recovery` or `error_recovery`, implement those behaviours exactly. They are part of the contract.

**`abandonment_recovery`** fires when the defined signal is detected:
- Implement the signal detection first (form dirty state, timer, scroll position, etc.)
- Implement the recovery UI exactly as specified (modal, inline banner, toast, etc.)
- Do not implement a generic "are you sure?" dialog if the design specifies a specific pattern

**`error_recovery`** fires when the screen enters error state:
- The recovery path described in `error_recovery` is the error state's CTA
- Do not substitute a generic "Try again" button if a specific recovery path is defined

Test assertions are required for both. These are contract then-clauses, not UX enhancements.

---

## What production-ui does not cover

- **Aesthetic direction** — which fonts, which color palette, what visual character. That is `frontend-design/SKILL.md`.
- **Component library selection** — that decision is in `decisions.yaml`.
- **Animation and motion design** — `frontend-design/SKILL.md`.
- **Which screen to build** — `design-language.yaml` and the contract.

If you are unsure whether something is a structural requirement (production-ui) or an aesthetic choice (frontend-design), ask: would a failing test catch it? If yes, it is a structural requirement. If it only affects appearance with no testable assertion, it is aesthetic.
