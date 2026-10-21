"""Seed Production AI: Agents + Generative Media (Nebius/Mikhail).

Registration-wall course: access only via questionnaire + manual
approval. Idempotent (get_or_create on slugs); reverse is a no-op.
"""

from django.db import migrations


COURSE_SLUG = "production-ai-agents-generative-media"
CAMPAIGN_SLUG = "production-ai-agents-generative-media"

COURSE_TITLE = "Production AI: Agents + Generative Media"

COURSE_DESCRIPTION = (
    "How do you build a production AI system when an agent can launch "
    "expensive, slow, failure-prone GPU workloads that produce large "
    "media artifacts? Outcome: build, deploy, evaluate, optimize and "
    "monitor a production AI system in which agents orchestrate "
    "GPU-powered image, video and audio models. "
    "4 weeks, ~8-10 h/week, free, open-source, project-based."
)

CAMPAIGN_MARKETING = """\
## Production AI: Agents + Generative Media

4 weeks · ~8–10 h/week · free · open-source · project-based

> How do you build a production AI system when an agent can launch expensive, slow, failure-prone GPU workloads that produce large media artifacts?

Outcome: build, deploy, evaluate, optimize and monitor a production AI system in which agents orchestrate GPU-powered image, video and audio models.

**Program**

- Week 1 — Make it work: generative media workloads, containers, GPU engineering lab, jobs vs endpoints
- Week 2 — Make it intelligent: agents that use GPUs, tools, async long-running jobs
- Week 3 — Make it scale
- Week 4 — Make it production-ready

**Who**

- ML / MLOps / data engineers adding image, video or audio generation to real systems
- Backend engineers turning a ComfyUI / notebook prototype into a service with SLOs and a cost line
- Founders / small teams paying per-call media APIs, asking when self-hosting wins

**Prerequisites:** Python, Docker basics, HTTP APIs, command line. No diffusion theory required. Prior LLM or MLOps course experience helps, not required.

**Application only — limited seats, medium–advanced level.** Fill in the questionnaire below. Acceptance is not automatic: we review every application and approve targeted applicants. Without approval you can still audit the public materials, but you cannot take the gated course path (homework, projects).
"""


def seed_production_ai(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    RegistrationCampaign = apps.get_model("courses", "RegistrationCampaign")

    course, _ = Course.objects.get_or_create(
        slug=COURSE_SLUG,
        defaults={
            "title": COURSE_TITLE,
            "description": COURSE_DESCRIPTION,
            "requires_registration_approval": True,
            "visible": True,
        },
    )
    if not course.requires_registration_approval:
        course.requires_registration_approval = True
        course.save(update_fields=["requires_registration_approval"])

    RegistrationCampaign.objects.get_or_create(
        slug=CAMPAIGN_SLUG,
        defaults={
            "title": COURSE_TITLE,
            "edition_label": "First cohort",
            "current_course": course,
            "is_active": True,
            "marketing_markdown": CAMPAIGN_MARKETING,
        },
    )


def unseed_production_ai(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0046_course_requires_registration_approval_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_production_ai, unseed_production_ai),
    ]
