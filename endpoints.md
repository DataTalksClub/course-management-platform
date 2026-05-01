# API Endpoints

Most API endpoints require authentication using a valid token in the Authorization header: `Token <token_key>` (except where noted as public)

## Generated OpenAPI Specification

**Endpoint:** `GET /api/openapi.json`

**Authentication:** Required. Use `Authorization: Token <token_key>`.

**Description:** Returns the generated OpenAPI 3.1 specification for the course management API. Agents should use this endpoint as the source of truth for current `/api/` routes, request bodies, responses, authentication, and guarded delete rules. The response includes `x-route-coverage`; `undocumented` must stay empty, and tests fail if a routed endpoint is missing from the spec.

**Example Usage:**
```bash
curl -H "Authorization: Token ${AUTH_TOKEN}" \
  https://courses.datatalks.club/api/openapi.json
```

---

## Course Criteria (Public)

**Endpoint:** `GET /api/courses/{course_slug}/course-criteria.yaml`

**Description:** Retrieves the review criteria for a course in YAML format. This is a public endpoint that doesn't require authentication.

**Response:** Returns YAML-formatted data containing:
- Course information (slug, title, description)
- All review criteria for the course including:
  - Criteria descriptions
  - Criteria types (Radio Buttons or Checkboxes)
  - Available options with scores

**Example Response:**
```yaml
course:
  slug: machine-learning-zoomcamp
  title: Machine Learning Zoomcamp
  description: Learn machine learning engineering
review_criteria:
  - description: Problem description
    type: Radio Buttons
    review_criteria_type: RB
    options:
      - criteria: The problem is not described
        score: 0
      - criteria: The problem is well described
        score: 2
  - description: Best practices
    type: Checkboxes
    review_criteria_type: CB
    options:
      - criteria: There are unit tests
        score: 1
      - criteria: There's a CI/CD pipeline
        score: 2
```

**Example Usage:**
```bash
curl http://localhost:8000/api/courses/machine-learning-zoomcamp/course-criteria.yaml
```

---

## Health Check (Public)

**Endpoint:** `GET /api/health/`

**Description:** Returns service status and the deployed application version.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## Leaderboard Data (Public)

**Endpoint:** `GET /api/courses/{course_slug}/leaderboard.yaml`

**Description:** Returns paginated leaderboard data in YAML format. Use `?page=N` to request a page. Page size is 100.

---

## Homework Data

**Endpoint:** `GET /api/courses/{course_slug}/homeworks/{homework_slug}/submissions`

**Description:** Retrieves comprehensive homework data including course information, homework details, and all student submissions with their answers.

**Response:** Returns course data, homework details, and an array of submissions with:
- Student information
- Homework submission details (links, time spent, scores)
- Individual question answers with correctness
- Learning in public contributions
- FAQ contributions

**Example Usage:**
```bash
TOKEN="your_token_here"
curl -H "Authorization: Token ${TOKEN}" \
  http://localhost:8000/api/courses/fake-course/homeworks/hw1/submissions
```

---

## Project Data

**Endpoint:** `GET /api/courses/{course_slug}/projects/{project_slug}/submissions`

**Description:** Retrieves comprehensive project data including course information, project details, and all student submissions with their scores and peer review information.

**Response:** Returns course data, project details, and an array of submissions with:
- Student information and GitHub links
- Project scores (project, FAQ, learning in public, peer review)
- Peer review status and scores
- Pass/fail status
- Time spent and learning in public links

**Example Usage:**
```bash
TOKEN="your_token_here"
curl -H "Authorization: Token ${TOKEN}" \
  http://localhost:8000/api/courses/fake-course/projects/project-1/submissions
```

---

## Graduates Data

**Endpoint:** `GET /api/courses/{course_slug}/graduates`

**Description:** Retrieves a list of students who have successfully completed the course by passing the minimum required number of projects.

**Response:** Returns an array of graduates with:
- Student email
- Certificate name (or display name if certificate name not set)

**Example Usage:**
```bash
TOKEN="your_token_here"
curl -H "Authorization: Token ${TOKEN}" \
  http://localhost:8000/api/courses/fake-course/graduates
```

