# API Endpoints

Most API endpoints require authentication using a valid token in the Authorization header: `Token <token_key>` (except where noted as public)

---

## Course Criteria (Public)

**Endpoint:** `GET /{course_slug}/course-criteria.yaml`

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
curl http://localhost:8000/machine-learning-zoomcamp/course-criteria.yaml
```

---

## Homework Data

**Endpoint:** `GET /data/{course_slug}/homework/{homework_slug}`

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
  http://localhost:8000/data/fake-course/homework/hw1
```

---

## Project Data

**Endpoint:** `GET /data/{course_slug}/project/{project_slug}`

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
  http://localhost:8000/data/fake-course/project/project-1
```

---

## Graduates Data

**Endpoint:** `GET /data/{course_slug}/graduates`

**Description:** Retrieves a list of students who have successfully completed the course by passing the minimum required number of projects.

**Response:** Returns an array of graduates with:
- Student email
- Certificate name (or display name if certificate name not set)

**Example Usage:**
```bash
TOKEN="your_token_here"
curl -H "Authorization: Token ${TOKEN}" \
  http://localhost:8000/data/fake-course/graduates
```

---

## Update Enrollment Certificate

**Endpoint:** `POST /data/{course_slug}/update-certificate`

**Description:** Updates the certificate URL for a user's enrollment in a specific course.

**Request Body:**
```json
{
  "email": "user@example.com",
  "certificate_path": "/path/to/certificate.pdf"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Certificate URL updated for user@example.com in course course-slug",
  "enrollment_id": 123,
  "certificate_url": "/path/to/certificate.pdf"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required fields or invalid JSON
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: User not found or not enrolled in the course
- `405 Method Not Allowed`: Wrong HTTP method (only POST allowed)
- `500 Internal Server Error`: Server error

**Example Usage:**
```bash
curl -X POST \
  -H "Authorization: Token your_token_here" \
  -H "Content-Type: application/json" \
  -d '{"email": "student@example.com", "certificate_path": "/certificates/student-cert.pdf"}' \
  http://localhost:8000/data/python-for-data-science/update-certificate
```

---

## Create Course Content

**Endpoint:** `POST /data/{course_slug}/create-content`

**Description:** Creates homeworks and projects for a course. All items are created with `state=CLOSED` (not visible to students until manually opened).

**Request Body:**
```json
{
  "homeworks": [
    {
      "name": "Homework 1",
      "slug": "hw-1",
      "due_date": "2025-03-15T23:59:59Z",
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
  ],
  "projects": [
    {
      "name": "Project 1",
      "slug": "project-1",
      "submission_due_date": "2025-03-20T23:59:59Z",
      "peer_review_due_date": "2025-03-27T23:59:59Z",
      "description": "Optional description"
    }
  ]
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `homeworks[].name` | string | Yes | Homework title |
| `homeworks[].slug` | string | No | URL identifier (auto-generated if omitted) |
| `homeworks[].due_date` | string | Yes | ISO 8601 datetime |
| `homeworks[].description` | string | No | Homework description |
| `homeworks[].questions` | array | No | Array of question objects |
| `projects[].name` | string | Yes | Project title |
| `projects[].slug` | string | No | URL identifier (auto-generated if omitted) |
| `projects[].submission_due_date` | string | Yes | ISO 8601 datetime |
| `projects[].peer_review_due_date` | string | Yes | ISO 8601 datetime |
| `projects[].description` | string | No | Project description |

### Question Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | No | Question text |
| `question_type` | string | No | `MC`, `FF`, `FL`, or `CB` (defaults to `FF`) |
| `answer_type` | string | No | `ANY`, `FLT`, `INT`, `EXS`, or `CTS` |
| `possible_answers` | array | No | Array of answer options (for MC/CB) |
| `correct_answer` | string | No | Correct answer (index for MC/CB, value for others) |
| `scores_for_correct_answer` | int | No | Points for correct answer (default: 1) |

### Question Types

- `MC` - **Multiple Choice**: Single correct answer from options
- `FF` - **Free Form**: Short text answer
- `FL` - **Free Form Long**: Long text answer
- `CB` - **Checkboxes**: Multiple correct answers

### Answer Types

- `ANY` - Any input accepted
- `FLT` - Float number
- `INT` - Integer
- `EXS` - Exact string match
- `CTS` - Contains string

### Response

```json
{
  "success": true,
  "course": "course-slug",
  "created_homeworks": [
    {
      "id": 123,
      "slug": "hw-1",
      "title": "Homework 1",
      "due_date": "2025-03-15T23:59:59Z",
      "state": "CL",
      "questions_count": 1
    }
  ],
  "created_projects": [
    {
      "id": 456,
      "slug": "project-1",
      "title": "Project 1",
      "submission_due_date": "2025-03-20T23:59:59Z",
      "peer_review_due_date": "2025-03-27T23:59:59Z",
      "state": "CL"
    }
  ],
  "errors": []
}
```

### Error Responses

- `400 Bad Request`: Invalid JSON
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Course not found
- `405 Method Not Allowed`: Wrong HTTP method (only POST allowed)
- `500 Internal Server Error`: Server error

### Partial Success

If some items fail (e.g., duplicate slug), others are still created. Check the `errors` array for details.

### Example Usage

```bash
# Create homeworks only
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"homeworks": [{"name": "Week 1", "due_date": "2025-03-15T23:59:59Z"}]}' \
  https://courses.datatalks.club/courses/data/ml-zoomcamp/create-content

# Create projects only
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"projects": [{"name": "Project 1", "submission_due_date": "2025-03-20T23:59:59Z", "peer_review_due_date": "2025-03-27T23:59:59Z"}]}' \
  https://courses.datatalks.club/courses/data/ml-zoomcamp/create-content

# Create both
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "homeworks": [{"name": "Homework 1", "due_date": "2025-03-15T23:59:59Z"}],
    "projects": [{"name": "Project 1", "submission_due_date": "2025-03-20T23:59:59Z", "peer_review_due_date": "2025-03-27T23:59:59Z"}]
  }' \
  https://courses.datatalks.club/courses/data/ml-zoomcamp/create-content
```
