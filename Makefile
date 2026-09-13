IMAGE_NAME := poxenstudio/mydict
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
# Docker tag 不允许出现 "/"，分支名里的斜杠（如 feature/xxx）换成 "-"
IMAGE_TAG := $(subst /,-,$(GIT_BRANCH))
IMAGE := $(IMAGE_NAME):$(IMAGE_TAG)
BUILDER := shukubuilder

.PHONY: build setup-multiarch build-multiarch-local
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
