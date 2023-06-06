FROM tiangolo/uvicorn-gunicorn-fastapi:python3.9

COPY ./app /app


CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "666", "--reload"]