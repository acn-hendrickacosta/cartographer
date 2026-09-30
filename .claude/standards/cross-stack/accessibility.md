# Accessibility

- Target WCAG 2.2 Level AA compliance. The four organizing principles are Perceivable,
  Operable, Understandable, and Robust (POUR). Every accessibility decision maps to at
  least one of these.
- Use the most semantic native element available before reaching for `role` attributes.
  A `<button>` is more accessible than a `<div role="button">` because the browser
  handles keyboard events, focus, and assistive technology announcements automatically.
- All text must meet contrast ratios: 4.5:1 for normal body text and 3:1 for large text
  (18pt+ or 14pt+ bold) and UI components. Color alone must never convey meaning — pair
  it with text, icon, or pattern.
- Every interactive element must be reachable and operable by keyboard alone. Focus
  order must follow the reading order. Visible focus indicators are required; do not
  suppress them with `outline: none` without providing an equivalent.
- Interactive touch and click targets must meet a minimum of 24×24 CSS pixels (WCAG
  2.2 SC 2.5.8). Native mobile targets should be at least 44×44 points.
- All images and icons that convey information need a text alternative (`alt` for `img`,
  `aria-label` for icon buttons). Decorative images use `alt=""`. Never prefix alt text
  with "Image of" — screen readers already announce the role.
- Modals and dialogs must trap focus while open. Keyboard users must be able to close
  with the `Escape` key or an explicit close button. When the modal closes, return focus
  to the element that opened it.
- Dynamic content changes that convey status or feedback must use `aria-live` regions
  (or platform equivalents) so screen readers announce them without requiring focus
  movement.
- Forms must associate labels with controls explicitly. Error messages must be text-
  based (not color-only) and linked to the field they describe via `aria-describedby`.
- Content must reflow at up to 400% zoom without requiring horizontal scrolling or loss
  of function on a standard viewport.
- Cross-platform label attributes: `aria-label` / `<label>` on web; `.accessibilityLabel()` on iOS; `contentDescription` on Android. Hints map to `aria-describedby` on web, `.accessibilityHint()` on iOS, and `stateDescription` semantics on Android.

## Anti-Patterns

- `<div>` or `<span>` as a click target without adding a role and keyboard handler.
- Indicating error or status with a color change only (turning a border red).
- Modals that allow keyboard focus to escape to background content.
- Redundant alt text that repeats what the surrounding text already says.
