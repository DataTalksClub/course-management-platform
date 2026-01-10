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
- **Auth token**: Available as `AUTH_TOKEN` environment variable, works for both dev and prod

## Workflow

0. **Find homework slugs**: If you don't know the homework slug, first use the `course-content` skill to list all homeworks and get their slugs
1. **Read the homework file**: typically it's named homework.md
2. **Read solutions file**: Analyze the content of the homework folder. There could be the solutions.md file (or similar) with the ansers
3. **Create questions**: POST questions with correct answers to the homework
4. **Open homework**: Always include `"state": "OP"` when creating questions to open the homework
5. **Provide summary**: List all questions with their answers and include the homework link

## API Endpoint

```
GET /data/<course_slug>/homework/<homework_slug>/content - Get homework details and questions
POST /data/<course_slug>/homework/<homework_slug>/content - Create questions for homework
```

Full URLs:
- Production: `https://courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content`
- Dev: `https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content`

## Authentication

`AUTH_TOKEN` environment varialbe

## Step 1: Find Homework Slugs

Use the course-content endpoint to list all homeworks:

```bash
curl -X GET "https://dev.courses.datatalks.club/data/<course_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}"
```

This returns all homeworks with their slugs, titles, and due dates. Find the target homework's `slug`.

## Step 2: Read Solutions File

Read the solutions from the cohort directory to get correct answers:

```bash
# Example path
~/git/data-engineering-zoomcamp/cohorts/2026/01-docker-terraform/solution.md
```

## Step 3: Create Questions

### Basic Question (Single Answer - MC)

```bash
curl -X POST "https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
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
    ],
    "state": "OP"
  }'
```

### Question with Multiple Correct Answers (CB)

When a question has **multiple correct answers**, provide comma-separated indices in `correct_answer`:

```bash
curl -X POST "https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "text": "Which hostnames can pgadmin use to connect to postgres? (select all that apply)",
        "question_type": "MC",
        "answer_type": "EXS",
        "possible_answers": ["postgres:5433", "localhost:5432", "db:5433", "postgres:5432", "db:5432"],
        "correct_answer": "4,5",
        "scores_for_correct_answer": 2
      }
    ],
    "state": "OP"
  }'
```

### State Update

Always include `"state": "OP"` to open the homework when creating questions:

```bash
curl -X POST "https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      ...
    ],
    "state": "OP"
  }'
```

## Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | No | Question text |
| `question_type` | string | No | `MC` (single), `FF`, `FL`, or `CB` (multiple) |
| `answer_type` | string | No | `ANY`, `FLT`, `INT`, `EXS`, or `CTS` |
| `possible_answers` | array | No | Array of answer options (for MC/CB questions) |
| `correct_answer` | string | No | For MC/CB: 1-based indices (`"1"` or `"1,3"`) |
| `scores_for_correct_answer` | int | No | Points for correct answer (default: 1) |
| `state` | string | No | Include `"OP"` to open homework when creating |

## Question Types

| Code | Name | Correct Answer Format |
|------|------|----------------------|
| `MC` | Multiple Choice | Single index: `"1"` |
| `FF` | Free Form | Text value: `"answer"` |
| `FL` | Free Form Long | Text value: `"answer"` |
| `CB` | Checkboxes | Comma-separated indices: `"1,3,4"` |

## Answer Types

| Code | Name | Description |
|------|------|-------------|
| `ANY` | Any | No validation |
| `FLT` | Float | Decimal number |
| `INT` | Integer | Whole number |
| `EXS` | Exact String | Exact match |
| `CTS` | Contains String | Contains text |

## Step 4: Verify and Provide Summary

After creating questions, verify and provide a summary:

```bash
# Verify questions were created
curl -X GET "https://dev.courses.datatalks.club/data/<course_slug>/homework/<homework_slug>/content" \
  -H "Authorization: Token ${AUTH_TOKEN}"
```

## Step 5. Give the user the URL to check the homework


```
Created N questions for "<Homework Title>"

Homework link: https://dev.courses.datatalks.club/<course_slug>/<homework_slug>


| # | Question | Correct Answer | Options |
|---|----------|----------------|---------|
| 1 | What is... | Option A | A, B, C, D |
| 2 | Select all... | Option A, C | A, B, C, D |
```

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication token required` | Missing/invalid token | Check `AUTH_TOKEN` env var |
| `Course or homework not found` | Invalid slugs | Use course-content to find slugs first |
| `Invalid JSON` | Malformed JSON | Check JSON syntax |
