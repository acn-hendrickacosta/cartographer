# React Accessibility

## Semantic HTML First

- Use the element that matches the intent. `<button>` for actions, `<a>` for navigation, `<nav>`, `<main>`, `<section>`, `<article>` for regions. Add `role` attributes only when native semantics are unavailable.
- A `<div onClick>` has no keyboard support, no accessible name, and no announced role. Replace with a `<button>`.

```tsx
// Wrong: no keyboard, no announced role
<div onClick={handleClick}>Submit</div>

// Correct: focusable, activates on Enter/Space, announced as "button"
<button type="button" onClick={handleClick}>Submit</button>
```

- Do not skip heading levels. `<h1>` → `<h2>` → `<h3>` in order. Jumping from `<h1>` to `<h4>` breaks document outline for screen reader users.

## Form Labels

- Every `<input>`, `<select>`, and `<textarea>` must have a connected `<label>` via `htmlFor`/`id`. A placeholder is not a label — it disappears on input and is not read by all screen readers.

```tsx
// Wrong: label has no connection
<label>Email</label>
<input type="email" />

// Correct: htmlFor matches id
<label htmlFor="email">Email</label>
<input id="email" type="email" />
```

## Error Messages

- Link error messages to their input with `aria-describedby`. Mark inputs with `aria-invalid` when they are in an error state. Wrap error text in `role="alert"` so it is announced immediately.

```tsx
<input
  id="email"
  type="email"
  aria-describedby={errors.email ? 'email-error' : undefined}
  aria-invalid={!!errors.email}
/>
{errors.email && (
  <span id="email-error" role="alert">{errors.email}</span>
)}
```

## Required Fields

- Use the `required` attribute and `aria-required="true"` together. Mark the visual asterisk with `aria-hidden="true"` so it is not read as "star".

```tsx
<label htmlFor="email">Email <span aria-hidden="true">*</span></label>
<input id="email" type="email" required aria-required="true" />
```

## ARIA Attributes

- Use `aria-label` when no visible label text exists (icon-only buttons). Use `aria-labelledby` when a visible label element exists — reference its `id`.
- Use `aria-describedby` for supplementary description beyond the label.
- Use `aria-expanded` + `aria-controls` on disclosure triggers (accordions, dropdowns, menus).
- Use `aria-live="polite"` for non-urgent dynamic updates (status messages). Use `aria-live="assertive"` only for urgent errors that must interrupt the user.
- Wrong ARIA is worse than no ARIA. Adding `aria-label` to a `<div>` without a `role` does nothing useful.

```tsx
// Icon button: aria-label provides the name
<button aria-label="Close modal"><XIcon /></button>

// Dynamic status
<div role="status" aria-live="polite" aria-atomic="true">{statusMessage}</div>

// Accordion
<button aria-expanded={isOpen} aria-controls={contentId} onClick={toggle}>
  {title}
</button>
<div id={contentId} hidden={!isOpen}>{children}</div>
```

## Keyboard Navigation

- Every interactive element must be reachable and operable by keyboard alone. Custom widgets must implement the ARIA keyboard pattern for their role.
- `tabIndex={0}` makes an element focusable in natural tab order. `tabIndex={-1}` makes it programmatically focusable but removes it from the tab sequence. Positive `tabIndex` values create unpredictable tab order — never use them.
- Custom dropdowns and comboboxes must handle `ArrowDown`/`ArrowUp` for list navigation, `Enter`/`Space` to select, and `Escape` to close.

## Focus Management

- Move focus into a modal when it opens. Restore focus to the trigger element when it closes.
- For full focus trapping (Tab/Shift+Tab cycling within the modal), use a library like `focus-trap-react` — the edge cases with dynamic content and nested portals are non-trivial to implement correctly.

```tsx
useEffect(() => {
  if (isOpen) {
    previousFocusRef.current = document.activeElement as HTMLElement
    modalRef.current?.focus()
  } else {
    previousFocusRef.current?.focus()
  }
}, [isOpen])
```

## Images and Icons

- Decorative images: `alt=""` and `aria-hidden="true"`. Content images: `alt` describing what the image conveys.
- Icon-only buttons: `aria-label` on the button, `aria-hidden="true"` on the icon element.

```tsx
<img src="/decoration.png" alt="" aria-hidden="true" />
<img src="/chart.png" alt="Monthly revenue increased 23% from January to March" />
<button aria-label="Delete item"><TrashIcon aria-hidden="true" /></button>
```

## Reduced Motion

- Respect `prefers-reduced-motion`. Users with motion sensitivity or vestibular disorders opt into this OS setting — override it at your own risk.

```tsx
const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
const transition = mq.matches ? 'none' : 'transform 300ms ease'
```

## Automated Testing

- Run `axe` (via `jest-axe` or `vitest-axe`) in component tests for every interactive component. It catches missing labels, invalid ARIA, and heading order violations automatically.
- Axe in JSDOM has limited CSS support; it cannot detect color contrast issues from external stylesheets. Use Playwright or Percy for visual contrast regression.

## Anti-Patterns to Reject in Review

- `<div onClick>` without `role`, `tabIndex={0}`, and `onKeyDown`.
- `aria-label` on a `<div>` with no `role` attribute.
- Placeholder used as the sole form label.
- `tabIndex` with a positive value.
- `aria-hidden="true"` on a focusable element — keyboard users get trapped.
- `role="button"` on a `<div>` without `tabIndex={0}` and keyboard handler.
