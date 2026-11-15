IMAGE_NAME := poxenstudio/mydict
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
# Docker tag 不允许出现 "/"，分支名里的斜杠（如 feature/xxx）换成 "-"
IMAGE_TAG := $(subst /,-,$(GIT_BRANCH))
IMAGE := $(IMAGE_NAME):$(IMAGE_TAG)
BUILDER := shukubuilder

.PHONY: build setup-multiarch build-multiarch-local dev-up dev-down
build:
	docker build --build-arg GIT_BRANCH=$(GIT_BRANCH) -t $(IMAGE) .

# 初始化多架构构建环境（本机/打包机只需运行一次），不要使用snap安装的docker
setup-multiarch:
	docker run --privileged --rm tonistiigi/binfmt --install all
	docker buildx create --use --name $(BUILDER) || docker buildx use $(BUILDER)
	docker buildx inspect $(BUILDER) --bootstrap

# 仅构建多架构镜像到本地缓存（不推送），同时产出 amd64 和 arm64
build-multiarch-local:
	docker buildx build --pull --platform=linux/amd64,linux/arm64 \
		--builder $(BUILDER) \
		--build-arg GIT_BRANCH=$(GIT_BRANCH) \
		-t $(IMAGE) --load .

# ---- 本地开发（不走 Docker）----

# 后端默认把数据写到容器里的 /data，本地开发改放到仓库下的 .dev-data，重启后数据保留
DEV_DATA_DIR := $(CURDIR)/.dev-data
DEV_BACKEND_PORT := 8000
DEV_FRONTEND_PORT := 5173

dev-up:
	@test -x backend/.venv/bin/python || { echo "缺少 backend/.venv，请先安装后端依赖"; exit 1; }
	@test -d frontend/node_modules || { echo "缺少 frontend/node_modules，请先 cd frontend && npm install"; exit 1; }
	@mkdir -p $(DEV_DATA_DIR)
	@if lsof -ti tcp:$(DEV_BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "后端已在 $(DEV_BACKEND_PORT) 端口运行，跳过"; \
	else \
		(cd backend && nohup env \
			CONFIG_STORAGE_PATH=$(DEV_DATA_DIR)/config \
			DICTS_INBOX_PATH=$(DEV_DATA_DIR)/dicts \
			DATABASE_PATH=$(DEV_DATA_DIR)/db/mydict.sqlite3 \
			DICTIONARY_STORAGE_PATH=$(DEV_DATA_DIR)/dictionaries \
			LOG_DIR=$(DEV_DATA_DIR)/logs \
			ENABLE_SCHEDULER=false \
			.venv/bin/python -m uvicorn app.main:app --reload \
			--host 127.0.0.1 --port $(DEV_BACKEND_PORT) \
			> $(DEV_DATA_DIR)/backend.log 2>&1 & echo $$! > $(DEV_DATA_DIR)/backend.pid); \
		i=0; until lsof -ti tcp:$(DEV_BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; do \
			i=$$((i+1)); \
			if [ $$i -ge 30 ]; then \
				echo "后端启动失败，看 $(DEV_DATA_DIR)/backend.log："; tail -n 10 $(DEV_DATA_DIR)/backend.log; exit 1; \
			fi; \
			sleep 0.5; \
		done; \
		echo "后端已启动 http://127.0.0.1:$(DEV_BACKEND_PORT)"; \
	fi
	@if lsof -ti tcp:$(DEV_FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "前端已在 $(DEV_FRONTEND_PORT) 端口运行，跳过"; \
	else \
		(cd frontend && nohup npm run dev -- --port $(DEV_FRONTEND_PORT) --strictPort \
			> $(DEV_DATA_DIR)/frontend.log 2>&1 & echo $$! > $(DEV_DATA_DIR)/frontend.pid); \
		i=0; until lsof -ti tcp:$(DEV_FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; do \
			i=$$((i+1)); \
			if [ $$i -ge 30 ]; then \
				echo "前端启动失败，看 $(DEV_DATA_DIR)/frontend.log："; tail -n 10 $(DEV_DATA_DIR)/frontend.log; exit 1; \
			fi; \
			sleep 0.5; \
		done; \
		echo "前端已启动 http://localhost:$(DEV_FRONTEND_PORT)"; \
	fi
	@echo "日志：$(DEV_DATA_DIR)/backend.log、$(DEV_DATA_DIR)/frontend.log；停止：make dev-down"

dev-down:
	@# uvicorn --reload 会派生子进程，先按端口找监听者，再按命令行兜底
	@for port in $(DEV_BACKEND_PORT) $(DEV_FRONTEND_PORT); do \
		pids=$$(lsof -ti tcp:$$port -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$pids" ]; then kill $$pids 2>/dev/null; echo "已停止端口 $$port"; fi; \
	done
	@pkill -f "uvicorn app.main:app --reload" 2>/dev/null || true
	@rm -f $(DEV_DATA_DIR)/backend.pid $(DEV_DATA_DIR)/frontend.pid
