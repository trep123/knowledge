#!/usr/bin/env bash
# 共享函数：列出 docker-compose.yml 中引用的全部镜像（不依赖 .env）
compose_images() {
    grep -E '^[[:space:]]+image:[[:space:]]' "${1:-docker-compose.yml}" \
        | awk '{print $2}' | tr -d '"'"'" | sort -u
}
