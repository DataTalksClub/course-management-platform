# CMP ↔ Datamailer Integration (Conceptual)

**Purpose of this document: describe the state we want to be in — how the CMP ↔
Datamailer integration *should* work — and what we need to do to get there.**
It is a design document, not a description of the current code. Current behaviour
appears only as implementation context: where it already matches the target, we say
so; where it differs, we call out the target rewrite.

Datamailer is a greenfield dependency for CMP. The target implementation does
**not** need backwards compatibility with today's Datamailer sandbox API shape or
with CMP's current flat/list-reconcile integration. Rewrite the integration to the
target contract; do not support two versions in parallel.

It has two parts:

- **Part 1 — Target design** (sections 1–10): the mental model, every lifecycle
  event, the preference model, and the gaps/work to reach the target.
- **Part 2 — API reference** (the appendix): the endpoints and payloads the target
  uses, annotated with what the current code already does.

Legend used throughout:

- **Target** — how it should work; the thing we are building toward. This is the
  default voice of the document.
- **Today** — what the current code does, called out only to mark the delta we
  need to close (sandbox only; there is no Datamailer production yet).
- ⚠️ **Gap / work to do** — something the target needs that does not exist yet.
  Build work is collected in [§9 Capability gaps](#9-capability-gaps-things-to-raise-on-the-datamailer-side);
  product decisions in [§7 Design decisions](#7-design-decisions); and
  lower-level target decisions in [§10 Design decisions and watchpoints](#10-design-decisions-and-watchpoints).

---

## 1. The two systems and who owns what

The single most important rule: **CMP decides *who should* receive an email;
Datamailer decides whether that email *can be delivered*.**

```mermaid
flowchart LR
    subgraph CMP["CMP — owns intent"]
        direction TB
        users[Users & accounts]
        courses[Courses, registrations, enrollments]
        work[Submissions, scores, certificates]
        deadlines[Deadlines & schedule]
        users ~~~ courses ~~~ work ~~~ deadlines
    end

    subgraph DM["Datamailer — owns delivery & preferences"]
        direction TB
        templates[Email templates]
        senders[Sender / from config]
        prefs[Subscription preferences]
        suppress[Suppression: bounces, complaints, unsubscribes]
        delivery[SQS → SES → delivery events]
        templates ~~~ senders ~~~ prefs ~~~ suppress ~~~ delivery
    end

    CMP -->|"contact sync"| DM
    CMP -->|"recipient-list membership"| DM
    CMP -->|"transactional send (who + context)"| DM
    DM -->|"callbacks: unsubscribe, bounce, complaint, fail"| CMP
```

CMP holds the source data (users, enrollments, submissions, scores, deadlines).
Datamailer holds the delivery machinery **and the learner's email preferences**
(templates, sender config, subscription preferences, hard-bounce/complaint/
unsubscribe suppression, queueing, SES, events). Preferences live in Datamailer so
there is only one store to keep correct (§5).

Datamailer must stay **client-generic**. CMP is one client, not the product model.
Datamailer can expose generic primitives — contacts, category preferences,
recipient-list trees, membership reasons, transactional sends, campaigns, imports,
callbacks — but course-specific concepts such as homework, peer reviews,
certificates, and cohorts live in CMP's keys, metadata, templates, and client
configuration.

In the target, CMP **keeps Datamailer's audience tree current by emitting events**
(§2–§3): a learner joins or leaves a node, computed metadata is written to the
relevant membership, and outcome nodes are updated when CMP determines the
outcome. Preference toggles and unsubscribe state live in Datamailer; CMP only
proxies the settings UI and records callbacks for support. Datamailer still
applies category preferences and deliverability suppression (bounces, complaints)
at delivery time.

This ownership split already holds today; the part we need to build is making the
event stream **complete and reliable** enough that Datamailer's list can be
trusted without a per-send reconcile (§3).

---

## 2. The audience tree (the core mental model)

Datamailer should model a client's audience as a **tree of nested scopes, keyed
by path**. This is **client-agnostic** — CMP is just one client; the same shape
works for any client that has broad and narrow audiences.

- The root `<all>` is the entire client audience.
- Each `:`-separated segment descends one level into a narrower scope.
- System-owned path segments start with `@`. Real course, homework, project, and
  campaign slugs must not start with `@`.
- **Membership cascades upward.** Adding a person to any node automatically makes
  them a member of every ancestor node, up to `<all>`. So when CMP adds someone
  to `{course-slug}:@e:@homework:{homework-slug}`, that person is — by construction
  — also in `{course-slug}:@e:@homework`, `{course-slug}:@e`, `{course-slug}` and
  in `<all>`. CMP never maintains parents and does not keep its own copy of this
  tree; it only sends Datamailer the leaf event/key that changed.

Generic shape, for any client:

```text
<all>
└── {scope}                                  e.g. a course
    ├── {scope}:{subscope}                   e.g. a homework or project
    │   └── {scope}:{subscope}:{outcome}     e.g. passed that project
    └── {scope}:{outcome}                    a course-level outcome, e.g. graduated
```

A client may also insert **intermediate grouping nodes**. CMP uses the reserved
synthetic segment `@e` (*enrolled*) to separate **registered** from **enrolled**,
and item-type segments (`@homework`, `@project`) so homework and project slugs
cannot collide:

```text
<all>
└── {course}                          registered
    └── {course}:@e                   enrolled (submitted ≥ 1 thing)
        ├── {course}:@e:@homework
        │   └── {course}:@e:@homework:{homework}   submitted a homework
        ├── {course}:@e:@project
        │   └── {course}:@e:@project:{project}     submitted a project
        │       └── {course}:@e:@project:{project}:@passed   passed the project
        └── {course}:@e:@graduated    graduated / certified
```

```mermaid
flowchart TD
    ALL["&lt;all&gt;<br/>entire client audience"]
    C["{course}<br/>registered"]
    E["{course}:@e<br/>enrolled — submitted ≥ 1"]
    HWG["{course}:@e:@homework<br/>homework submissions"]
    HW["{course}:@e:@homework:{homework}<br/>submitted a homework"]
    PRG["{course}:@e:@project<br/>project submissions"]
    PR["{course}:@e:@project:{project}<br/>submitted a project"]
    PRP["{course}:@e:@project:{project}:@passed<br/>passed the project"]
    GRAD["{course}:@e:@graduated<br/>graduated / certified"]

    HW -->|cascades to| HWG
    HWG -->|cascades to| E
    PR -->|cascades to| PRG
    PRG -->|cascades to| E
    PRP -->|cascades to| PR
    GRAD -->|cascades to| E
    E -->|cascades to| C
    C -->|cascades to| ALL
```

Arrows point **the way membership cascades**: a member of a leaf is automatically a
member of every ancestor. So "everyone who submitted homework 2 of ML Zoomcamp
2026" is the node `ml-zoomcamp-2026:@e:@homework:homework-2`; emailing it is "name
the node." Email `ml-zoomcamp-2026:@e` to reach everyone **enrolled**,
`ml-zoomcamp-2026` to reach everyone **registered**, and `<all>` to reach everyone.
(`@e`, `@homework`, `@project`, `@passed`, and `@graduated` are reserved system
segments, not real slugs; see namespacing in §10 G12.)

### How CMP populates the tree — and what "registrant / enrolled / submitter" become

A learner's role is simply **where they sit in the tree**, and they get there by an
action:

| Action | Node the learner joins | cascades up to |
| --- | --- | --- |
| Registers for a course | `{course}` | `<all>` |
| Submits homework H | `{course}:@e:@homework:{H}` | `{course}:@e:@homework`, `{course}:@e`, `{course}`, `<all>` |
| Submits project P | `{course}:@e:@project:{P}` | `{course}:@e:@project`, `{course}:@e`, `{course}`, `<all>` |
| **Passes project P** — **Target** | `{course}:@e:@project:{P}:@passed` | `{course}:@e:@project:{P}`, `{course}:@e:@project`, `{course}:@e`, `{course}`, `<all>` |
| **Graduates the course** — **Target** | `{course}:@e:@graduated` | `{course}:@e`, `{course}`, `<all>` |

So the old three-list model becomes tree position:

- **Registered** = member of `{course}`.
- **Enrolled (active learner)** = member of `{course}:@e`. Populated **by cascade** —
  submitting anything joins a typed item node under `{course}:@e`, which cascades
  into `{course}:@e`.
  It is a **real, addressable node**, not a derived query.
- **Submitted homework X** = member of `{course}:@e:@homework:{X}`.
- **Submitted project X** = member of `{course}:@e:@project:{X}`.
- **Registered but not enrolled** = in `{course}` but not `{course}:@e` (registered,
  never submitted).

Anything that varies per person (score, `submitted_at`, country) lives in that
membership's metadata, never in the key.

#### Outcomes (passed, graduated) are deeper *outcome nodes*

Scope nodes fill *automatically* — you enter a typed item node by submitting, and
`{course}:@e` (enrolled) by cascade. **Outcomes** — passing a project, graduating —
are different: they depend on CMP's scoring logic, so they **cannot be derived from
tree shape** and must be written by an explicit event.

Model each outcome as a **deeper node that cascades up**, so it stays directly
addressable for email:

- **Project graduates** (passed project P) = `{course}:@e:@project:{P}:@passed`, a
  child of the project node. "You passed" / project-graduate emails name this node.
- **Course graduates** (completed / certified) = `{course}:@e:@graduated`, a child of
  `{course}:@e` (graduates are necessarily enrolled). Certificate and alumni emails
  name this node.

CMP emits the join when it *determines* the outcome — passing at project scoring
(§4.8), graduating at certificate / course completion (§4.9). Unlike `{course}:@e`
(which fills automatically by cascade), outcome nodes need explicit milestone
events.

> **Decision (updated):** enrolled **is** a node — `{course}:@e`, filled by cascade —
> not a derived predicate and not a flat `course-enrolled` side list. The reserved
> `@e` segment separates *registered* (`{course}`) from *enrolled* (`{course}:@e`),
> so enrolled is directly addressable (this closes G8) while staying a clean tree
> level rather than a role-keyed list.

#### Today's implementation — to be replaced

The code does **not** use this tree yet. Today it writes flat, **role-prefixed**
keys (`course-registrants`, `course-enrolled`, `homework-submitters`, …) with **no
upward cascade** — every level is written by hand (or by the backfill command). The
target rewrite uses path keys with the `@e` enrolled level and typed item levels:

| Target tree node | Current key in code (today) | Rewrite |
| --- | --- | --- |
| `<all>` | the audience (`dtc-courses`) | keep |
| `{course}` | `course-registrants:{course}` | rename to path key |
| `{course}:@e` | `course-enrolled:{course}` | rename to the `:@e` node |
| `{course}:@e:@homework:{homework}` | `homework-submitters:{course}:{homework}` | rename to typed path key |
| `{course}:@e:@project:{project}` | `project-submitters:{course}:{project}` | rename to typed path key |
| `{course}:@e:@project:{project}:@passed` *(Target)* | — *(not built)* | add (outcome node) |
| `{course}:@e:@graduated` *(Target)* | `course-graduates:{course}` *(not built)* | add (outcome node) |

The target structural changes are **(a) pure path keys with the `:@e` enrolled level**,
**(b) typed item levels to avoid homework/project slug collisions**, and
**(c) upward cascade so parents are implicit** (gaps #8–#9). Datamailer is
greenfield and CMP can rewrite this integration directly against the target. We can
implement the new keys directly.

**Two building blocks** compose every flow below:

| Building block | What it represents | Datamailer call |
| --- | --- | --- |
| **Contact** | a person in the audience | `POST /api/contacts` |
| **Recipient-list membership** | a person inside one tree node | `PUT /api/recipient-lists/{key}/members/{source_object_key}` |
| **Transactional send** | an actual email | `POST /api/transactional/send` (one person) or `POST /api/recipient-lists/{key}/transactional-send` (a whole node) |

The target maintains these nodes **by events** (§3), adds the
`{course}:@e:@graduated` node, and relies on **upward cascade** so parent nodes are
implicit. Today the code writes flat role-prefixed keys explicitly, with no
cascade — see the rewrite mapping above and gaps #8–#9.

---

## 3. How the audience list is maintained — keep the two in sync

This is the core design decision, so it gets its own section.

**Guiding principle: keep CMP and Datamailer continuously synchronized — never let
them diverge.** Every change in CMP is mirrored to Datamailer *as it happens*, so
Datamailer's copy always matches CMP. There is no separate "rebuild the list"
step, because the list never went out of sync in the first place.

**We explicitly reject reconcile-at-send.** Stopping to re-query the whole
database, rebuild a full recipient snapshot, and diff it against Datamailer on
*every* email is fragile and slow — it treats divergence as normal and papers over
it once per send, instead of preventing it. The fix for "the two might disagree"
is to **not let them disagree**: emit the events reliably.

**Target: Datamailer maintains the tree as the live audience. CMP emits source
events and computed metadata updates; Datamailer applies them to the tree.**

Every membership change is one small event from CMP to Datamailer:

| When this happens in CMP | CMP emits |
| --- | --- |
| Learner registers | add member to `{course}` |
| Learner submits homework / project | add member to `{course}:@e:@homework:{homework}` or `{course}:@e:@project:{project}` (cascades up) |
| Homework / project is scored | bulk-update member metadata (score, result links, pass/fail) on the node |
| Learner completes / is certified | add member to `{course}:@e:@graduated` |
| Learner is erased or a registration/submission is removed | remove the source membership reason or erase/anonymize the contact |

Datamailer applies each event and keeps the node current. For a simple
announcement, CMP can name the node directly. For result emails, CMP first pushes
the computed batch metadata (scores, result URLs, review links, pass/fail state)
to the members of that node, waits for Datamailer to acknowledge it, and only then
triggers the node send.

```mermaid
flowchart LR
    subgraph events["Event stream (target)"]
        e1[register] --> L
        e2[submit] --> L
        e3[score/review batch = metadata update] --> L
        e4[removal / erasure] --> L
    end
    L[(Datamailer tree node = live list)]
    send[Send: name node after required metadata is acked] --> L
    L --> mail[Datamailer emails current members]
```

**No reconcile at send time.** CMP does not re-query its database and ship a full
audience snapshot with `remove_absent_members` on every send. The durable audience
is already correct because the events kept it correct. CMP may still compute and
push a **batch of per-member metadata** for the workflow transition that makes the
email possible; that is not audience reconciliation.

### Some events are computed, not user actions

Not every event is a single user click. Datamailer cannot know things CMP computes
at a lifecycle transition — **final scores, the peer-review assignment graph
(who reviews whom), pass/fail.** These reach Datamailer because **the computation
itself is an event source.** Two kinds of event:

- **Action events** — one user action → one event (register, submit). The submitter
  *set* is already current at form-close this way: every submission emitted a join.
- **Computed (batch) events** — at a transition CMP computes derived state and emits
  the results as a batch of **member-metadata updates and outcome-node joins**
  (scoring → per-submission scores + `:@passed`; project form closes → each
  reviewer's assigned-project links as metadata). Datamailer never runs course
  logic — CMP computes, then tells it.

**This is bulk-upsert, not reconcile.** The batch *pushes what CMP computed*
(`members/bulk-upsert`, keyed by `source_object_key`); it does **not** diff the
audience or remove-absent. Keyed by `source_object_key`, bulk-upsert
creates-or-updates, so it is also self-healing for membership — a member is correct
even if an earlier join was missed.

**Transport — two paths by size.** A cohort batch can be large (thousands of
submitters with score metadata), so choose the transport by size:

- **Inline, chunked** *(default)* — POST to `members/bulk-upsert` in pages of
  ~500–1000. Each page is small, individually retriable, and acks synchronously.
  Fine up to a few thousand members.
- **By reference** *(large batches)* — CMP writes the batch as a **JSONL** file
  (one member per line — *streamable*, unlike a single JSON array or YAML), uploads
  it to **its own S3**, and hands Datamailer a **time-limited pre-signed URL**.
  Datamailer fetches and ingests **asynchronously**, returning an import-job id; the
  **send waits for the import to ack** (G7). This keeps CMP's bucket private (no
  cross-account IAM) and decouples transfer from processing.

Use **JSONL, not YAML** — YAML isn't streamable and is slow to parse at scale. The
outbox holds a *reference* to the file, not thousands of individual events. This is
still bulk-upsert (push what changed), never reconcile. (gap #12)

**CMP builds the batch from its own data — it does not mirror Datamailer's list.**
To push scores it iterates its **own** submissions; to push assignments, its **own**
assignment graph. It needs neither a local copy of node membership nor any
subscription state: preferences live in Datamailer (§5) and are applied at delivery,
so the batch includes *everyone who did the work* and Datamailer suppresses opt-outs.

**What triggers the batch:** the CMP-side transition — never the send, never
Datamailer. Either an **operator action** in cadmin (Score homework, Assign peer
reviews, Score project) or a **scheduled job** (EventBridge) for time-based
transitions. ("Form closes" is not itself an event — the trigger is the operator
action allowed *after* the deadline, or a scheduled job.)

```mermaid
sequenceDiagram
    participant Op as Operator / scheduler
    participant CMP
    participant DM as Datamailer

    Op->>CMP: Score homework (transition)
    CMP->>CMP: Compute scores + outcomes (own data)
    CMP->>CMP: Persist scores
    CMP->>DM: bulk-upsert member metadata + outcome joins (retry)
    DM-->>CMP: acked
    CMP->>DM: Send — name the node
    DM->>DM: suppress opt-outs, render per-member metadata
```

The send fires **only after the batch is acked** (gap #10 reliable emission, G7
ordering), so no one is emailed with missing scores.

The same **compute-then-bulk-push** pattern also handles *negative* audiences —
"who has **not** done X" (deadline reminders). CMP computes the set (Datamailer
can't, it's a set-difference) and materializes it as a **transient send-list**.
Note the distinction: the **durable audience tree** is never reconciled (§3's
rule); a reminder list is a separate, **send-scoped** object CMP legitimately
recomputes each run. See §4.10 and G3.

### What we need to do to get there

Event-driven is only correct if the event stream is **complete and reliable**.
That is the work:

1. **Emit every audience event — including removals.** Today CMP emits joins
   (submissions) but rarely emits removals. The target must emit joins, removals,
   outcome joins, erasure events, and computed metadata updates so the list never
   silently drifts. Preference/unsubscribe state is not mirrored from CMP because
   Datamailer owns it.
2. **Make emission reliable (transactional outbox + retry).** A dropped event
   means a wrong list with no automatic correction. CMP should write events to an
   outbox when the local change must not be lost, then deliver with retry, so no
   audience event is ever lost (gap #10). Operator-triggered computed batches such
   as scoring can persist the local score first, then push the Datamailer batch
   with retry and block the send until Datamailer acknowledges it.
3. **Seed once when enabling the integration (bulk API).** Datamailer is
   greenfield, so the first load can be a clean bootstrap from CMP's current data:
   people who already registered or submitted are loaded per node through the
   **bulk API** (`members/bulk-upsert`), then normal operation switches to events.

After that seed, the system is **purely event-driven — there is no reconcile in
normal operation.** Reconcile is an operator repair/audit tool, not a send-time
step.

```mermaid
flowchart LR
    one["One-time bootstrap — bulk API<br/>(load current CMP data)"] --> steady["Steady state — events only<br/>no reconcile in sends"]
```

> **Today (the delta to close):** the current code does the opposite — it treats
> Datamailer's accumulated list as untrusted and **reconciles a full DB snapshot
> on every score send** (`member_sync: reconcile`, `remove_absent_members: true`).
> That stopgap exists because the audience event stream is incomplete today. In
> the target rewrite, per-send reconcile goes away and bulk-load is used only for
> the initial bootstrap, computed metadata batches, transient reminder lists, or
> operator repair.

---

## 4. Lifecycle, event by event

Each subsection is one event: a diagram, what fires, which preference gates it,
and Today vs Target.

A learner's whole journey:

```mermaid
journey
    title Learner journey and the emails it produces
    section Intake
      Register for course: 3: Learner
    section Active learning
      Submit homework: 4: Learner
      Receive submission confirmation: 5: CMP
      Receive homework scores: 5: Operator
    section Project
      Submit project: 4: Learner
      Peer reviews assigned: 3: Operator
      Submit peer reviews: 4: Learner
      Receive project scores: 5: Operator
    section Completion
      Certificate available: 5: Operator
```

### 4.1 Course registration

A person fills the registration form. This is **interest capture, not email
subscription** — no email is sent.

```mermaid
sequenceDiagram
    participant Browser
    participant CMP
    participant DB as CMP DB
    participant MC as Mailchimp
    participant DM as Datamailer

    Browser->>CMP: Submit registration form
    CMP->>DB: Create CourseRegistration
    CMP-->>Browser: Success
    Note over CMP,DM: after commit (on_commit)
    CMP->>MC: Upsert member + tag
    CMP->>DM: POST /api/contacts (subscribed, verified)
    CMP->>DM: PUT course-registrants:{course} member (registration:{id})
```

- **Event (target):** add member to node `{course}` (cascades to `<all>`).
  Registering is simply what puts a learner in the course audience.
- **Contact:** upserted as `status: subscribed`, `verified: true`,
  `email_validation: externally_validated` — the form requires newsletter
  consent, so we mark it validated.
- **Preference:** none gates this; it sends no email.
- **Email sent:** none.

**Today (delta):** already emits the membership, but under the role-prefixed key
`course-registrants:{course_slug}` (or `:{campaign_slug}` if no course is attached
yet) — to be renamed to the path key `{course}` (gap #9). A parallel Mailchimp
sync runs too, eventually retired once Datamailer is the single audience store.

### 4.2 Course enrollment

Enrollment is created **implicitly on the first submission** (`get_or_create`),
not by a separate action. A `post_save` signal fires **only on creation**.

```mermaid
sequenceDiagram
    participant Learner
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Learner->>CMP: First submission (homework or project)
    CMP->>DB: get_or_create Enrollment  (created = true)
    Note over CMP,DM: post_save(Enrollment), created only
    CMP->>DM: POST /api/contacts with course tags + custom fields
    CMP->>DM: PUT course-enrolled:{course} member (user:{student_id})
```

In the target, **`{course}:@e` is the enrolled list**. The first submission's node
join (§4.3 / §4.5) makes the learner enrolled by cascade into `{course}:@e`; the
only extra thing to do here is **enrich the contact**.

- **Event (target):** on first submission, enrich the contact with cohort tags
  (`course-{family}`, `course-cohort-{course}`) and custom fields (course
  slug/title/family/cohort). No separate role-prefixed `course-enrolled:{course}`
  membership is written.
- **Preference:** none; no email.

**Today (delta):** the code materialises a role-prefixed
`course-enrolled:{course_slug}` list (member key `user:{student_id}`) via a
`post_save` signal that fires **only on create** (`if not created: return`). The
target renames that list to the path-keyed enrolled node `{course}:@e` and fills it
by cascade (gap #9). ⚠️ The only-on-create guard also means later changes (e.g. a
preference toggle) never re-sync the contact — see §5 and gap #1.

### 4.3 Homework submission (and resubmission)

Two things happen on submit, as two separate calls: a **confirmation email** and
a **list-membership upsert**.

```mermaid
sequenceDiagram
    participant Learner
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Learner->>CMP: Submit / update homework
    CMP->>DB: Create or update Submission (submitted_at = now)
    CMP-->>Learner: Saved
    Note over CMP,DM: after commit
    CMP->>DM: POST /api/transactional/send — homework-submission-confirmation
    CMP->>DM: PUT homework-submitters:{course}:{hw} member (homework-submission:{id})
```

- **Confirmation gated by:** `email_submission_confirmations` (default `True`).
- **Node joined:** `{course}:@e:@homework:{homework}` (today keyed
  `homework-submitters:{course}:{homework}`, gap #9), member key
  `homework-submission:{submission_id}`.
- **Resubmission:** updating a submission refreshes `submitted_at`, so:
  - the confirmation's idempotency key
    (`homework-submission:{id}:{submitted_at_iso}`) **changes → a new
    confirmation email is sent** for every update;
  - the list member is **upserted in place** (same `source_object_key`, new
    metadata/timestamp/scores).

**Today:** confirmation-on-submit and confirmation-on-update both fire; membership
upserts in place. **Target:** keep — re-sending the confirmation on update is
correct because the learner changed what they submitted (see the
[resubmission design question](#q2-re-sending-after-an-update)).

### 4.4 Homework scoring (operator publishes results)

An operator scores the homework in cadmin. CMP persists scores, **pushes each
score as a metadata update on the member's node**, then triggers one send that
just **names the node** — Datamailer already holds the members.

```mermaid
sequenceDiagram
    participant Operator
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Operator->>CMP: Click "Score homework"
    CMP->>DB: Recompute & persist scores
    loop per scored submission (event)
        CMP->>DM: PUT {course}:@e:@homework:{homework} member metadata = score
    end
    CMP->>DM: Send template to node {course}:@e:@homework:{homework}
    DM->>DM: Render per-member context from node metadata
    DM-->>Operator: created / enqueued / skipped counts
```

- **Audience:** node `{course}:@e:@homework:{homework}` — no snapshot, no `remove_absent`. The
  node is already correct because submission and preference events kept it correct.
- **Category:** submission — Datamailer suppresses opted-out contacts at delivery
  (§5), not a per-send DB filter.
- **Idempotency:** base key `homework-score:{course}:{homework}`, Datamailer
  appends each member's `source_object_key` → safe to re-run.

**Today (delta):** the code instead **builds a full submitter snapshot from the DB
and sends it with `member_sync: reconcile` + `remove_absent_members`** — the
per-send reconcile §3 removes. It filters the snapshot by preference, drops
no-email and duplicate submissions, and (usefully) still includes submissions that
predate the integration. The target replaces that snapshot with the event-kept
node; the preference filtering moves to preference events (gap #1), and reliable
emission (gap #10) is what lets us trust the node without the snapshot.

### 4.5 Project submission

Identical shape to homework submission, on the project list.

- **Confirmation gated by:** `email_submission_confirmations`.
- **Node joined:** `{course}:@e:@project:{project}` (today keyed
  `project-submitters:{course}:{project}`, gap #9), member key
  `project-submission:{submission_id}`.
- **Resubmission:** same semantics as homework (new `submitted_at` → new
  confirmation; member upserted in place).

**Today / Target:** same as homework.

### 4.6 Peer-review assignment (the separate project flow)

Projects have an extra step homework doesn't. After the submission deadline, an
operator **assigns peer reviews**, which moves the project to `PEER_REVIEWING`
and opens a review window. Submitters get a "go review your peers" email.

```mermaid
stateDiagram-v2
    [*] --> COLLECTING_SUBMISSIONS
    COLLECTING_SUBMISSIONS --> PEER_REVIEWING: operator assigns peer reviews (after due date)
    PEER_REVIEWING --> COMPLETED: operator scores project (after review window)
    COMPLETED --> [*]
```

```mermaid
sequenceDiagram
    participant Operator
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Operator->>CMP: Assign peer reviews
    CMP->>DB: Create PeerReview rows, state → PEER_REVIEWING
    CMP->>DB: Build submitter snapshot (filter by preference)
    CMP->>DM: POST project-submitters:{course}:{project}/transactional-send — peer-review-assignment
```

- **Computed batch (target):** assigning reviews is a *computed transition* (§3) —
  CMP computes who reviews whom and pushes **each reviewer's assigned-project links
  as member metadata** (bulk-upsert), *then* sends. The submitter set itself is
  already present from join events; only the assignment data is new.
- **Send (target):** name the node `{course}:@e:@project:{project}` — Datamailer already holds
  the members; the email renders each reviewer's links from the pushed metadata. No
  snapshot.
- **Gated by:** `email_submission_confirmations`.
- **Idempotency:** `peer-review-assignment:{course}:{project}`.

**Today (delta):** the code builds a submitter snapshot and sends it with the
per-send reconcile (the §3 stopgap), to the `project-submitters` key.
Note this is the *"go review your peers"* assignment email, sent once to all
submitters. The *reminder* for those who **still owe** reviews is separate and
CMP-computed at run time (§4.10) — it needs no maintained node (gap #2 is optional).
Also consider whether "go do your reviews" should be gated by
`email_deadline_reminders` rather than `email_submission_confirmations` (see
[preference granularity](#q3-preference-granularity)).

### 4.7 Peer review submitted (by a learner)

When a learner submits their evaluation of a peer, CMP records it and shows a
thank-you message — **nothing is sent to Datamailer today**. There is no
peer-review-submission confirmation email and no list update.

```mermaid
sequenceDiagram
    participant Learner
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Learner->>CMP: Submit peer evaluation
    CMP->>DB: PeerReview state → SUBMITTED, save
    CMP-->>Learner: "Thank you for submitting your evaluation"
    Note over CMP,DM: no Datamailer call today
```

- **Fires:** `project_eval_post_submission` (`courses/views/project.py`) — sets the
  review state to `SUBMITTED` and saves. No email, no Datamailer call.
- **Email sent today:** none.

**Today:** **not** a Datamailer integration point. **Target (candidate):**
(a) optionally send a "your reviews are recorded" confirmation gated by
`email_submission_confirmations`, and/or (b) remove the learner from a
`peer-review-pending` audience once they've finished all assigned non-optional
reviews — which would make the peer-review-due reminder (§4.10) self-clearing.
⚠️ both depend on the `peer-review-pending` list (gap #2) and a new template.

### 4.8 Project scoring

After the review window closes, the operator scores the project. CMP computes
median peer scores, persists them, moves the project to `COMPLETED`, and — exactly
like homework scoring (§4.4) — **pushes each score as member metadata on the node,
then names the node** to send.

- **Node:** `{course}:@e:@project:{project}` (today keyed `project-submitters:{course}:{project}`).
- **Outcome event (target):** learners whose submission `passed` also join the
  outcome node `{course}:@e:@project:{project}:@passed` (§2), enabling later project-graduate /
  "you passed" emails.
- **Category:** submission — Datamailer-enforced at delivery (§5).
- **Idempotency:** `project-score:{course}:{project}`.

**Today (delta):** same per-send reconcile snapshot as §4.4; the target replaces it
the same way (events keep the node correct).

### 4.9 Certificate availability

When a certificate URL is published for an enrollment (bulk upload / API), the
learner gets a one-off email. This one is a **direct send**, not a list send.

```mermaid
sequenceDiagram
    participant Operator
    participant CMP
    participant DB as CMP DB
    participant DM as Datamailer

    Operator->>CMP: Publish certificate URLs (bulk)
    CMP->>DB: Set certificate_url (empty → non-empty)
    Note over CMP,DM: per enrollment, after commit
    CMP->>DM: POST /api/transactional/send — certificate-availability
```

- **Gated by:** `email_course_updates` (default `True`) — it's a course
  operational update, not a submission confirmation.
- **Idempotency:** `certificate-available:{enrollment_id}` (per enrollment).
- **List:** none — direct send to one address.

**Today:** direct send, gated by `email_course_updates`. **Target:** issuing a
certificate is the **graduation outcome event** — the learner joins the outcome
node `{course}:@e:@graduated` (§2), and the certificate email is a send to that node.
The same node powers later alumni / graduate campaigns.

### 4.10 Deadline reminders

CMP owns scheduling because only CMP knows who is enrolled, who has submitted,
and who still owes peer reviews. A scheduled command (`send_deadline_reminders`,
run by EventBridge) recomputes eligibility from current state, replaces each
transient reminder list, and triggers one list send per active reminder event.
All three reminders are gated by `email_deadline_reminders` and **skip anyone who
has already done the thing** the reminder is about.

```mermaid
sequenceDiagram
    participant Sched as External scheduler (EventBridge)
    participant CMP as send_deadline_reminders
    participant DB as CMP DB
    participant DM as Datamailer

    Sched->>CMP: Run one-off task
    CMP->>DB: Compute who still owes the action (negative audience)
    loop per active reminder event
        CMP->>DM: bulk-upsert the computed set → reminder list
        CMP->>DM: Send to the reminder list, category = deadline
    end
```

> **Reminders are a *negative* audience — a CMP-computed send-list.** Their audience
> is *who has **not** submitted / still owes reviews* — a set-difference Datamailer
> can't derive. So the scheduled CMP job **computes the set and pushes it as a
> transient send-list** via bulk-upsert (file-by-reference if large, §3 / gap #12),
> then sends. This does **not** violate "no reconcile" (§3): that rule governs the
> durable audience *tree*; a reminder list is a separate, send-scoped object. See G3.

Three reminder types, **all implemented today**:

| Reminder | When | Audience (who gets it) | List key |
| --- | --- | --- | --- |
| **Homework due** | 24h before due | enrolled, **not yet submitted** | `deadline-reminders:homework:{course}:{hw}:24h` |
| **Project due** | 7d **and** 24h before due | enrolled, **not yet submitted** | `deadline-reminders:project-submission:{course}:{project}:{7d\|24h}` |
| **Peer review due** | 24h before review deadline | submitted a project **and still has ≥1 unsubmitted, non-optional** assigned review | `deadline-reminders:peer-review:{course}:{project}:24h` |

Idempotency keys mirror the event (`deadline-reminder:homework:{hw_id}:24h`,
`deadline-reminder:project:{project_id}:{7d|24h}`,
`deadline-reminder:peer-review:{project_id}:24h`) and omit the command timestamp,
so the command can run repeatedly without duplicating.

**All three are computed the same way — none need a maintained "pending" node.**
CMP queries its own data each run and pushes the result:

- **Homework / project due** are conceptually a node diff —
  `{course}:@e` (enrolled) **minus** the typed item node for the submitted work
  (`{course}:@e:@homework:{homework}` or `{course}:@e:@project:{project}`). CMP
  runs the diff from source (more robust than asking Datamailer to diff nodes, and
  no new Datamailer capability).
- **Peer-review due** has no clean node diff ("still owes reviews" depends on the
  assignment graph and review progress), so CMP queries `PeerReview` rows
  (`state=TO_REVIEW`, non-optional) directly. Same mechanism, richer query.

Eligibility is **self-clearing**: finishing the action (submitting, completing
reviews) drops the learner from the next run's computed set — no node removal
needed. A dedicated `peer-review-pending` node (gap #2) is therefore **optional** —
justified only if a *non-reminder* feature needs to address "who owes reviews"
directly via Datamailer.

**Today:** all three implemented; because eligibility is recomputed each run,
moving a deadline just changes the next run (no campaign to update).
**Target:** keep; extend the "tighten audience to who still owes work" pattern.

### 4.11 General course announcements (new courses, cohorts, starts, modules) — not built

Broad, non-personalized announcements — "a new course is open", "a new cohort is
launching", "the course starts Monday", "module 3 is live" — are **not
implemented anywhere today**. The `email_course_updates` preference exists (its
help text even mentions course-start announcements), but no code sends them.

These are **campaign territory, not transactional**: one message to a whole
audience node, not one-per-learner with per-learner context.

- **Audience:** a tree node — `<all>` for a platform-wide notice, `{course-slug}`
  for one course/cohort, optionally `{course-slug}` filtered by module progress.
- **Category:** course updates — Datamailer-enforced at delivery (§5).
- **Mechanism (target):** a Datamailer **campaign** with an external key (Part 2 →
  Broad course emails / Campaign API, gap #5), so CMP can create / queue / cancel
  a scheduled announcement and Datamailer snapshots recipients at queue time.

**Today:** absent — any such email is sent by hand from the Datamailer operator
UI. **Target:** CMP-driven campaign API keyed per announcement. ⚠️ depends on the
campaign API (gap #5).

---

## 5. Preferences — store them in Datamailer, not CMP

The cleanest way to keep two stores in sync is to **not have two stores.** So in
the target, **CMP does not store email preferences at all.** They live only in
Datamailer, which already owns unsubscribe and suppression state. With a single
store, preference divergence is *impossible* — there is nothing to sync.

In the target, **CMP barely touches preferences** — it hosts the settings UI but
**proxies reads and writes to Datamailer asynchronously**, and stores nothing.

- **Settings page = CMP-hosted, preferences loaded asynchronously.** CMP renders
  its settings page **immediately** and does **not** block on Datamailer. The email
  preferences panel fetches the learner's toggles **asynchronously** (a client-side
  call to CMP's own backend) *after* the page is shown. If Datamailer is slow or
  down, the page still loads — only the preferences panel shows a **fallback**
  ("email preferences are temporarily unavailable — try again later").
- **CMP backend proxies to Datamailer (no storage).** The async request hits CMP's
  own backend, which calls Datamailer for that contact's toggles and relays them;
  saving a toggle goes the same path (browser → CMP backend → Datamailer). CMP is a
  pass-through and persists no preference. Identity is ordinary: the learner is
  logged into CMP, and CMP's backend authenticates to Datamailer with its API key —
  no token is handed to the browser and nothing is embedded from Datamailer.
- **Categories are generic, tag-driven, and client-defined.** A client defines its
  own set of subscription categories; each category is a **tag**, and every
  triggered message type declares the category tag it belongs to. The settings
  panel renders one toggle per category that client defined. **CMP happens to
  define three** — but nothing is hardcoded to three; another client defines its own.
  This mirrors the generic audience tree (§2): generic on the Datamailer side,
  specialized per client.
- **Sending = Datamailer enforces.** A send names a node and declares its category
  tag; Datamailer suppresses contacts who toggled that category off, at delivery.
  CMP never filters by a stored preference.

```mermaid
sequenceDiagram
    participant Learner
    participant Page as CMP page (browser)
    participant API as CMP backend
    participant DM as Datamailer

    Learner->>Page: Open settings
    Page-->>Learner: Render page immediately (no wait on Datamailer)
    Page->>API: async fetch preferences
    API->>DM: GET this contact's category toggles
    alt Datamailer reachable
        DM-->>API: toggles
        API-->>Page: toggles
        Page-->>Learner: show toggles
        Learner->>Page: toggle a category
        Page->>API: async save
        API->>DM: write toggle
    else Datamailer slow / down
        DM--xAPI: unavailable
        API-->>Page: error
        Page-->>Learner: panel shows "temporarily unavailable — try later"
    end
```

CMP's category set — **a client-defined example; the model itself is generic**:

| CMP category (tag) | Message types it gates |
| --- | --- |
| **submission & results** | submission/score confirmations, peer-review assignment |
| **deadline reminders** | the three reminders (§4.10) |
| **course updates** | certificate availability, new course launches, new cohort announcements, course/module announcements |

**No duplication — CMP never needs a local copy.** The three places CMP might seem
to need preferences, it doesn't:

- *Settings page* — proxies to Datamailer (above); stores nothing.
- *Sending* — CMP names a node + category; **Datamailer suppresses opt-outs at
  delivery** (gap #11). CMP never filters by preference.
- *Audience computation, incl. reminders* — CMP computes by **who did the work**
  (its own enrollments / submissions), not by preference. A reminder batch is
  "everyone who hasn't submitted"; Datamailer drops the deadline-unsubscribed when
  it sends. The batch may be slightly larger than what's delivered — that's fine;
  pre-filtering would require a local preference copy, i.e. the duplication we are
  removing.

(The **only** duplication is in *today's* code — three CMP booleans plus
Datamailer's own unsubscribe state — and they drift. See below.)

### Today (the delta to close)

Today CMP **does** store three boolean fields on the user
(`email_submission_confirmations`, `email_deadline_reminders`,
`email_course_updates`, all default `True`) and gates every send by reading them.
Sync is **one-way and broken**: a Datamailer unsubscribe webhook writes back to
those fields (`subscription.unsubscribed` + a recognized `preference_key`), but a
**CMP-side toggle pushes nothing** to Datamailer (the contact is synced only on
*creation*, `if not created: return`). That asymmetry is exactly the divergence we
are designing out.

### Work to do

- **Datamailer:** a per-contact, per-category preference **read + write** API with
  client-defined category tags (gap #1); **delivery-time enforcement** of a send's
  declared category tag (gap #11).
- **CMP:** host the settings UI and load/save preferences **asynchronously via its
  backend**, proxying to Datamailer, with the unavailable-fallback panel; **remove
  the three preference fields** and all per-send preference gating.
- Keep the existing Datamailer→CMP webhook only for *storing* events for support
  (bounces, complaints) — not as the preference store.

---

## 6. Where Current and Target differ — at a glance

| Area | Today | Target |
| --- | --- | --- |
| Audience model | flat role-prefixed lists incl. a materialised `enrolled` | **path-keyed tree**; `enrolled` = `{course}:@e` node; `{course}:@e:@graduated` added (gap #9) |
| List maintenance | **reconcile a full DB snapshot on every send** | **event-driven** — emit each change; Datamailer's tree is the live list; **no per-send reconcile** (§3) |
| Bulk / reconcile API | used at send time | **bootstrap / repair only** — never part of normal sends |
| Event emission | joins only; no preference/unsubscribe push; rarely removals | **complete + reliable** (outbox + retry), incl. removals & preferences (gap #10) |
| Preference sync | Datamailer → CMP only | **bidirectional** (add CMP → Datamailer, gap #1) |
| Cascade | none — every level written by hand | adding a leaf implies ancestors (gap #8) |
| Peer-review audience | all project submitters | only those who still owe reviews (gap #2) |
| Certificate audience | direct send, no list | `{course}:@e:@graduated`-backed |
| Broad announcements | operator UI campaigns | CMP-driven campaign API with external key (gap #5) |
| Submit confirmation + membership | two separate calls | keep separate; no force-send-on-membership in v1 (§7) |
| Preference granularity | results share `email_submission_confirmations` | v1 uses three category tags (§7) |

---

## 7. Design decisions

These were the softer product questions. They are now target decisions for the
first Datamailer rewrite unless a product requirement changes.

### Q1. Trigger-on-membership vs separate send

Today, submitting homework makes **two** calls: send the confirmation email, and
upsert the list member. A campaign-style alternative is "adding a member can
optionally **force a send**" — one call that both records membership and emails.

- **For:** fewer calls; membership and notification can't drift apart.
- **Against:** the two have genuinely different lifecycles. Membership is *funnel
  state* (durable); the confirmation is a *per-event transactional* keyed to
  `submitted_at`. Score/result emails already use the unified pattern
  (update node metadata + send the node) and that's correct *because the operator chooses the
  moment*. Auto-sending on every membership add would email people at the wrong
  time (e.g. a backfill or a resubmission shouldn't blast a score email).

**Decision:** keep submit-time confirmation and membership separate; keep
operator-time results as metadata-update-then-node-send. Do **not** require a
force-send-on-membership flag for v1. If a future workflow truly needs "add member
and immediately send", it should be an explicit, opt-in Datamailer feature with a
separate idempotency key, never the default membership behavior.

### Q2. Re-sending after an update

If a learner edits a submission, should they get a fresh email?

- **Submission confirmation:** **yes, today** — `submitted_at` changes, the
  idempotency key changes, a new confirmation goes out. This is correct: the
  content they submitted changed.
- **After scores are published:** today, editing a submission does **not**
  re-trigger a score email (scores are operator-published, idempotent per
  homework). That's the safe default — we don't want edits to silently re-blast
  scores. If we ever want "your updated submission was re-scored" emails, that's
  a deliberate new event with its own key, not a side effect of the edit.

**Decision:** keep current behavior; make any post-score re-send an explicit
operator action.

### Q3. Preference taxonomy

V1 uses exactly the three categories exposed on the learner settings page:

- `submission-results` — homework/project submission confirmations and score
  emails.
- `deadline-reminders` — homework deadline reminders, project deadline reminders,
  and peer-review completion reminders / assignments.
- `course-updates` — general course messages, workshop messages, course start
  announcements, new course announcements, and new cohort announcements.

**Decision:** do not add dedicated result or peer-review preference fields in v1.
The settings UI stays simple, and Datamailer category tags remain client-defined
configuration rather than CMP database fields. If learners complain about
over-emailing, split `submission-results` or `deadline-reminders` later as a
product change with a clear migration of existing category preferences.

---

## 8. Glossary of keys

```text
# Audience tree nodes — TARGET (pure path keys, §2; '@' = reserved system segment)
<all>
{course_slug}                                  # registered
{course_slug}:@e                               # enrolled (submitted >= 1)
{course_slug}:@e:@homework                     # all homework submitters in course
{course_slug}:@e:@homework:{homework_slug}     # submitted the homework
{course_slug}:@e:@project                      # all project submitters in course
{course_slug}:@e:@project:{project_slug}       # submitted the project
{course_slug}:@e:@project:{project_slug}:@passed # outcome: passed the project
{course_slug}:@e:@graduated                    # outcome: completed / certified

# Current keys in code — TODAY, to replace in the target rewrite (gap #9)
course-registrants:{course_slug}                   -> {course_slug}
course-enrolled:{course_slug}                      -> {course_slug}:@e
homework-submitters:{course_slug}:{homework_slug}  -> {course_slug}:@e:@homework:{homework_slug}
project-submitters:{course_slug}:{project_slug}    -> {course_slug}:@e:@project:{project_slug}
peer-review-pending:{course_slug}:{project_slug}   -> {course_slug}:@e:@project:{project_slug} review-pending subset  # optional ⚠️
certificate-eligible:{course_slug}                 -> {course_slug}:@e:@graduated        # not built ⚠️

# Deadline-reminder lists (scoped to who still owes the action)
deadline-reminders:homework:{course_slug}:{homework_slug}:24h
deadline-reminders:project-submission:{course_slug}:{project_slug}:{7d|24h}
deadline-reminders:peer-review:{course_slug}:{project_slug}:24h

# Member keys (source_object_key)
registration:{registration_id}
user:{student_id}                                     # today's role-prefixed enrolled list member key
homework-submission:{submission_id}
project-submission:{submission_id}

# Idempotency keys (events)
homework-submission:{submission_id}:{submitted_at_iso}
project-submission:{submission_id}:{submitted_at_iso}
homework-score:{course_slug}:{homework_slug}
project-score:{course_slug}:{project_slug}
peer-review-assignment:{course_slug}:{project_slug}
certificate-available:{enrollment_id}
deadline-reminder:homework:{homework_id}:24h
deadline-reminder:project:{project_id}:{7d|24h}
deadline-reminder:peer-review:{project_id}:24h
```

---

## 9. Capability gaps (things to raise on the Datamailer side)

Collected from the sections above — what the Target needs that may not exist yet.
Datamailer currently has only a sandbox deployment; none of this implies a
production rollout.

| # | Gap | Needed for | Side |
| --- | --- | --- | --- |
| 1 | **Datamailer owns preferences** — a per-contact, per-category preference **read + write** API with **client-defined category tags**; CMP hosts the settings UI but proxies to it **asynchronously** and stores nothing | Single store, no divergence (§5) | Datamailer + CMP |
| 2 | `peer-review-pending` node *(optional)* — only if a **non-reminder** feature needs to address "who still owes reviews" directly; reminders don't need it (CMP computes the set, §4.10) | Optional targeted addressing | CMP + Datamailer |
| 3 | `certificate-eligible` / `course-graduates` list | Graduate campaigns; list-backed certs | CMP + Datamailer |
| 4 | **Force-send-on-membership** flag (opt-in) | Q1, special-case unified add+send | Datamailer |
| 5 | Campaign API with external key (`PUT /api/campaigns/{key}`, queue, cancel) | CMP-driven broad announcements | Datamailer |
| 6 | Dedicated result / review preference fields | Q3 finer learner control | CMP |
| 7 | Resubscribe → optionally re-enable CMP preference (today: stored only) | Honor re-opt-in | CMP policy + Datamailer metadata |
| 8 | **Upward-cascade membership** — adding a member to a node implies all ancestor nodes up to `<all>` | Generic audience tree (§2); CMP stops maintaining parent levels by hand | Datamailer |
| 9 | **Pure path key scheme** — drop role prefixes (`course-registrants`→`{course}`, `homework-submitters`→`{course}:@e:@homework:{homework}`); add the `{course}:@e` enrolled level and typed item levels | Audience tree (§2) | CMP + Datamailer |
| 10 | **Reliable event emission** — transactional outbox + retry for every membership event, plus removals, so the list never drifts and no per-send reconcile is needed | Event-driven list (§3) | CMP |
| 11 | **Delivery-time category enforcement** — a node send declares its category and Datamailer suppresses contacts opted out of that category | §5 sending | Datamailer |
| 12 | **Bulk import by reference** — accept a fetchable JSONL file (CMP S3 pre-signed URL), ingest asynchronously, expose import-job status to ack before send | Large computed batches & negative audiences (§3, §4.10) | Datamailer |

---

## 10. Unresolved design gaps

Holes in the **design itself** (distinct from the build work in §9). Each needs a
decision before implementation. Ordered roughly by risk; "Lean" is a proposed
resolution, not a commitment.

### Must resolve first

**G1. Removal & reverse-cascade — DECISION: reference-count membership reasons.**
The tree (§2) defines *joining* by adding a leaf and cascading up. Leaving works by
removing the specific reason that put the contact in the node. Datamailer keeps
one visible membership per `(list, contact)`, but internally tracks membership
reasons such as `registration:{id}`, `homework-submission:{id}`, and
`project-submission:{id}`. A membership stays active while at least one reason
remains, and becomes inactive when the last reason is removed.

Removing a parent membership does **not** blindly cascade down. CMP removes the
source reason that changed: deleting a homework submission removes
`homework-submission:{id}` from `{course}:@e:@homework:{homework}` and from its
implicit ancestors; withdrawing a registration removes `registration:{id}` from
`{course}`. If the learner still has a submission reason, they remain in
`{course}:@e` and `{course}`.

**G2. Explicit vs cascade-implied membership at the same node — DECISION: keep
reasons separate.** A contact can reach `{course}` directly by registration and
indirectly by submitting work. The explicit registration reason and implicit
cascade reasons never overwrite each other. List-level metadata is split into:
explicit membership metadata from the source event, and derived rollup metadata
that Datamailer computes from active reasons. Removing a child reason removes only
that reason and its derived contribution; it does not delete the explicit
registration reason.

**G3. Reminders are a *negative* audience — RESOLVED: CMP computes the list.**
Deadline reminders (§4.10) target who has **not** submitted / **still owes** reviews
— a set-difference (`{course}:@e` minus a typed item node) Datamailer can't derive.
**Decision:** CMP computes the set each run and materializes it as a **transient
send-list** via bulk-upsert (inline, or file-by-reference for large batches, gap
#12), triggered by the scheduled CMP job; Datamailer set-difference is **not**
needed. This does **not** violate §3's "no reconcile" — that rule governs the
*durable audience tree*; a reminder list is a separate, send-scoped object CMP
recomputes per run.

**Reminder-list lifecycle — DECISION: stable event key, replace contents.** CMP uses
one stable reminder-list key per reminder event, e.g.
`deadline-reminders:homework:{course}:{homework}:24h`, and replaces that list's
members on each scheduled run before sending. This keeps idempotency stable and
prevents stale recipients. Per-run list keys are useful for audit but create
unbounded list growth, so Datamailer should keep send snapshots/history instead of
creating a new list for every run.

**G4. Email change — DECISION: not supported in CMP.** Learners cannot change their
account email in CMP today. The target does not need an email-change / contact
re-key event for the first Datamailer build. If CMP later allows email changes,
that product change must add a Datamailer contact merge / re-key flow before it
ships.

**G14. Reliable event emission options.** Gap #10 says CMP needs a transactional
outbox + retry, but the exact shape is still open. Options to discuss:

- **DB outbox in CMP, polled by a worker / management command.** CMP writes one
  event row in the same transaction as the local change. A worker claims pending
  rows, sends them to Datamailer with a stable idempotency key, records attempts,
  and leaves failed rows available for retry or manual repair. This is the most
  explicit option and works even if no external queue is available.
- **DB outbox + queue handoff.** CMP still writes the DB outbox transactionally,
  then a dispatcher publishes event ids to SQS / EventBridge. Workers load the row
  and send it to Datamailer. This reduces DB polling and scales better, but adds
  queue operations and still needs the DB outbox as the source of truth.
- **Direct `on_commit` send with periodic repair.** CMP sends to Datamailer after
  commit and relies on a repair command to find missing events. This is simpler,
  but it is too weak if we remove per-send reconcile; a process crash after commit
  can still lose the event.
- **Keep reconcile as a safety audit, not a send step.** CMP can run a scheduled
  drift check or admin-triggered repair that compares CMP source data with
  Datamailer lists and reports or fixes differences. This should not block normal
  sends, but it gives operators a recovery path when an event bug or Datamailer
  incident creates drift.

*Lean:* start with a CMP DB outbox plus a small dispatcher and admin repair view.
Add SQS / EventBridge later if volume or latency requires it. Keep a drift audit
as an operational safety net, but do not put reconcile back into every send.

### Required for §5 and compliance

**G5. Contact lifecycle, consent, preferences, and suppression.** The settings
panel (§5) assumes a contact already exists with sane defaults. Target rules:

- **Contact creation:** CMP creates/upserts a Datamailer contact on course
  registration, account creation when `DATAMAILER_SYNC_ON_USER_CREATE=1`, and the
  first enrollment/submission event if the contact does not already exist.
- **Consent:** course registration remains the explicit newsletter / course email
  consent point. CMP sends `status: subscribed`, `verified: true`, and
  `email_validation.status: externally_validated` only when the CMP flow collected
  that consent.
- **Category preferences:** Datamailer stores per-contact category toggles. CMP
  renders and saves them through the proxy UI. Default category state is `true`
  for consented course contacts unless Datamailer already has a stricter global
  unsubscribe/suppression state.
- **Global unsubscribe and suppression:** global unsubscribe, hard bounce, and
  complaint state override all category toggles. Re-enabling a category does not
  override a global unsubscribe, hard bounce, or complaint suppression.
- **Resubscribe:** a resubscribe can clear a Datamailer global unsubscribe only
  through a Datamailer-controlled re-opt-in flow. CMP stores the callback for
  support, but CMP does not invent consent.

**G6. Account deletion / erasure (GDPR) — target event required.** If a learner
deletes their account or requests erasure, CMP emits a Datamailer erasure event.
Datamailer deletes or anonymizes the contact, memberships, preferences, and message
history according to the retention policy. CMP should treat erasure as stronger
than unsubscribe: the contact should not remain addressable through any audience
node.

### Lower risk

**G7. Score-metadata ↔ send ordering — DECISION: ack before send.** Scoring
(§4.4/§4.8) pushes per-member metadata before sending the node. CMP must wait
until all required metadata writes or import jobs are acknowledged. If any required
metadata write fails, CMP does not trigger the send; the outbox retries or the
operator repairs the failed batch and sends afterward. Datamailer should expose
import/job status and member-write errors clearly enough for CMP to block the send
with a useful operator message.

**G15. Template context and metadata precedence — DECISION.** Datamailer renders a
message from several sources. Precedence from lowest to highest:

1. Datamailer client globals: brand name, support address, footer, optional base
   URL.
2. Contact fields: email, name, country, global/contact-level attributes.
3. Recipient-list metadata: course/item labels that describe the whole list.
4. Member metadata: learner-specific fields such as `submitted_at`, score, review
   links, certificate URL.
5. Send context: values CMP passes for this send, such as announcement title,
   deadline label, scores URL, or campaign-specific copy.

Higher-precedence values win on key conflict. CMP should avoid duplicate key names
where possible, but Datamailer must make the merge deterministic and record the
rendered context or enough debug context for support.

**G16. Operational visibility options.** The target should make event and delivery
health visible before production use. Options to discuss:

- **Minimum viable dashboard:** outbox pending count, oldest pending age, failed
  event count, last successful dispatcher run, and last Datamailer API error.
- **Per-course send summary:** for each send, show intended audience count,
  suppressed count by reason/category, enqueued count, skipped duplicate count, and
  failure count.
- **Drift audit:** scheduled or admin-triggered comparison of CMP source data to
  Datamailer list membership. This reports differences and can optionally repair
  them, but it does not run inside normal sends.
- **Callback health:** webhook success/failure counts, last callback time, and
  duplicate callback count.
- **Import-job health:** for file-by-reference imports, show job state, row count,
  failed rows, content hash, and URL-expiry failures.

*Lean:* build the minimum dashboard plus per-send summaries first. Add drift audit
before relying on event-kept sends for score/results workflows. Add import-job
health when the file-by-reference path is implemented.

**G8. "Enrolled" must be queryable — RESOLVED.** Earlier enrolled was a *derived*
predicate, which Datamailer might not be able to query. Now enrolled is the real
node `{course}:@e`, filled by cascade (§2) — directly addressable, no query needed.
Closed.

**G9. Course family vs cohort.** Nodes are per-cohort (`ml-zoomcamp-2026`); "everyone
who ever did ML Zoomcamp" has no node and falls back to family tags. Document the
tree/tag boundary.

**G10. Volunteer / review-only participants** (reviewers who didn't submit a project)
have no obvious node — decide where they live.

**G11. Category taxonomy.** "Submission confirmation" and "results" share one category,
and peer-review assignment is parked in it (see §7 Q3). Revisit before adding more
result-type emails.

**G12. Reserved synthetic segments — DECISION: `@` prefix.** System-owned path
segments use an `@` prefix: `@e`, `@homework`, `@project`, `@passed`, and
`@graduated` (§2). Real course, homework, project, and campaign slugs must not
start with `@`. Typed item segments also prevent homework/project collisions when
both have the same human slug.

**G13. Email links must be absolute — and tested end to end.** Every link in a
templated email (leaderboard, scores, profile, update URLs) must be a
**fully-qualified URL** (scheme + host). `public_url()` returns a **bare relative
path** when `PUBLIC_BASE_URL` is empty (`course_management/datamailer.py:258`), so a
misconfigured / unset `PUBLIC_BASE_URL` in a sending environment produces broken
links — observed in a real score-notification email as
`http:///llm-zoomcamp-2026/leaderboard` (empty host) instead of
`https://courses.datatalks.club/llm-zoomcamp-2026/leaderboard`.

**Decision: pin the host on exactly one side; never empty; never guessed.** The
link base host is *pinned configuration*, and config is split across two sides (see
[Configuration → Where configuration lives](#where-configuration-lives--two-sides)).
Two valid homes:
- **Datamailer client-global** *(preferred)* — the base host is a stable per-client
  brand value, so make it a **global client variable** on the Datamailer side;
  templates compose `{{ base_url }}/{path}` and CMP sends only paths/slugs. Pinned
  here, an empty host is impossible.
- **CMP-side** — CMP pins `PUBLIC_BASE_URL` (required in any sending environment;
  empty/scheme-only is a **hard error** at send time, not a relative path) and sends
  fully-qualified URLs; Datamailer renders verbatim.

Either way, Datamailer **never *guesses* a host from the request** — it uses a
pinned client-global or the CMP-provided absolute URL. And: an **end-to-end test**
asserting the *rendered* body has absolute `https://<host>/…` links, since today's
tests pin `PUBLIC_BASE_URL` (or set `""`) and only check context — nothing catches
a real environment shipping an empty host. (Reported by Luis Oliveira.)

---

# Part 2 — API reference

The wire-level contract behind Part 1. CMP owns course state and learner
preferences; Datamailer owns templates, sender config, suppression, delivery,
event tracking, and message history.

## Implementation status

The current CMP integration has:

- Datamailer contact sync for new users and enrollments.
- Datamailer homework and project submission confirmation emails.
- Datamailer contact status and history lookups.
- Parallel Datamailer sync for course registrations.
- Datamailer recipient-list member sync for course registrations, course
  enrollments, homework submitters, and project submitters.
- Datamailer recipient-list sends for homework and project score notifications
  and peer-review assignment.
- Datamailer certificate availability emails.
- Datamailer deadline reminder command using recipient-list sends.
- Datamailer callbacks to CMP for hard bounces, complaints, unsubscribes,
  resubscribes, transactional skips, and transactional failures.
- CMP backfill command for Datamailer recipient lists.
- Mailchimp sync for course registrations.

Planned, not implemented yet:

- CMP UI surfacing for stored Datamailer callback events.
- The capability gaps listed in [§9](#9-capability-gaps-things-to-raise-on-the-datamailer-side).

## Configuration

CMP enables Datamailer only when all required settings are present:

```text
DATAMAILER_URL
DATAMAILER_API_KEY
DATAMAILER_CLIENT
DATAMAILER_AUDIENCE
```

CMP may also set:

```text
DATAMAILER_FROM_EMAIL
DATAMAILER_STRICT
DATAMAILER_WEBHOOK_TOKEN
DATAMAILER_SYNC_ON_USER_CREATE
```

`DATAMAILER_FROM_EMAIL` is a Datamailer sender ID, not a raw email address.
Datamailer validates it against the authenticated client sender configuration.

CMP keeps transactional template keys as code-level constants. We don't add one
environment variable per template.

`PUBLIC_BASE_URL` is a CMP URL-building setting, not a Datamailer API setting.
CMP uses it when it builds links for email context.

When `DATAMAILER_STRICT=0`, CMP logs Datamailer failures and lets the course
flow continue. When `DATAMAILER_STRICT=1`, CMP raises the Datamailer API failure
to the caller.

### Where configuration lives — two sides

Configuration for the client is **split across two sides**, and each value should
have **exactly one home**:

- **Datamailer-side — global client variables.** Stable, per-client brand/delivery
  values configured once on the Datamailer side and available to every template for
  that client: sender identity, brand name/logo, legal & unsubscribe footer, support
  address, the subscription **category tags** (§5), and — a strong candidate — the
  **link base host** (so templates compose `{{ base_url }}/{path}` and CMP never
  repeats it). Pinned here, an empty host is impossible.
- **CMP-side — settings + per-send context.** Connection config (`DATAMAILER_URL`,
  `_API_KEY`, `_CLIENT`, `_AUDIENCE`), and the **per-message context** CMP computes:
  course title, slugs, scores, paths. If the base host is *not* a Datamailer
  client-global, then CMP pins `PUBLIC_BASE_URL` and sends fully-qualified URLs.

Rule of thumb: a value that's the same for the whole client → Datamailer global;
a value that varies per course/learner/message → CMP context. The link host is the
boundary case (G13) — pick one side and pin it.

## Generic client model

Datamailer should not hardcode CMP concepts. The API should work for other clients
with different audience trees, categories, templates, and metadata.

Generic Datamailer primitives:

- **Client** — an API tenant with sender config, templates, categories, global
  variables, suppression state, and campaigns.
- **Audience** — a namespace under a client. CMP uses `dtc-courses`; another client
  may use a different audience for a product, newsletter, or event program.
- **Contact** — an email identity scoped to client/audience.
- **Category tag** — a client-defined preference bucket such as
  `submission-results` or `course-updates`.
- **Recipient-list tree** — client-defined path keys. Datamailer understands
  `:`-separated hierarchy and `@` system segments, but not CMP semantics.
- **Membership reason** — a source object that explains why a contact belongs to a
  node.
- **Template / campaign / transactional send** — generic delivery mechanisms that
  receive client-specific context and metadata.

CMP-specific meaning stays outside Datamailer core code. For example,
`ml-zoomcamp-2026:@e:@homework:homework-1` is just a path key to Datamailer; CMP
and CMP-owned templates know it means homework 1 submitters.

## Event schema and outbox

CMP writes Datamailer events to an outbox in the same database transaction as the
local course change. A dispatcher sends those events to Datamailer and records the
result.

Common event envelope:

```json
{
  "event_id": "cmp-datamailer-event:12345",
  "event_type": "recipient_list.member_upsert",
  "idempotency_key": "recipient-list-member:ml-zoomcamp-2026:@e:@homework:homework-1:homework-submission:123",
  "client": "dtc-courses",
  "audience": "dtc-courses",
  "list_key": "ml-zoomcamp-2026:@e:@homework:homework-1",
  "source_object_key": "homework-submission:123",
  "contact": {
    "email": "learner@example.com"
  },
  "metadata": {
    "submission_id": 123,
    "user_id": 55,
    "submitted_at": "2026-06-18T12:00:00Z"
  },
  "ordering_key": "user:55",
  "occurred_at": "2026-06-18T12:00:00Z"
}
```

Target event types:

| Event type | Meaning |
| --- | --- |
| `contact.upsert` | create/update a contact and contact-level fields |
| `contact.erase` | delete/anonymize a contact for erasure |
| `recipient_list.member_upsert` | add or refresh a membership reason |
| `recipient_list.member_remove` | remove a membership reason |
| `recipient_list.members_bulk_upsert` | add/update many membership reasons inline |
| `recipient_list.members_replace` | replace a transient send-list, used for reminders |
| `recipient_list.import_by_reference` | start a JSONL import job |
| `transactional.send` | send one direct transactional email |
| `recipient_list.transactional_send` | send one template to a node/list |
| `campaign.upsert` | create/update a draft or scheduled campaign |
| `campaign.queue` | queue a campaign and snapshot recipients |
| `campaign.cancel` | cancel a draft/scheduled campaign |

Outbox states:

| State | Meaning |
| --- | --- |
| `pending` | event is stored and ready to dispatch |
| `processing` | a dispatcher has claimed it |
| `acked` | Datamailer accepted it, including duplicate-idempotency accept |
| `retrying` | the last attempt failed with a retryable error |
| `failed` | retries are exhausted or the error requires operator action |
| `dead` | operator closed the event without sending it |

Retry policy: retry temporary network/server failures with backoff. Do not retry
validation errors, unknown templates, unknown category tags, or auth failures until
an operator changes config or data. A retry must reuse the same idempotency key.

Ordering: preserve order for events with the same `ordering_key`. CMP should use a
contact/user ordering key for learner events, a list key for list replacement, and
a campaign key for campaign events. Cross-user events can run in parallel.

Membership idempotency: a duplicate member upsert with the same
`source_object_key` updates that reason's metadata. A duplicate remove leaves the
reason inactive. Upsert after remove reactivates the reason with the new metadata.

## API error contract

Datamailer should return structured errors so CMP can decide whether to retry,
surface an operator message, or fail fast in strict mode.

```json
{
  "error": {
    "code": "unknown_template",
    "message": "Template homework-score-notification does not exist",
    "retryable": false,
    "details": {
      "template_key": "homework-score-notification"
    }
  }
}
```

Core error codes:

| Code | Retryable | Typical CMP action |
| --- | --- | --- |
| `unauthorized` | no | fail config check; operator fixes API key |
| `forbidden_client` | no | fail config check; operator fixes client/audience |
| `validation_error` | no | mark event failed with field errors |
| `unknown_template` | no | block send until template exists |
| `unknown_category` | no | block send until category config exists |
| `unknown_sender` | no | block send until sender config exists |
| `duplicate_idempotency_key` | no | treat as accepted if response includes existing object |
| `contact_suppressed` | no | store skip/suppression result; do not retry |
| `temporary_unavailable` | yes | retry with backoff |
| `import_failed` | depends | retry if fetch/temporary; operator repair if row validation failed |

## Contact sync

CMP syncs contacts when it creates users, enrollments, and course registrations
(conceptually §4.1–4.2). During rollout, CMP keeps the existing Mailchimp sync
and also upserts the registrant into Datamailer.

```text
POST /api/contacts
Authorization: Bearer <DATAMAILER_API_KEY>
```

```json
{
  "email": "learner@example.com",
  "audience": "dtc-courses",
  "client": "dtc-courses",
  "status": "subscribed",
  "verified": true,
  "email_validation": {
    "status": "externally_validated"
  },
  "tags": [
    "course-ml-zoomcamp",
    "course-cohort-ml-zoomcamp-2026"
  ]
}
```

CMP sends `status: subscribed`, `verified: true`, and
`email_validation.status: externally_validated` for course-scoped contacts. The
registration form requires newsletter consent, so CMP marks the contact verified
and externally validated. Course-scoped tags include both the family tag and
cohort tag, e.g. `course-ml-zoomcamp` and `course-cohort-ml-zoomcamp-2026`.

## Transactional sends

CMP uses Datamailer transactional email for several learner-specific events.
They call the same endpoints but trigger from different parts of the lifecycle
(see Part 1, §4).

| Trigger | Email | CMP owner | Status |
| --- | --- | --- | --- |
| Learner submits work | homework submission confirmation | homework submit view | implemented |
| Learner submits work | project submission confirmation | project submit view | implemented |
| Operator publishes results | homework score notification | cadmin homework scoring | implemented |
| Operator assigns peer reviews | peer-review assignment | cadmin project action | implemented |
| Operator publishes results | project score notification | cadmin project scoring | implemented |
| Operator publishes certificates | certificate availability | certificate bulk/API flow | implemented |
| Scheduled command runs | deadline reminders | `send_deadline_reminders` | implemented |

Single-recipient sends (submission confirmations, certificates):

```text
POST /api/transactional/send
Authorization: Bearer <DATAMAILER_API_KEY>
```

```json
{
  "email": "learner@example.com",
  "template_key": "homework-submission-confirmation",
  "category_tag": "submission-results",
  "from_email": "courses",
  "idempotency_key": "homework-submission:123:2026-06-18T10:00:00+00:00",
  "context": {
    "course_slug": "ml-zoomcamp",
    "course_title": "Machine Learning Zoomcamp",
    "homework_slug": "homework-1",
    "homework_title": "Homework 1",
    "update_url": "https://courses.datatalks.club/course/homework/homework-1",
    "profile_url": "https://courses.datatalks.club/accounts/settings/"
  },
  "metadata": {
    "source": "course-management-platform",
    "event": "homework_submission",
    "course_slug": "ml-zoomcamp",
    "homework_slug": "homework-1",
    "submission_id": 123
  }
}
```

List sends (score publication, peer-review assignment, deadline reminders) carry
only the list key, template, category, and send context. They do **not** carry a
member snapshot. For score publication and peer-review assignment, CMP first
pushes computed metadata to the node and waits for Datamailer to ack it. For
deadline reminders, CMP first replaces the transient reminder list with the
current computed audience. The send then names the node or transient list:

```text
POST /api/recipient-lists/{list_key}/transactional-send
Authorization: Bearer <DATAMAILER_API_KEY>
```

```json
{
  "audience": "dtc-courses",
  "client": "dtc-courses",
  "template_key": "homework-score-notification",
  "category_tag": "submission-results",
  "idempotency_key": "homework-score:ml-zoomcamp-2026:homework-1",
  "context": {
    "course_title": "Machine Learning Zoomcamp",
    "homework_title": "Homework 1",
    "scores_url": "https://courses.datatalks.club/ml-zoomcamp-2026/"
  },
  "metadata": {
    "source": "course-management-platform",
    "event": "homework_score_publication",
    "course_slug": "ml-zoomcamp-2026",
    "homework_slug": "homework-1"
  }
}
```

Datamailer snapshots active members at send time, applies category preferences and
deliverability suppression, then creates one transactional message per deliverable
member. It merges context deterministically using the precedence in G15. CMP
remains the source of truth for scores. If the same `idempotency_key` is sent
again for the same client, Datamailer returns the existing send and does not
enqueue duplicate email.

```mermaid
sequenceDiagram
    participant CMP
    participant DM as Datamailer API
    participant DB as Datamailer DB
    participant SQS
    participant Worker
    participant SES

    CMP->>DM: POST transactional or recipient-list send
    DM->>DB: Validate template and idempotency key
    alt Existing idempotency key
        DM-->>CMP: Existing message, enqueued=false
    else New send
        DM->>DB: Create contact, message, queued event
        DM->>SQS: Enqueue transactional-email job
        DM-->>CMP: New message, enqueued=true
        SQS->>Worker: transactional-email job
        Worker->>SES: Send email
        Worker->>DB: Mark sent or failed
    end
```

## Template contract

Every Datamailer template used by CMP should have an explicit contract: required
category tag, required send context, required member metadata, and link fields. CMP
tests should verify that it supplies those fields, and Datamailer should validate
required fields before queueing a send.

| Template key | Category tag | Required send context | Required member/contact context |
| --- | --- | --- | --- |
| `homework-submission-confirmation` | `submission-results` | `course_title`, `homework_title`, `update_url`, `profile_url` | contact email |
| `project-submission-confirmation` | `submission-results` | `course_title`, `project_title`, `update_url`, `profile_url` | contact email |
| `homework-score-notification` | `submission-results` | `course_title`, `homework_title`, `scores_url` | score fields from member metadata |
| `project-score-notification` | `submission-results` | `course_title`, `project_title`, `scores_url` | project score / pass fields from member metadata |
| `peer-review-assignment` | `submission-results` | `course_title`, `project_title`, `review_deadline` | assigned review links from member metadata |
| `certificate-availability` | `course-updates` | `course_title`, `profile_url` | `certificate_url` |
| `deadline-reminder-homework` | `deadline-reminders` | `course_title`, `homework_title`, `deadline`, `submission_url` | contact email |
| `deadline-reminder-project` | `deadline-reminders` | `course_title`, `project_title`, `deadline`, `submission_url` | contact email |
| `deadline-reminder-peer-review` | `deadline-reminders` | `course_title`, `project_title`, `review_deadline` | unfinished review links from member metadata |

Rules:

- Every URL rendered in an email must be absolute unless the template composes it
  from a pinned Datamailer client-global base URL.
- Datamailer should reject a send before queueing if required fields are missing.
- Datamailer should expose a preview/test-send path for operators, using explicit
  sample context rather than production learners.
- CMP should keep template keys as code constants, not environment variables.

## Render testbed

Datamailer should provide a testbed where CMP developers send the **same API
request to the same endpoint** CMP would normally use, but mark it as render-only.
Datamailer runs the same production code path, stores the generated result, and
returns a `testbed_run_id` instead of enqueueing delivery. A developer then fetches
that run to inspect the generated subject, text, HTML, merged context, link
diagnostics, validation result, and delivery/suppression decision.

This is not a separate renderer or mock pipeline: it uses the real template lookup,
context merge, required-field validation, category checks, suppression checks, and
render code. The only disabled step is enqueueing or handing the message to the
delivery provider.

There are two entry modes:

- **Per-request render-only mode:** send the normal Datamailer API request with
  `X-Datamailer-Mode: render-only`.
- **Environment-level capture mode:** run Datamailer in a local/sandbox mode where
  every normal send request is captured and rendered, but no email is delivered.
  CMP does not need special testbed code in this mode; it points at Datamailer and
  behaves normally.

Use cases:

- Verify what a transactional request would render before wiring it into CMP.
- Debug missing template fields, bad links, wrong metadata precedence, or category
  selection.
- Test category preferences and unsubscribe behavior: send a request for someone
  opted out of that category and confirm Datamailer returns `would_send: false`
  with the expected suppression reason.
- Test global unsubscribe and deliverability suppression without sending email to
  the suppressed contact.
- Verify absolute links in both text and HTML output, including leaderboard, score,
  profile, update, review, certificate, and unsubscribe/preferences links.
- Inspect one representative recipient from a node send without emailing the whole
  node.
- Save fixtures for template contract tests.

### Local E2E capture mode

The main CMP testing workflow should be end-to-end:

1. Run CMP and Datamailer together, for example with Docker Compose.
2. Configure CMP with normal Datamailer settings:
   `DATAMAILER_URL`, `DATAMAILER_API_KEY`, `DATAMAILER_CLIENT`,
   `DATAMAILER_AUDIENCE`, and `DATAMAILER_FROM_EMAIL`.
3. Configure Datamailer itself with delivery disabled and capture enabled.
4. Use CMP normally: register, submit homework, publish scores, assign peer
   reviews, run deadline reminders, publish certificates, or queue announcements.
5. Inspect captured Datamailer runs through an API or UI.

Example compose-style environment:

```text
CMP:
  DATAMAILER_URL=http://datamailer:8000
  DATAMAILER_API_KEY=dev-token
  DATAMAILER_CLIENT=dtc-courses
  DATAMAILER_AUDIENCE=dtc-courses
  DATAMAILER_FROM_EMAIL=courses

Datamailer:
  DATAMAILER_DELIVERY_MODE=capture
  DATAMAILER_CAPTURE_UI=1
```

In capture mode, CMP sends the exact same requests it would send in a real
environment. Datamailer stores each rendered message and returns normal API
responses to CMP, but marks the message as captured rather than queued for
provider delivery.

For local E2E capture, the only intended difference is Datamailer configuration:
set Datamailer's delivery mode to `capture`. CMP code, CMP endpoints, and CMP
payloads stay unchanged. CMP should not branch on "testbed mode"; it should behave
as if it were talking to a normal Datamailer deployment.

Capture inspection API:

```text
GET /api/testbed/runs
GET /api/testbed/runs?source=course-management-platform&event=homework_submission
GET /api/testbed/runs/{testbed_run_id}
GET /api/testbed/runs/{testbed_run_id}/messages/{message_id}
DELETE /api/testbed/runs
```

The UI should support the same basic workflow: list captured runs, filter by
email/template/course/event, open a message, switch between text and HTML, inspect
merged context, check suppression reasons, and inspect link diagnostics.

Normal send endpoints, testbed mode:

```text
POST /api/transactional/send
POST /api/recipient-lists/{list_key}/transactional-send
POST /api/campaigns/{external_key}/queue
X-Datamailer-Mode: render-only
```

The request body is the same as the normal production request. The only difference
is the render-only header. Datamailer should also accept an equivalent query
parameter for manual cURL/browser testing, e.g. `?mode=render-only`.

Retrieval endpoints:

```text
GET /api/testbed/runs/{testbed_run_id}
GET /api/testbed/runs/{testbed_run_id}/messages/{message_id}
```

Example direct-send testbed request:

```text
POST /api/transactional/send
X-Datamailer-Mode: render-only
```

```json
{
  "client": "dtc-courses",
  "audience": "dtc-courses",
  "email": "learner@example.com",
  "template_key": "homework-submission-confirmation",
  "category_tag": "submission-results",
  "context": {
    "course_title": "Machine Learning Zoomcamp",
    "homework_title": "Homework 1",
    "update_url": "https://courses.datatalks.club/course/homework/homework-1",
    "profile_url": "https://courses.datatalks.club/accounts/settings/"
  },
  "metadata": {
    "source": "course-management-platform",
    "event": "homework_submission",
    "submission_id": 123
  }
}
```

Immediate response:

```json
{
  "mode": "render-only",
  "testbed_run_id": "testbed-run:abc123",
  "delivery_enqueued": false,
  "result_url": "/api/testbed/runs/testbed-run:abc123"
}
```

Example retrieved run:

```json
{
  "testbed_run_id": "testbed-run:abc123",
  "source_endpoint": "POST /api/transactional/send",
  "template_key": "homework-submission-confirmation",
  "category_tag": "submission-results",
  "messages": [
    {
      "message_id": "testbed-message:1",
      "email": "learner@example.com",
      "subject": "Homework 1 submitted",
      "text": "Your Homework 1 submission for Machine Learning Zoomcamp was recorded...",
      "html": "<p>Your Homework 1 submission for Machine Learning Zoomcamp was recorded...</p>",
      "merged_context": {
        "course_title": "Machine Learning Zoomcamp",
        "homework_title": "Homework 1",
        "update_url": "https://courses.datatalks.club/course/homework/homework-1",
        "profile_url": "https://courses.datatalks.club/accounts/settings/"
      },
      "validation": {
        "ok": true,
        "missing_fields": [],
        "warnings": []
      },
      "delivery_decision": {
        "would_send": true,
        "suppressed": false,
        "reasons": []
      },
      "links": {
        "absolute": true,
        "urls": [
          "https://courses.datatalks.club/course/homework/homework-1",
          "https://courses.datatalks.club/accounts/settings/"
        ],
        "warnings": []
      }
    }
  ]
}
```

Rules:

- Render-only mode never enqueues email and never hands email to SES/provider
  delivery.
- It uses the same production code path as real sends through the final rendered
  message. Any difference between testbed rendering and production rendering is a
  bug.
- It may create a non-delivery audit/testbed record, but must not create a normal
  transactional message that can be retried or delivered later.
- For node/list renders, the request may either pick one `source_object_key` or
  pass explicit sample member metadata. Datamailer should not render every member
  by default.
- The response should include both `text` and `html`, even when one is generated
  from the other.
- The response should expose **why** Datamailer would or would not send:
  category opt-out, global unsubscribe, hard bounce, complaint, unknown contact,
  missing required context, or template/category validation error.
- The response should include link diagnostics: all URLs found in `text` and
  `html`, whether each is absolute, and warnings for empty hosts, `localhost`,
  unsupported schemes, or missing unsubscribe/preferences links where required.
- Testbed requests should be auditable but should not pollute normal message
  history or idempotency state.

Suppression test examples:

```json
{
  "email": "learner@example.com",
  "category_tag": "deadline-reminders",
  "delivery_decision": {
    "would_send": false,
    "suppressed": true,
    "reasons": [
      {
        "code": "category_opted_out",
        "category_tag": "deadline-reminders"
      }
    ]
  }
}
```

```json
{
  "email": "learner@example.com",
  "category_tag": "course-updates",
  "delivery_decision": {
    "would_send": false,
    "suppressed": true,
    "reasons": [
      {
        "code": "global_unsubscribed"
      }
    ]
  }
}
```

## Preferences API

Datamailer owns category preferences. CMP hosts the settings page and proxies reads
and writes to Datamailer; CMP does not store preference booleans in the target.

```text
GET /api/contacts/preferences?email=<email>&audience=<audience>&client=<client>
PUT /api/contacts/preferences?email=<email>&audience=<audience>&client=<client>
```

```json
{
  "categories": [
    {
      "tag": "submission-results",
      "label": "Homework and project submissions",
      "enabled": true
    },
    {
      "tag": "deadline-reminders",
      "label": "Deadline reminders",
      "enabled": true
    },
    {
      "tag": "course-updates",
      "label": "General course-related emails",
      "enabled": true
    }
  ],
  "global_unsubscribed": false,
  "suppressed": false
}
```

The write endpoint accepts the same category tags with updated `enabled` values.
Datamailer rejects writes that would bypass global unsubscribe, hard-bounce, or
complaint suppression. Category tags are client-defined Datamailer config, not CMP
database fields.

## Recipient lists

Datamailer has native recipient lists rather than using tags as lists. Tags are
audience-scoped and broad; recipient lists have client and audience scope,
membership audit, bootstrap/repair support, and send-specific counters. List keys
do not need a `cmp:` prefix because the authenticated API client already scopes
ownership. (Key scheme: Part 1, §8.)

Datamailer tables:

```text
recipient_lists
- client, audience, key, type, name, metadata
- member_count, active_member_count, last_replaced_at
- created_at, updated_at

recipient_list_members
- recipient_list, contact, email, metadata
- active, removed_at, created_at, updated_at

recipient_list_member_reasons
- recipient_list_member, source_object_key, metadata
- active, removed_at, created_at, updated_at
```

Required uniqueness:

```text
(client, audience, key)
(recipient_list, contact)
(recipient_list_member, source_object_key)
```

CMP maintains registration, enrolled, homework-submitter, project-submitter, and
outcome nodes after local commits. The first member upsert creates the parent list
if it does not exist, so CMP never checks before adding a member. Adding a leaf
also creates or refreshes active membership reasons on every ancestor node.

```text
PUT  /api/recipient-lists/{key}
PUT  /api/recipient-lists/{key}/members/{source_object_key}
DELETE /api/recipient-lists/{key}/members/{source_object_key}
POST /api/recipient-lists/{key}/members/bulk-upsert
POST /api/recipient-lists/{key}/members/replace
POST /api/recipient-lists/{key}/imports
GET  /api/recipient-lists/{key}/imports/{job_id}
GET  /api/recipient-lists/{key}
```

Example first homework submit:

```text
PUT /api/recipient-lists/ml-zoomcamp-2026:@e:@homework:homework-1/members/homework-submission:123
```

```json
{
  "audience": "dtc-courses",
  "client": "dtc-courses",
  "list": {
    "type": "homework_submitters",
    "name": "ML Zoomcamp 2026 Homework 1 submitters",
    "metadata": { "course_slug": "ml-zoomcamp-2026", "homework_slug": "homework-1" }
  },
  "member": {
    "email": "learner@example.com",
    "status": "active",
    "metadata": { "submission_id": 123, "user_id": 55, "submitted_at": "2026-06-18T12:00:00Z" }
  }
}
```

The `members/replace` endpoint is only for transient send lists such as deadline
reminders. It replaces that list's active members with the current CMP-computed
set and records the previous contents in send/list history for support. Durable
audience-tree nodes use event upserts/removals, not replace.

The `imports` endpoints support file-by-reference bulk upserts for large batches:
CMP uploads JSONL to its own S3, sends a pre-signed URL to Datamailer, then waits
for the import job to ack before sending.

CMP exposes a backfill command for the initial greenfield bootstrap or operator
repair — never as part of normal sends:

```console
$ uv run python manage.py sync_datamailer_recipient_lists registrations --course-slug ml-zoomcamp-2026
$ uv run python manage.py sync_datamailer_recipient_lists enrollments --course-slug ml-zoomcamp-2026
$ uv run python manage.py sync_datamailer_recipient_lists homework --course-slug ml-zoomcamp-2026 --homework-slug homework-1
$ uv run python manage.py sync_datamailer_recipient_lists project --course-slug ml-zoomcamp-2026 --project-slug midterm-project
$ uv run python manage.py sync_datamailer_recipient_lists homework --course-slug ml-zoomcamp-2026 --reconcile
$ uv run python manage.py sync_datamailer_recipient_lists registrations --dry-run
```

For large lists, CMP can use Datamailer's file-by-reference import jobs instead
of sending members inline:

```console
DATAMAILER_IMPORT_S3_BUCKET=cmp-datamailer-imports \
  uv run python manage.py sync_datamailer_recipient_lists registrations \
    --course-slug ml-zoomcamp-2026 \
    --import-by-reference \
    --wait-for-import
```

The command writes JSONL to CMP-owned S3, creates a short-lived pre-signed URL,
and sends Datamailer a stable import idempotency key. `--reconcile` maps to
Datamailer's `remove_absent` import flag and is for bootstrap or operator repair,
not normal sends.

## Idempotency keys

CMP sends stable idempotency keys for every transactional email. The key
identifies the event, not the command run. (Full list: Part 1, §8.) For
recipient-list sends, CMP sends the base event key and Datamailer appends each
member's `source_object_key` when creating that learner's idempotency key.

Deadline-reminder keys deliberately omit the command timestamp, so the command
can run repeatedly without duplicating. If a moved deadline should allow a second
reminder, CMP can add the deadline timestamp to the key
(`deadline-reminder:homework:{id}:24h:{deadline_iso}`) — a deliberate change,
since it sends a second reminder after each deadline edit.

## Deadline reminders

CMP owns scheduling because Datamailer doesn't know CMP course state: who is
enrolled, has submitted, or has unfinished peer reviews (conceptually §4.10).
Datamailer applies opt-out and deliverability suppression at send time. The command:

```console
$ uv run python manage.py send_deadline_reminders
```

For deployed environments, EventBridge runs a one-off ECS task with the CMP
image (command overridden to `python manage.py send_deadline_reminders`),
provisioned via Terraform in `DataTalksClub/infra-terraform` alongside the CMP
ECS service. The rule assumes an invocation role that trusts EventBridge and may
call `ecs:RunTask` for the CMP task definition plus `iam:PassRole`. CMP itself
does not configure the schedule. The command replaces each transient reminder
list with the current CMP-computed audience, triggers one list send per reminder
event, then exits.

## Broad course emails

Broad announcements — including new course launches and new cohort announcements
— should use Datamailer campaigns, not a CMP loop over transactional sends. CMP
syncs contact tags for coarse filtering:

```text
course-{course_slug}
course-cohort-{course_cohort_slug}
pref-submission-confirmations
pref-deadline-reminders
pref-course-updates
pref-results-notifications
```

CMP should not use tags as the canonical source for submitter or registrant
lists — use recipient lists for those. Datamailer currently supports campaign
creation through the operator UI. The target adds a campaign API with an external
key (gap #5):

```text
PUT  /api/campaigns/{external_key}
POST /api/campaigns/{external_key}/queue
POST /api/campaigns/{external_key}/cancel
POST /api/campaigns/{external_key}/preview
POST /api/campaigns/{external_key}/test-send
```

Campaign target contract:

- `PUT` creates or updates only `draft` or `scheduled` campaigns. It rejects
  `queued`, `sending`, `sent`, and `cancelled` campaigns.
- The payload declares `category_tag`, recipient source (`<all>`, a recipient-list
  key, or tag filters), subject, template/content reference, send context, and
  schedule time.
- Schedule times must include timezone or be UTC. CMP should pass UTC plus the
  course display timezone if the email mentions local time.
- Datamailer snapshots recipients only when the campaign is queued, not when CMP
  creates the draft. This keeps preferences, suppression, tags, and list
  membership current until queue time.
- `queue` is idempotent for the same external key. It returns recipient counts:
  snapshot count, suppressed count by reason/category, and enqueued count.
- `cancel` works only for `draft`, `scheduled`, or `queued` campaigns that have not
  started sending. Sent messages are not recalled.
- `preview` renders the campaign with supplied sample context and no recipients.
- `test-send` sends the rendered campaign to explicit operator/test addresses and
  never snapshots the production audience.

## Status lookups

CMP can read contact status and email history for support and debugging:

```text
GET /api/contacts/status?email=<email>&audience=<audience>&client=<client>
GET /api/contacts/{contact_id}/history?audience=<audience>&client=<client>
GET /api/transactional/messages/{message_id}
```

CMP should not use status lookups to decide routine sends — Datamailer applies
hard-bounce and complaint suppression when CMP calls the send endpoint.

## Admin and operator UX

CMP operators need enough Datamailer status in cadmin to know whether a send is
ready, queued, delivered to Datamailer, or blocked.

Target cadmin surfaces:

- **Outbox page:** pending/retrying/failed Datamailer events, oldest pending event,
  last attempt, next retry time, error code/message, and a retry/mark-dead action.
- **Send summary:** for each score publication, peer-review assignment, certificate
  batch, reminder, or campaign: intended audience count, suppressed count by
  category/deliverability, enqueued count, duplicate-idempotency count, and failed
  count.
- **Import status:** for large metadata batches and reminder lists: job state, row
  count, failed rows, and whether the send is blocked waiting for import ack.
- **Learner support view:** contact status, category preferences, recent messages,
  callback events, suppression state, and Datamailer message ids.
- **Template preview/test:** render a template or campaign with sample context and
  optionally send it to operator/test addresses.
- **Production-path testbed:** paste or replay a CMP send payload, run it through
  the real Datamailer render pipeline without delivery, and inspect subject, text,
  HTML, merged context, validation, unsubscribe/category suppression decisions, and
  link diagnostics.

Datamailer should return stable ids and status URLs/message ids where possible so
CMP can link operator screens to Datamailer support detail.

## Callbacks

Datamailer calls CMP for contact events CMP needs to surface or map back to
preferences (conceptually §5):

```text
POST /api/datamailer/events
Authorization: Bearer <DATAMAILER_WEBHOOK_TOKEN>
```

CMP stores each callback in `data_datamailercontactevent` keyed by Datamailer's
stable `event_id`, so repeated callbacks are idempotent. On the Datamailer side
callbacks sit in a `cmp_callbacks` outbox and a dispatcher posts them with retry
and backoff.

Implemented event types:

```text
contact.hard_bounced
contact.complained
subscription.unsubscribed
subscription.resubscribed
transactional.skipped
transactional.failed
```

Hard bounces and complaints are deliverability state; skipped/failed are delivery
audit state — CMP stores them for support. For `subscription.unsubscribed`, CMP
updates a preference only when the callback carries a recognized `preference_key`
(`email_submission_confirmations`, `email_deadline_reminders`,
`email_course_updates`). Resubscribe events are stored but do **not**
auto-re-enable a CMP preference (gap #7).

```json
{
  "event_id": "datamailer-email-event:123",
  "event_type": "subscription.unsubscribed",
  "email": "learner@example.com",
  "occurred_at": "2026-06-18T10:00:00Z",
  "audience": "dtc-courses",
  "client": "dtc-courses",
  "preference_key": "email_course_updates",
  "metadata": { "scope": "client" }
}
```

## Failure handling

CMP writes Datamailer work to the outbox after local DB commits, so it never emails
for rolled-back course changes. When Datamailer is unconfigured, CMP skips
Datamailer work. In strict environments, missing Datamailer configuration or
non-retryable Datamailer errors should fail tests and operator actions quickly.

Datamailer returns existing objects for duplicate idempotency keys, so CMP can
safely retry failed HTTP requests with the same key. List membership maintenance is
stricter than best-effort confirmation emails: if a membership update, metadata
batch, or import job fails, CMP must not trigger dependent score/result sends until
the outbox retries or an operator repairs the failed event. Drift audit and
operator repair are the recovery path; normal sends do not perform reconcile.

## Security

Target security rules:

- CMP authenticates to Datamailer with a server-side API key. The browser never
  receives a Datamailer token.
- Datamailer webhook calls to CMP should use a shared webhook secret or signed
  payload. CMP must verify the source before storing or acting on callbacks.
- Webhook delivery should include a stable `event_id` and timestamp so CMP can
  deduplicate callbacks.
- Pre-signed JSONL import URLs should be short-lived, HTTPS-only, and scoped to one
  object. Datamailer should record the content hash and row count it imported.
- Import files contain learner PII. CMP owns the bucket and should expire import
  objects after Datamailer acks the job or after a short retention window for
  failed jobs.
- API keys and webhook secrets need rotation without code changes.

## Data retention

Retention should support learner privacy, debugging, and delivery audit without
keeping more rendered personal data than needed.

Suggested target:

- **Contacts and preferences:** retained while the contact exists; erased or
  anonymized on erasure request.
- **Membership reasons:** retained while active; inactive reasons retained long
  enough for support/audit, then pruned or anonymized.
- **Outbox events:** keep acked events for operational audit, failed/dead events
  until an operator resolves them, then prune on a fixed schedule.
- **Rendered message context:** keep minimal debug context and message ids; avoid
  storing full rendered bodies indefinitely.
- **Callbacks:** keep enough to support bounce/complaint/unsubscribe debugging and
  deduplication.
- **Import files:** expire from CMP S3 after successful import; retain failed
  imports only long enough for operator diagnosis.

## Testing plan

Target tests before relying on the integration:

- **CMP unit tests:** event creation on registration, submission, scoring,
  certificate publication, preference proxy calls, erasure, and reminder
  computation.
- **Outbox tests:** retryable vs non-retryable failures, idempotency key reuse,
  ordering by `ordering_key`, and operator retry/mark-dead actions.
- **Datamailer contract tests:** contact upsert, preference read/write, membership
  reason upsert/remove, cascade behavior, transient list replace, import job ack,
  and node send.
- **Template contract tests:** each CMP template receives all required fields and
  rendered links are absolute.
- **Render testbed tests:** the testbed and real send path produce the same subject,
  text, HTML, merged context, validation result, category/global-unsubscribe
  suppression decision, and link diagnostics for the same request, while the
  testbed never enqueues provider delivery.
- **Local E2E capture tests:** run CMP and Datamailer together, e.g. with Docker
  Compose, with Datamailer in capture mode. Use CMP normally to register, submit,
  publish scores, assign peer reviews, send deadline reminders, publish
  certificates, and create/queue/cancel a campaign. Assert on captured text/HTML,
  suppression decisions, and links.
- **Drift audit tests:** intentionally remove or alter a Datamailer membership and
  verify the audit reports or repairs the difference.
