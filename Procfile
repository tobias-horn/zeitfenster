web: sh -c "python -m playwright install chromium && gunicorn --worker-class gthread --threads 4 --workers 1 app:app"
