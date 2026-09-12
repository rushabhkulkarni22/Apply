FROM node:24-slim AS frontend
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r /app/backend/requirements.lock
COPY backend /app/backend
COPY --from=frontend /web/dist /app/apps/web/dist
COPY job_applications/matching.py /app/job_applications/matching.py
RUN touch /app/job_applications/__init__.py && useradd --create-home --uid 10001 appuser && mkdir -p /app/runtime/resumes && chown -R appuser:appuser /app/runtime
USER appuser
EXPOSE 8000
CMD ["python", "-m", "backend.run", "--host", "0.0.0.0"]