---

## Bulk Update Enrollment Certificates

**Endpoint:** `POST /api/courses/{course_slug}/certificates`

**Description:** Updates certificate URLs for many enrollments in one request. This endpoint is intended for certificate generation scripts and returns per-entry errors instead of failing the entire batch.

**Request Body:**
```json
{
  "certificates": [
    {
      "email": "user@example.com",
      "certificate_path": "/path/to/certificate.pdf"
    }
  ]
}
```

A bare JSON array with the same objects is also accepted.

**Response:**
```json
{
  "success": false,
  "updated_count": 1,
  "error_count": 1,
  "updated": [
    {
      "index": 0,
      "email": "user@example.com",
      "enrollment_id": 123,
      "certificate_url": "/path/to/certificate.pdf"
    }
  ],
  "errors": [
    {
      "index": 1,
      "email": "missing@example.com",
      "code": "user_not_found",
      "error": "User with email missing@example.com not found"
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request`: Invalid JSON, missing `certificates`, or empty update list
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Course not found
- `405 Method Not Allowed`: Wrong HTTP method (only POST allowed)

**Example Usage:**
```bash
curl -X POST \
  -H "Authorization: Token your_token_here" \
  -H "Content-Type: application/json" \
  -d '{"certificates":[{"email":"student@example.com","certificate_path":"/certificates/student-cert.pdf"}]}' \
  http://localhost:8000/api/courses/python-for-data-science/certificates
```

---

## Course Management API

All endpoints in this section require `Authorization: Token <token_key>`.

### Courses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/courses/` | List courses |
| `POST` | `/api/courses/` | Create a course |
| `GET` | `/api/courses/{course_slug}/` | Get course details with homework and project summaries |
| `PATCH` | `/api/courses/{course_slug}/` | Update a course |

Create payload:
```json
{
  "slug": "ml-zoomcamp-2026",
  "title": "Machine Learning Zoomcamp 2026",
  "description": "Course description",
  "visible": true
}
```

### Homeworks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/courses/{course_slug}/homeworks/` | List homeworks |
| `POST` | `/api/courses/{course_slug}/homeworks/` | Create one homework, or bulk-create from a JSON array |
| `GET` | `/api/courses/{course_slug}/homeworks/{homework_id}/` | Get homework details |
| `PATCH` | `/api/courses/{course_slug}/homeworks/{homework_id}/` | Update an existing homework |
| `DELETE` | `/api/courses/{course_slug}/homeworks/{homework_id}/` | Delete a homework, only when safe |
| `GET` | `/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/` | Get homework details by slug |
| `PUT` | `/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/` | Create or update homework by slug |
| `PATCH` | `/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/` | Update homework by slug |
| `DELETE` | `/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/` | Delete homework by slug, only when safe |

Create payload:
```json
{
  "name": "Homework 1",
  "slug": "hw-1",
  "due_date": "2026-04-01T23:59:59Z",
  "description": "Optional description",
  "questions": [
    {
      "text": "What is 2+2?",
      "question_type": "MC",
      "answer_type": "INT",
      "possible_answers": ["3", "4", "5"],
      "correct_answer": "2",
      "scores_for_correct_answer": 1
    }
  ]
}
```

Patchable fields: `title`, `description`, `due_date`, `state`, `learning_in_public_cap`, `homework_url_field`, `time_spent_lectures_field`, `time_spent_homework_field`, `faq_contribution_field`.

Homework delete safety rules:
- The homework must be `CL` closed.
- The homework must have no submissions.
- Responses include `submissions_count`, `can_delete`, and `delete_blockers`.
- Agents can use the `by-slug` endpoint when correcting draft homework from course repositories.

`PUT` by slug is idempotent. If the homework does not exist, it creates it with `state=CL`. If it exists, it updates supplied fields. If `questions` are supplied for an existing homework, the API replaces existing questions only when the homework is closed and has no submissions.

Delete rejection examples:
```json
{"error": "Only closed homeworks can be deleted"}
```

