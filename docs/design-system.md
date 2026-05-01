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

## Secondary Reference

Atlassian Design System can be used as a secondary reference for Cadmin-only workflows when we need denser operational patterns, but Primer remains the primary direction.
