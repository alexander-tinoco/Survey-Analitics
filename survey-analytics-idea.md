# SurveyAnalytics — Project Idea

## The Problem

Institutions that run surveys usually end up with raw response data (CSV/Excel exports) and no real way to extract insights beyond basic counts and percentages. Tools like Google Forms already handle survey creation and basic charting well, so building "another form builder" adds no real value.

The gap is on the **analysis side**: nobody easily answers questions like *"which respondents who chose X also tend to choose Y?"*, *"are there distinct groups/profiles within my respondents?"*, or *"which questions show polarized vs. consensus opinions?"*. This project focuses entirely on that gap.

## The Idea

A web application where the core product is **the analytics engine**, not the survey builder. Users upload survey response data (CSV/XLSX, or import from Google Forms/Sheets), and the system processes it through three layers of analysis:

1. **Descriptive layer** — response distributions, participation rates, missing values.
2. **Relational layer** — correlations between questions (contingency tables, chi-square tests), segment comparisons (by demographic or custom groups).
3. **Pattern layer** — clustering respondents into behavioral/opinion profiles, detecting polarized vs. consensus questions.

Instead of just showing charts, the system generates **plain-language insights** from the statistical results (e.g., "68% of respondents who selected 'Unsatisfied' also reported low support availability"), turning numbers into readable findings — something generic survey tools don't do.

Heavy computations (correlations, clustering) are processed asynchronously and cached, since they shouldn't block the user or be recalculated on every page load.

## Stack

**Backend**
- Django + Django REST Framework
- PostgreSQL

**Analytics**
- pandas, scipy (statistical tests), scikit-learn (clustering)

**Auth**
- JWT (djangorestframework-simplejwt)

**Async & Caching**
- Celery (background processing for heavy analytics jobs)
- Redis (cache layer + Celery broker)

**Testing**
- pytest + coverage.py

**CI/CD**
- Jenkins (test, lint, build pipeline)
- Docker / Docker Compose

**Frontend**
- Chart.js or Plotly for interactive, filterable dashboards
