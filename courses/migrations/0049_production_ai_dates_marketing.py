"""Refresh Production AI campaign marketing with 2026 cohort dates (t658u)."""

from django.db import migrations

SLUG = "production-ai-agents-generative-media"

MARKETING = """## Production AI Agents for Generative Media

4 weeks over 5 calendar weeks (Module 1 is two weeks) · ~8-10 h/week · free · open-source · project-based.

> How do you build a production AI system when an agent can launch expensive, slow, failure-prone GPU workloads that produce large media artifacts?

Outcome: build, deploy, evaluate, optimize and monitor a production AI system in which agents orchestrate GPU-powered image, video and audio models on Nebius Serverless AI.

### Dates (2026 cohort)

- Welcome: Tue 10 Nov 2026
- Course starts: Mon 17 Nov 2026
- Apply by: Wed 26 Nov 2026
- Module 1 (two weeks): 17-30 Nov 2026 (through Sun 30 Nov)
- Module 2: 1-7 Dec 2026
- Module 3: 8-14 Dec 2026
- Module 4: 15-21 Dec 2026
- Course ends: Sun 21 Dec 2026
- Capstone due: Fri 15 Jan 2027

### Program

- **Week 1 - Make it work.** Generative media workloads: modalities and model families, first GPU generation from script to container to GPU job, containers for generative AI, GPU engineering, jobs vs endpoints.
- **Week 2 - Make it intelligent.** Agents that use GPUs: the agent loop, tools and structured outputs, CPU agents with GPU tools, long-running tools.
- **Week 3 - Make it scale.** Scaling, reliability and cost.
- **Week 4 - Make it production-ready.** Evaluation, observability and production.

### Who this is for

- ML / MLOps / data engineers adding image, video or audio generation to real systems.
- Backend engineers turning a prototype into a service with SLOs and a cost line.
- Founders and small teams deciding when self-hosting beats per-call media APIs.

### Prerequisites

Python, Docker basics, HTTP APIs, command line. No diffusion theory required. Prior LLM or MLOps course experience helps, not required.

Application only, limited seats.
"""

NOTICE = (
    "4 weeks over 5 calendar weeks (~8-10 h/week), free and open-source. "
    "Welcome 10 Nov 2026 · starts 17 Nov 2026 · apply by 26 Nov 2026 · ends 21 Dec 2026 · capstone due 15 Jan 2027. "
    "Prerequisites: Python, Docker basics, HTTP APIs, command line. "
    "Only applicants whose background fits the medium-advanced level are approved."
)

META = (
    "Production AI Agents for Generative Media - free project-based course on production GPU media systems. "
    "Welcome 10 Nov 2026, starts 17 Nov, apply by 26 Nov, ends 21 Dec, capstone 15 Jan 2027. Limited seats, application only."
)

TITLE = "Production AI Agents for Generative Media"


def forwards(apps, schema_editor):
    RegistrationCampaign = apps.get_model("courses", "RegistrationCampaign")
    Course = apps.get_model("courses", "Course")
    c = RegistrationCampaign.objects.filter(slug=SLUG).first()
    if c:
        c.title = TITLE
        c.marketing_markdown = MARKETING
        if hasattr(c, "meta_description"):
            c.meta_description = META
        if hasattr(c, "application_notice"):
            c.application_notice = NOTICE
        c.save()
    course = Course.objects.filter(slug=SLUG).first()
    if course:
        course.title = TITLE
        course.save(update_fields=["title"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0048_courseregistration_accepted_nebius_sharing_and_more"),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
