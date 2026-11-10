#!/usr/bin/env bash
# 校验模型文件完整性（与 offline/manifests/models.sha256 比对）
set -e
cd "$(dirname "$0")/.."
sha256sum -c offline/manifests/models.sha256 && echo "模型文件校验通过"
