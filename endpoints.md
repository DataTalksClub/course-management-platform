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

## Course Content

**Endpoints:**
- `GET /data/{course_slug}/content` - Get all homeworks and projects
- `POST /data/{course_slug}/content` - Create homeworks and projects

**Description:** Get or create homeworks and projects for a course. All created items have `state=CLOSED` (not visible to students until manually opened).

### GET Request

Retrieves all homeworks and projects for a course.

**Response:**
```json
{
  "success": true,
  "course": "course-slug",
  "homeworks": [
    {
      "id": 123,
      "slug": "hw-1",
      "title": "Homework 1",
      "due_date": "2025-03-15T23:59:59Z",
      "state": "CL",
      "questions_count": 5
    }
  ],
  "projects": [
    {
      "id": 456,
      "slug": "project-1",
      "title": "Project 1",
      "submission_due_date": "2025-03-20T23:59:59Z",
      "peer_review_due_date": "2025-03-27T23:59:59Z",
      "state": "CL"
    }
  ]
}
```

### POST Request

Creates homeworks and projects for a course.

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

| Code | Name | Description |
|------|------|-------------|
| `MC` | Multiple Choice | Single correct answer from a list of options |
| `FF` | Free Form | Short text answer (1-2 sentences) |
| `FL` | Free Form Long | Long text answer (essays, explanations) |
| `CB` | Checkboxes | Multiple correct answers from a list of options |

### Answer Types

| Code | Name | Description |
|------|------|-------------|
| `ANY` | Any | Any input is accepted (no validation) |
| `FLT` | Float | Decimal number validation (e.g., 3.14, -0.5) |
| `INT` | Integer | Whole number validation (e.g., 1, 42, -7) |
| `EXS` | Exact String | Answer must match exactly (case-sensitive) |
| `CTS` | Contains String | Answer must contain the specified text |

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
- `405 Method Not Allowed`: Wrong HTTP method (only GET and POST allowed)
- `500 Internal Server Error`: Server error

### Partial Success (POST only)

If some items fail (e.g., duplicate slug), others are still created. Check the `errors` array for details.

### Example Usage

```bash
# Get all course content
curl -X GET \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  https://courses.datatalks.club/data/ml-zoomcamp/content

# Create homeworks only
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"homeworks": [{"name": "Week 1", "due_date": "2025-03-15T23:59:59Z"}]}' \
  https://courses.datatalks.club/data/ml-zoomcamp/content

# Create projects only
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"projects": [{"name": "Project 1", "submission_due_date": "2025-03-20T23:59:59Z", "peer_review_due_date": "2025-03-27T23:59:59Z"}]}' \
  https://courses.datatalks.club/data/ml-zoomcamp/content

# Create both
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "homeworks": [{"name": "Homework 1", "due_date": "2025-03-15T23:59:59Z"}],
    "projects": [{"name": "Project 1", "submission_due_date": "2025-03-20T23:59:59Z", "peer_review_due_date": "2025-03-27T23:59:59Z"}]
  }' \
  https://courses.datatalks.club/data/ml-zoomcamp/content
```

---

## Homework Content

**Endpoints:**
- `GET /data/{course_slug}/homework/{homework_slug}/content` - Get homework details and questions
- `POST /data/{course_slug}/homework/{homework_slug}/content` - Create questions for homework

**Description:** Get homework details with all questions, or create new questions for a homework.

### GET Request

Retrieves homework details and all questions.

**Response:**
```json
{
  "success": true,
  "course": "ml-zoomcamp",
  "homework": {
    "id": 123,
    "slug": "hw-1",
    "title": "Homework 1",
    "description": "Introduction to ML",
    "due_date": "2025-03-15T23:59:59Z",
    "state": "CL",
    "learning_in_public_cap": 7,
    "homework_url_field": true,
    "time_spent_lectures_field": true,
    "time_spent_homework_field": true,
    "faq_contribution_field": true
  },
  "questions": [
    {
      "id": 1,
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

### POST Request

Creates questions for a homework.

**Request Body:**
```json
{
  "questions": [
    {
      "text": "What is the capital of France?",
      "question_type": "MC",
      "answer_type": "EXS",
      "possible_answers": ["London", "Paris", "Berlin"],
      "correct_answer": "2",
      "scores_for_correct_answer": 2
    },
    {
      "text": "Explain your answer",
      "question_type": "FL",
      "answer_type": "ANY"
    }
  ]
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | No | Question text |
| `question_type` | string | No | `MC`, `FF`, `FL`, or `CB` (defaults to `FF`) |
| `answer_type` | string | No | `ANY`, `FLT`, `INT`, `EXS`, or `CTS` |
| `possible_answers` | array | No | Array of answer options (for MC/CB) |
| `correct_answer` | string | No | Correct answer (index for MC/CB, value for others) |
| `scores_for_correct_answer` | int | No | Points for correct answer (default: 1) |
| `state` | string | No | Homework state: `CL`, `OP`, or `SC` |

### Homework States

| Code | Name | Description |
|------|------|-------------|
| `CL` | Closed | Not visible to students |
| `OP` | Open | Students can submit |
| `SC` | Scored | Grading completed |

### Response

```json
{
  "success": true,
  "course": "ml-zoomcamp",
  "homework": "hw-1",
  "created_questions": [
    {
      "id": 456,
      "text": "What is the capital of France?",
      "question_type": "MC"
    }
  ],
  "errors": []
}
```

If `state` is provided, response includes state change:

```json
{
  "success": true,
  "course": "ml-zoomcamp",
  "homework": "hw-1",
  "created_questions": [],
  "errors": [],
  "homework_state": {
    "old": "CL",
    "new": "OP"
  }
}
```

### Error Responses

- `400 Bad Request`: Invalid JSON or invalid state value
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Course or homework not found
- `405 Method Not Allowed`: Wrong HTTP method (only GET and POST allowed)

### Example Usage

```bash
# Get homework content
curl -X GET \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  https://courses.datatalks.club/data/ml-zoomcamp/homework/hw-1/content

# Create questions
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
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
  }' \
  https://courses.datatalks.club/data/ml-zoomcamp/homework/hw-1/content

# Create questions and open homework
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [{"text": "What is 2+2?", "question_type": "MC"}],
    "state": "OP"
  }' \
  https://courses.datatalks.club/data/ml-zoomcamp/homework/hw-1/content

# Update homework state only (no new questions)
curl -X POST \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"state": "OP"}' \
  https://courses.datatalks.club/data/ml-zoomcamp/homework/hw-1/content
```
