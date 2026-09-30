# Design Systems

- A design system is the single source of truth for visual language. Colors,
  typography, spacing, shadows, border radii, and breakpoints should be defined in one
  place and referenced everywhere, not re-invented per component.
- Design tokens (named values for each visual property) make the system maintainable.
  Changing a brand color in one token propagates everywhere; changing a hardcoded hex
  requires hunting through every file.
- Audit visual consistency across ten dimensions: color consistency (palette vs random
  hex values), typography hierarchy (clear h1→h2→h3→body→caption scale), spacing
  rhythm (4px/8px/16px grid or equivalent), component consistency (similar elements
  look similar), responsive behavior (fluid at breakpoints), dark mode completeness,
  animation purposefulness, accessibility (contrast, focus states, touch targets),
  information density, and polish (hover states, transitions, empty states).
- Components in the design system should expose only the variants that exist in the
  design. Open-ended prop surfaces lead to design drift. If a variant is not in the
  design, it should not be in the component.
- Keep component API surface minimal. Every prop is a decision point for every
  developer who uses the component. Fewer, well-named props are easier to use correctly
  than many fine-grained options.
- Color must meet contrast requirements: 4.5:1 for body text, 3:1 for large text and
  UI components. Verify contrast for all theme variants (light, dark, high-contrast)
  before shipping a new palette.
- Spacing should follow a consistent scale. Arbitrary spacing values scattered across
  components are a signal that the scale is not being used or is inadequate.
- Animations and transitions should be purposeful. Excessive animation on scroll, entry,
  and hover creates visual noise and may cause vestibular issues for users who prefer
  reduced motion. Respect `prefers-reduced-motion`.
- AI-generated design patterns to avoid: gratuitous purple-to-blue gradients on
  everything, glass morphism cards with no functional purpose, excessive scroll
  animations, generic hero sections with centered text over a gradient, and heavily
  rounded corners applied uniformly without typographic rationale.
