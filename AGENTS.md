### ⚠️ Use UV for Python Package Management

When installing Python packages, use `uv` instead of `pip`. See `/uv` for details.

❌ WRONG:
```bash
pip install djangorestframework
```

✅ CORRECT:
```bash
cd backend-django
uv add djangorestframework
```

Run Django commands:
```bash
cd backend-django
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py test
```


## One-time tests and debug scripts


One-time scripts and temporary files should be in .tmp. It's in .gitignore so we won't accidentally commit it to git.


## Health Check Endpoint

There is a public health check endpoint that returns the current version:

```
GET /data/health/
```

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

This endpoint requires no authentication and can be used to:
- Verify the service is running
- Check the deployed version
- Health monitoring for load balancers

**Example:**
```bash
curl https://dev.courses.datatalks.club/data/health/
# {"status": "ok", "version": "0.1.0"}
```
