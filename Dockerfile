# ---- Stage 1: 编译前端 ----
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: 后端运行时，装入前端构建产物 ----
FROM python:3.12-slim
WORKDIR /app
# .git 不在构建上下文里（见 .dockerignore），分支名需由构建方通过 --build-arg 传入，
# 如 --build-arg GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)；不传时落回 dev
ARG GIT_BRANCH=dev
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /app/dist ./app/static
RUN echo "${GIT_BRANCH}" > /version.txt && chmod 644 /version.txt
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
