---
name: homework-questions
description: Get or add questions to homeworks via API using curl
---

# Homework Questions API

## Overview

This skill provides commands to get and create questions for homeworks via the API endpoint.

## Configuration

- **Production instance**: `https://courses.datatalks.club`
- **Dev instance**: `https://dev.courses.datatalks.club`
- **Auth token**: Available as `AUTH_TOKEN` environment variable

## API Endpoint

```
GET /data/<course_slug>/homework/<homework_slug>/content - Get homework details and questions
POST /data/<course_slug>/homework/<homework_slug>/content - Create questions for homework
```

Full URLs:
- Production: `https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content`
- Dev: `https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content`

## Authentication

```bash
# Get auth token from env
TOKEN=${AUTH_TOKEN}

# Or set it manually
TOKEN="your-token-here"
```

## Getting Homework Content (GET)

Returns homework details and all questions.

```bash
curl -X GET "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}"
```

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

## Creating Questions (POST)

Create questions for an existing homework.

### Basic Question

```bash
curl -X POST "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "text": "What does SQL stand for?",
        "question_type": "MC",
        "answer_type": "EXS",
        "possible_answers": ["Structured Query Language", "Simple Query Language", "Standard Query Language"],
        "correct_answer": "1",
        "scores_for_correct_answer": 1
      }
    ]
  }'
```

### Multiple Questions

```bash
curl -X POST "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "text": "What does SQL stand for?",
        "question_type": "MC",
        "answer_type": "EXS",
        "possible_answers": ["Structured Query Language", "Simple Query Language", "Standard Query Language"],
        "correct_answer": "1",
        "scores_for_correct_answer": 1
      },
      {
        "text": "Write a SELECT statement to get all users from the 'users' table",
        "question_type": "FF",
        "answer_type": "CTS",
        "correct_answer": "SELECT",
        "scores_for_correct_answer": 2
      },
      {
        "text": "Explain your approach to solving this problem",
        "question_type": "FL",
        "answer_type": "ANY"
      }
    ]
  }'
```

### Checkbox Question

```bash
curl -X POST "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "text": "Which of the following are SQL databases? (select all that apply)",
        "question_type": "CB",
        "answer_type": "INT",
        "possible_answers": ["PostgreSQL", "MongoDB", "MySQL", "Redis"],
        "correct_answer": "1,3",
        "scores_for_correct_answer": 2
      }
    ]
  }'
```

### Update Homework State

You can also update the homework state when creating questions:

```bash
curl -X POST "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "text": "What is 2+2?",
        "question_type": "MC",
        "answer_type": "INT",
        "possible_answers": ["3", "4", "5"],
        "correct_answer": "2"
      }
    ],
    "state": "OP"
  }'
```

**States:**
- `CL` - Closed (not visible to students)
- `OP` - Open (students can submit)
- `SC` - Scored (grading completed)

You can also update state without adding questions:

```bash
curl -X POST "https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"state": "OP"}'
```

**Response includes state change:**
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

## Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | No | Question text |
| `question_type` | string | No | `MC`, `FF`, `FL`, or `CB` (defaults to `FF`) |
| `answer_type` | string | No | `ANY`, `FLT`, `INT`, `EXS`, or `CTS` |
| `possible_answers` | array | No | Array of answer options (for MC/CB questions) |
| `correct_answer` | string | No | Correct answer (1-based index for MC/CB, value for others) |
| `scores_for_correct_answer` | int | No | Points for correct answer (default: 1) |
| `state` | string | No | Homework state: `CL`, `OP`, or `SC` |

## Question Types

| Code | Name | Description |
|------|------|-------------|
| `MC` | Multiple Choice | Single correct answer from a list of options |
| `FF` | Free Form | Short text answer (1-2 sentences) |
| `FL` | Free Form Long | Long text answer (essays, explanations) |
| `CB` | Checkboxes | Multiple correct answers from a list of options |

## Answer Types

| Code | Name | Description |
|------|------|-------------|
| `ANY` | Any | Any input is accepted (no validation) |
| `FLT` | Float | Decimal number validation (e.g., 3.14, -0.5) |
| `INT` | Integer | Whole number validation (e.g., 1, 42, -7) |
| `EXS` | Exact String | Answer must match exactly (case-sensitive) |
| `CTS` | Contains String | Answer must contain the specified text |

## Response Format

### POST Response

```json
{
  "success": true,
  "course": "ml-zoomcamp",
  "homework": "hw-1",
  "created_questions": [
    {
      "id": 456,
      "text": "What does SQL stand for?",
      "question_type": "MC"
    }
  ],
  "errors": []
}
```

## Error Handling

Partial success is supported - if some questions fail, others are still created:

```json
{
  "success": true,
  "course": "ml-zoomcamp",
  "homework": "hw-1",
  "created_questions": [
    {"id": 456, "text": "Valid question", ...}
  ],
  "errors": [
    {"question": "Invalid question", "error": "error details"}
  ]
}
```

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication token required` | Missing/invalid token | Check `AUTH_TOKEN` env var |
| `Course or homework not found` | Invalid course or homework slug | Verify both exist |
| `Invalid JSON` | Malformed JSON payload | Check JSON syntax |
