# Datamailer Integration Action Plan

This is a high-level sequence for moving CMP to the target Datamailer model. It
intentionally avoids naming exact files or implementation details. The goal is to
make the order of work clear and keep each phase independently useful.

## 1. Freeze the target contract

Before rewriting CMP behavior, lock the Datamailer-side contract that CMP will
build against.

- Confirm the generic client model: contacts, audiences, recipient-list tree,
  category preferences, templates, campaigns, callbacks, and capture mode.
- Confirm path-key audience nodes with reserved `@` segments:
  `{course}`, `{course}:@e`, `{course}:@e:@homework:{homework}`,
  `{course}:@e:@project:{project}`, outcome nodes, and graduate nodes.
- Confirm upward cascade and membership reasons.
- Confirm Datamailer owns category preferences, global unsubscribe, bounce, and
  complaint suppression.
- Confirm score/result sends use a two-step flow: push computed member metadata,
  wait for ack, then send to the node.
- Confirm deadline reminders use transient computed lists, not durable tree
  nodes.

## 2. Build Datamailer primitives first

CMP should not rewrite onto partial behavior. Datamailer needs the core primitives
available first, even if the UI around them is minimal.

- Contact upsert and contact status/history.
- Preference read/write with client-defined category tags.
- Recipient-list tree with upward cascade and membership reasons.
- Member metadata writes and bulk-upsert.
- Transient send lists for reminders.
- Transactional sends to a contact, address, or recipient-list node.
- Campaign API for broad announcements.
- Callback/event delivery for unsubscribe, resubscribe, bounce, complaint,
  skipped, failed, and message lifecycle events.
- Capture mode/testbed that uses the same production rendering and suppression
  path without sending real email.

## 3. Bootstrap CMP data into Datamailer

Because Datamailer is greenfield, do a clean initial load instead of preserving
old list shapes.

- Load current contacts.
- Load current course registrations into `{course}`.
- Load current homework/project submissions into typed path nodes.
- Load current graduate/certificate state into outcome nodes.
- Load relevant member metadata needed for templates.
- Verify counts by course and node before switching sends.

This is a one-time seed. After this, normal operation should be event-driven.

## 4. Rewrite CMP event emission

Move CMP from role-prefixed list writes to target path-key events.

- Emit registration events into `{course}`.
- Emit submission events into homework/project path nodes.
- Emit removal events when registrations or submissions are withdrawn/deleted.
- Emit outcome events when CMP determines pass/graduation/certificate state.
- Emit member metadata updates when CMP computes scores, review assignments, or
  certificate URLs.
- Use reliable retry/outbox behavior for events that must not be lost.

CMP should not keep its own copy of the Datamailer tree. CMP owns source data and
emits changes; Datamailer owns the audience tree.

## 5. Move preferences to Datamailer

Make Datamailer the single preference store.

- Keep the CMP settings page, but load/save email preferences through Datamailer.
- Stop treating CMP preference fields as authoritative for Datamailer sends.
- Use the three v1 category tags:
  `submission-results`, `deadline-reminders`, and `course-updates`.
- Let Datamailer enforce category opt-outs and global suppression at delivery.
- Store Datamailer callbacks in CMP only for support/audit visibility.

## 6. Port transactional workflows

Move one workflow group at a time, starting with the lowest-risk direct sends.

- Course registration confirmation email.
- Homework/project submission confirmations.
- Certificate availability.
- Homework score emails.
- Peer-review assignment emails.
- Project score emails.
- Deadline reminders through transient computed lists.

For result workflows, the required order is always:

1. CMP computes and persists the result.
2. CMP pushes member metadata/outcome updates to Datamailer.
3. Datamailer acknowledges the batch.
4. CMP triggers the send to the node or transient list.

## 7. Port campaigns and announcements

After transactional sends are stable, move broad announcements.

- Use Datamailer campaigns for course starts, workshop starts, new course
  announcements, and new cohort announcements.
- Use external campaign keys so CMP can create, update, queue, cancel, preview,
  and test-send campaigns without duplicating delivery state.
- Let Datamailer snapshot campaign recipients at queue time.
- Keep CMP-specific concepts in campaign metadata and template context, not in
  Datamailer core.

## 8. Add local E2E capture testing

Make testing production-like without sending real mail.

- Run CMP and Datamailer together locally, for example with Docker Compose.
- Configure only Datamailer into capture mode.
- Exercise CMP normally: register, submit, score, assign reviews, send reminders,
  publish certificates, and queue campaigns.
- Inspect captured rendered subject, text, HTML, links, headers, suppression
  reasons, and unsubscribe/preference decisions.
- Use the same API requests and render path as real delivery.

## 9. Add operational visibility

Before relying on Datamailer for normal sends, make failures visible.

- Show pending/failed CMP event delivery.
- Show Datamailer API errors and last successful sync/send.
- Show per-send counts: intended, suppressed, enqueued, skipped, failed.
- Show callback health.
- Provide an operator repair/bootstrap path for drift or failed imports.

This is not a return to send-time reconcile. It is operational safety and repair.

## 10. Cover generic multi-client requirements

Do not let CMP-specific assumptions leak into Datamailer. The AI Shipping Labs
review adds generic requirements that should be considered before the Datamailer
API hardens.

- Support non-contact recipients and explicit test recipients.
- Support `cc`, `bcc`, `reply_to`, and per-template/category sender rules.
- Keep campaign targeting generic: either materialized transient audiences or a
  small generic filter model, not CMP-specific fields.
- Support richer message history and lifecycle events, including delivered,
  opened, and clicked.
- Support raw MIME or structured message parts for future clients that need
  calendar/iTIP emails.
- Capture mode should store enough rendered detail to debug links, headers,
  suppression, and complex message parts.

## 11. Retire old paths

Once the target flows are stable, remove the old compatibility behavior instead
of supporting two models.

- Stop writing role-prefixed list keys.
- Stop per-send audience reconcile for score/result sends.
- Stop using CMP as the authoritative preference store.
- Retire Mailchimp course-registration sync once Datamailer is the chosen audience
  and campaign system.
- Keep only the target Datamailer path.

## 12. Suggested rollout order

1. Finalize Datamailer contract and capture mode.
2. Implement Datamailer primitives.
3. Seed current CMP audience data.
4. Switch registration and submission events to target path keys.
5. Move preferences to Datamailer.
6. Port direct transactional sends.
7. Port score/result sends with metadata ack-before-send.
8. Port reminders with transient lists.
9. Port campaigns and announcements.
10. Add operational dashboards and repair tools.
11. Remove old list keys, reconcile sends, and duplicate preference storage.
