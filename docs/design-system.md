# Design System Direction

The redesign should use GitHub Primer as the main product design reference:

- Primer: https://primer.style/
- Primer repository: https://github.com/primer

We are not copying GitHub branding. We are using Primer as the interaction and visual-quality baseline because this platform is developer- and course-workflow oriented: repositories, links, forms, status labels, issue-like lists, tables, dashboards, and dark mode are all familiar parts of that UI language.

## Principles

- Use a clean, utilitarian interface with restrained borders, compact spacing, blue links, and clear status labels.
- Prefer content-first pages over decorative layouts.
- Keep student-facing homework and project pages easy to scan on mobile.
- Keep Cadmin dense, predictable, and task-focused.
- Use Tailwind from the CDN for this redesign pass. Do not introduce a Node/Tailwind build pipeline.
- Do not change the database schema for this redesign. No migrations.

## Component Direction

- Navigation: simple top bar, compact mobile behavior, no overflowing course names.
- Breadcrumbs: lightweight, blue links, low visual weight.
- Lists: row-based layouts with dividers on mobile; subtle bordered containers on desktop where they improve scanning.
- Forms: clear labels, familiar inputs, visible disabled states, compact vertical rhythm.
- Status: Primer-like labels/pills for submitted, open, closed, scored, and review states.
- Dark mode: preserve the existing no-reload toggle model. JavaScript should toggle the `dark-mode` state; CSS should own colors.

## Forms and Actions

Forms should follow a GitHub settings-page pattern: compact sections, clear labels, calm helper text, and actions that are only as wide as their content.

### Form Layout

- Use one form layout language per page. Prefer the settings layout for profile/account/enrollment forms: `settings-section`, a left-side section title/description on desktop, and fields on the right.
- Use horizontal separators sparingly. A `border-t app-border pt-6` separator is appropriate between major form groups; do not add a section header when the group has only one obvious control.
- Avoid nested cards inside forms. Use bordered cards only for repeated records, tables, modals, or genuinely framed admin tools. Normal form sections should be unframed rows separated by spacing or a single divider.
- Keep helper text immediately under the field/control it explains. Helper text should use `settings-helper`, `text-xs` or `text-sm`, and muted text color.
- Keep related fields in a responsive grid. Use one column on mobile and two or three columns on desktop only when fields are short and comparable.
- Keep checkboxes/toggles as inline label rows: checkbox first, label text second, helper text below. Do not put a single checkbox under a redundant section header.
- Do not use input-shaped boxes for read-only data. Use definition-list/meta rows instead.
- Templates must be readable multi-line HTML. Do not add or preserve one-line templates for form pages.

### Buttons

- Use `.primer-button` for the primary action and `.primer-button-secondary` for secondary/navigation actions.
- Buttons should be content-width by default. Use `w-fit`, `inline-flex`, or normal `.primer-button` sizing. Avoid `w-full` on buttons unless a narrow mobile layout cannot otherwise fit the action row.
- On mobile, prefer wrapping action rows (`flex flex-wrap justify-end gap-2`) over full-width buttons. Full-width submit buttons should be an exception, not the default.
- Primary form actions belong at the bottom-right of the form in a footer row: `flex flex-wrap justify-end gap-2 border-t app-border pt-4/pt-6`.
- Cancel/back actions should be secondary buttons or links. They should not visually dominate the save/submit action.
- Icon-only buttons are appropriate for dense tables and menus when the icon is familiar and the control has `title`, `aria-label`, or screen-reader text.
- Do not hard-code one-off button colors in templates. Use the shared Primer-style button classes and add a named variant in CSS only when the meaning is reusable.

### Current Discrepancies To Fix

- Some submit buttons still use `w-full sm:w-auto`, producing wide mobile actions. These should be converted to wrapping content-width action rows unless the specific page needs a full-width mobile CTA.
- Several homework/project submit/login buttons hard-code the blue background in template classes instead of using `.primer-button`.
- Cadmin pages often use bordered cards around form subsections while student settings pages use unframed `settings-section` rows. Keep Cadmin dense cards for operational tools, but do not copy that pattern to normal student/account forms.
- Some templates are still one-line HTML, which makes form structure hard to review and easy to regress.
- Form fields use both `question/question-text` and `settings-section/settings-label` patterns. Use `question` for homework/project question flows; use `settings-section` for account, enrollment, profile, and admin edit settings.

## Secondary Reference

Atlassian Design System can be used as a secondary reference for Cadmin-only workflows when we need denser operational patterns, but Primer remains the primary direction.
