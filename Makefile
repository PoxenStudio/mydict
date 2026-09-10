IMAGE_NAME := poxenstudio/mydict
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
# Docker tag 不允许出现 "/"，分支名里的斜杠（如 feature/xxx）换成 "-"
IMAGE_TAG := $(subst /,-,$(GIT_BRANCH))
IMAGE := $(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: build
build:
	docker build --build-arg GIT_BRANCH=$(GIT_BRANCH) -t $(IMAGE) .
