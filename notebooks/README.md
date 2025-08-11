# Course Management Platform - Notebooks

This directory contains Jupyter notebooks for data analysis, course management, and administrative tasks related to the course management platform.

## Overview

All notebooks in this directory are designed to work with the Django-based course management platform. They include setup code to initialize Django and access the database models.

## Notebook Descriptions

### Core Setup and Utilities

- **`_starter.ipynb`** - Basic setup notebook that initializes Django environment and imports models. Use this as a starting point for other notebooks.

### Course Management and Analysis

- **`graduates.ipynb`** - Generates graduate lists and certificate data for completed courses. Computes certificate hashes and exports graduate information to CSV format.

- **`graduates-two-projects.ipynb`** - Similar to graduates.ipynb but specifically for students who completed two projects, used for advanced certification.

- **`de-zoomcamp-leaderboard.ipynb`** - Analyzes and processes leaderboard data for Data Engineering Zoomcamp courses, including project submissions and student rankings.

### Project Management

- **`project-submission.ipynb`** - Examines project submissions, peer reviews, and related metadata like GitHub links and commit IDs.

- **`project-test-data.ipynb`** - Creates and manages test data for projects, useful for development and testing scenarios.

- **`submitted-projects.ipynb`** - Analyzes submitted projects across courses, including project status and evaluation data.

- **`project-review-delete.ipynb`** - Administrative tool for removing project reviews and related data.

- **`project-review-dump.ipynb`** - Exports project review data for analysis and reporting purposes.

### Homework and Assessment

- **`homework-submissions.ipynb`** - Analyzes homework submissions, scores, and student performance data.

- **`copy-homework.ipynb`** - Utility for duplicating homework assignments across different courses or sections.

- **`competition.ipynb`** - Processes competition-style homework submissions, particularly for machine learning competitions with specific answer formats.

### Scoring and Evaluation

- **`scoring-speedup.ipynb`** - Optimizes homework scoring processes and converts answer formats between text and index-based systems.

- **`criteria.ipynb`** - Defines and manages review criteria for projects, including scoring rubrics for different evaluation types (radio buttons, checkboxes, etc.).

### Data Management and Analysis

- **`merge_submissions.ipynb`** - Combines and consolidates submission data from multiple sources.

- **`time-spent-export.ipynb`** - Exports time tracking data for analysis of student engagement and course completion patterns.

- **`cheater-removal.ipynb`** - Administrative tool for identifying and removing fraudulent submissions and enrollments.

### Content and Documentation

- **`article.ipynb`** - Generates content and documentation, likely for course materials or reports.

## Usage Notes

1. **Django Setup**: All notebooks include the necessary Django setup code at the beginning. Make sure you're running from the correct directory.

2. **Environment Variables**: Notebooks set `IS_LOCAL=1` and configure Django settings for local development.

3. **Model Access**: Notebooks import from `courses.models.*` to access the database models.

4. **Data Export**: Many notebooks export data to CSV format for further analysis or reporting.

5. **Administrative Functions**: Some notebooks perform administrative tasks like data cleanup, user removal, and system maintenance.

## Dependencies

- Django
- Pandas
- Jupyter Notebook
- Python standard libraries (os, hashlib, collections, etc.)


## Important Notes

- **Backup Data**: Before running administrative notebooks (especially deletion operations), ensure you have backups of your database.
- **Testing**: Test notebooks on development data before running on production systems.
- **Permissions**: Some notebooks perform destructive operations - ensure you have the necessary permissions and understanding of the consequences. 