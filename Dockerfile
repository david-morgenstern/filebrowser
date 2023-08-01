FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

ENV DATA_VOLUME=/app/data

COPY ./app/templates/ /app/templates/
COPY ./app/static/ /app/static/
COPY ./app/app.py /app/app.py

ENTRYPOINT ["uvicorn"]
CMD ["app:app", "--host", "0.0.0.0", "--port", "666", "--reload"]
