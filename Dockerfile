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
# liblzo2 运行库：LZO 压缩的 mdx（读懂你的化验单、超级新华字典等 6 部）需要。
# 不装 python-lzo（无预编译 wheel，编译不可靠），由 app/parsers/lzo_compat.py
# 用 ctypes 直接调 liblzo2 的 lzo1x_decompress_safe。
RUN apt-get update && apt-get install -y --no-install-recommends liblzo2-2 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-build /app/dist ./app/static
RUN echo "${GIT_BRANCH}" > /version.txt && chmod 644 /version.txt
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
