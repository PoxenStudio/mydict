# ---- Stage 1: 编译前端 ----
FROM docker.1ms.run/node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

LABEL Author="PoxenStudio(poxenstudio@gmail.com)" \
      org.opencontainers.image.description="mydict: A web application for managing a dictionary and providing query APIs." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="mydict" \
      org.opencontainers.image.vendor="PoxenStudio" \
      org.opencontainers.image.source="https://github.com/PoxenStudio/mydict"

# ---- Stage 2: 后端运行时，装入前端构建产物 ----
FROM docker.1ms.run/python:3.12-slim
WORKDIR /app
ARG GIT_BRANCH=dev
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /app/dist ./app/static
RUN echo "${GIT_BRANCH}" > /version.txt && chmod 644 /version.txt
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
