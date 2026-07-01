def date_to_iso(value):
    if value is None:
        return None
    return value.isoformat()


def course_to_dict(course):
    return {
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "start_date": date_to_iso(course.start_date),
        "end_date": date_to_iso(course.end_date),
        "registration_url": course.registration_url,
        "github_repo_url": course.github_repo_url,
        "finished": course.finished,
        "visible": course.visible,
        "social_media_hashtag": course.social_media_hashtag,
        "faq_document_url": course.faq_document_url,
        "min_projects_to_pass": course.min_projects_to_pass,
        "homework_problems_comments_field": (
            course.homework_problems_comments_field
        ),
        "project_passing_score": course.project_passing_score,
    }


def course_summary_to_dict(course):
    result = course_to_dict(course)
    hidden_fields = (
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
    )
    for field in hidden_fields:
        result.pop(field)
    return result


def course_detail_to_dict(course):
    result = course_to_dict(course)
    homework_records = course_homework_records(course)
    project_records = course_project_records(course)
    result.update(
        {
            "homeworks": homework_records,
            "projects": project_records,
        }
    )
    return result


def course_homework_records(course):
    homeworks = course.homework_set.all().order_by("id")
    records = []
    for homework in homeworks:
        record = course_homework_to_dict(homework)
        records.append(record)
    return records


def course_project_records(course):
    projects = course.project_set.all().order_by("id")
    records = []
    for project in projects:
        record = course_project_to_dict(project)
        records.append(record)
    return records


def course_homework_to_dict(homework):
    return {
        "id": homework.id,
        "slug": homework.slug,
        "title": homework.title,
        "instructions_url": homework.instructions_url,
        "due_date": homework.due_date.isoformat(),
        "state": homework.state,
    }


def course_project_to_dict(project):
    return {
        "id": project.id,
        "slug": project.slug,
        "title": project.title,
        "instructions_url": project.instructions_url,
        "submission_due_date": project.submission_due_date.isoformat(),
        "peer_review_due_date": project.peer_review_due_date.isoformat(),
        "state": project.state,
    }