```json
{"error": "Cannot delete homework with existing submissions"}
```

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/courses/{course_slug}/projects/` | List projects |
| `POST` | `/api/courses/{course_slug}/projects/` | Create one project, or bulk-create from a JSON array |
| `GET` | `/api/courses/{course_slug}/projects/{project_id}/` | Get project details |
| `PATCH` | `/api/courses/{course_slug}/projects/{project_id}/` | Update an existing project |
| `DELETE` | `/api/courses/{course_slug}/projects/{project_id}/` | Delete a project, only when safe |
| `GET` | `/api/courses/{course_slug}/projects/by-slug/{project_slug}/` | Get project details by slug |
| `PUT` | `/api/courses/{course_slug}/projects/by-slug/{project_slug}/` | Create or update project by slug |
| `PATCH` | `/api/courses/{course_slug}/projects/by-slug/{project_slug}/` | Update project by slug |
| `DELETE` | `/api/courses/{course_slug}/projects/by-slug/{project_slug}/` | Delete project by slug, only when safe |

Create payload:
```json
{
  "name": "Project 1",
  "slug": "project-1",
  "submission_due_date": "2026-04-01T23:59:59Z",
  "peer_review_due_date": "2026-04-08T23:59:59Z",
  "description": "Optional description"
}
```

Patchable fields: `title`, `description`, `submission_due_date`, `peer_review_due_date`, `state`, `learning_in_public_cap_project`, `learning_in_public_cap_review`, `number_of_peers_to_evaluate`, `points_for_peer_review`, `time_spent_project_field`, `problems_comments_field`, `faq_contribution_field`.

Project delete safety rules:
- The project must be `CL` closed.
- The project must have no submissions.
- Responses include `submissions_count`, `can_delete`, and `delete_blockers`.
- Agents can use the `by-slug` endpoint when correcting draft projects from course repositories.

`PUT` by slug is idempotent. If the project does not exist, it creates it with `state=CL`. If it exists, it updates supplied fields.

Delete rejection examples:
```json
{"error": "Only closed projects can be deleted"}
```

```json
{"error": "Cannot delete project with existing submissions"}
```

### Questions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/courses/{course_slug}/homeworks/{homework_id}/questions/` | List questions |
| `POST` | `/api/courses/{course_slug}/homeworks/{homework_id}/questions/` | Create one question, or bulk-create from a JSON array |
| `GET` | `/api/courses/{course_slug}/homeworks/{homework_id}/questions/{question_id}/` | Get question details |
| `PATCH` | `/api/courses/{course_slug}/homeworks/{homework_id}/questions/{question_id}/` | Update an existing question |
| `DELETE` | `/api/courses/{course_slug}/homeworks/{homework_id}/questions/{question_id}/` | Delete a question only if it has no answers |

Question fields:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Question text; required for create |
| `question_type` | string | `MC`, `FF`, `FL`, or `CB`; defaults to `FF` |
| `answer_type` | string | `ANY`, `FLT`, `INT`, `EXS`, or `CTS` |
| `possible_answers` | array | Answer options for `MC` or `CB` |
| `correct_answer` | string | Correct answer, or answer indexes for `MC`/`CB` |
| `scores_for_correct_answer` | int | Points for a correct answer |

Question delete safety rule:
- A question with existing answers cannot be deleted, because that would delete submitted answer data.
- Responses include `answers_count`, `can_delete`, and `delete_blockers`.

Delete rejection example:
```json
{"error": "Cannot delete question with existing answers"}
```

### States

Homework states:

| Code | Name | Description |
|------|------|-------------|
| `CL` | Closed | Not visible to students |
| `OP` | Open | Students can submit |
| `SC` | Scored | Grading completed |

Project states:

| Code | Name | Description |
|------|------|-------------|
| `CL` | Closed | Not visible to students |
| `CS` | Collecting submissions | Students can submit |
| `PR` | Peer reviewing | Peer review is active |
| `CO` | Completed | Project is complete |

### Submission Mutation

The API does not expose endpoints to create, patch, or delete homework submissions, project submissions, answers, peer reviews, or project evaluation scores. Submission data is read-only through the `/api/` export endpoints.
