# 部署文档

> 相关文档：[README](../README.md) · [架构](ARCHITECTURE.md) · [API](API.md) · [配置](CONFIGURATION.md) · [模型下载](MODELS.md) · [开发](DEVELOPMENT.md)

## 0. 从 GitHub 部署（全新机器）

```bash
# 1) 安装 Docker + Compose，GPU 机器再装 nvidia-container-toolkit
#    （Ubuntu: apt 安装后执行 nvidia-ctk runtime configure --runtime=docker && systemctl restart docker）

# 2) 克隆代码
git clone <your-repo-url> knowledge && cd knowledge

# 3) 下载模型到 models/（不入库，必须手动获取，含国内镜像方式）
#    详见 docs/MODELS.md
./deploy/check-models.sh        # 下载后校验 SHA256

# 4) 配置
cp .env.example .env && chmod 600 .env
#    编辑 .env：替换所有 change-this-*，设置 ADMIN_PASSWORD、GATEWAY_PORT

# 5) 启动 + 验证
./deploy/check-environment.sh
./deploy/start.sh
./deploy/smoke-test.sh          # 13 项端到端冒烟测试
```

访问 `http://<服务器IP>:8080`，用 `.env` 的管理员账号登录。下文为本项目在实际部署机上的环境实测与运维细节。

## 0b. 离线包部署（无网络环境，推荐内网/生产机）

离线包 `knowledge-offline-<日期>.tar.zst` 内含**项目代码 + 全部 Docker 镜像**（约 11GB，`docker save` 打包），
但**不含模型文件**（9GB，需另行准备，见 [MODELS.md](MODELS.md)）。

```bash
# 制作离线包（在联网/已 build 的机器上）：
./deploy/package-offline.sh          # 先 docker save 镜像到 offline/images/，再压成 .tar.zst

# 目标机部署：
zstd -d knowledge-offline-<日期>.tar.zst -o knowledge-offline-<日期>.tar
tar xf knowledge-offline-<日期>.tar
cd knowledge

# 放入模型（离线包不含，必须手动准备）：
#   models/embedding/bge-m3/、models/reranker/bge-reranker-v2-m3/、models/llm/Qwen3-8B-Q4_K_M.gguf

./deploy/offline-deploy.sh           # 一键：docker load 镜像 → 生成 .env（随机密钥）→ 启动 → 健康检查
```

`offline-deploy.sh` 会：加载 `offline/images/*.tar` 全部镜像 → 若 `.env` 不存在则从 `.env.example`
生成并随机填充密钥/管理员密码（会打印一次，请立即记录）→ 校验模型文件 → `docker compose up -d --no-build`
→ 等待 `/api/health` 就绪并打印访问地址。目标机仍需预装 Docker/Compose，GPU 机需 nvidia-container-toolkit。

## 1. 环境要求与实测结果

| 项目 | 方案要求 | 本机实测 |
|------|----------|----------|
| 操作系统 | Ubuntu 22.04 | Ubuntu 26.04 LTS（兼容） |
| GPU | Tesla P4 × 2 | ✅ 2 × P4，驱动 580.178.04 |
| CPU / 内存 | 16核 / 64GB | ✅ 40核 / 168GB |
| 磁盘 | 数据盘 1TB | ✅ /kvm 916GB（可用 557GB） |
| Docker | 20.10+ | ✅ 29.1.3 + Compose v2.40 |
| GPU 容器 | nvidia runtime | ✅ nvidia-container-toolkit 已装 |

**端口冲突处理**：宿主机 80/443（现有 nginx）、5432（现有 postgres）、8000（gunicorn）已被占用，
本平台网关改用 **8080** 端口，其余服务不向宿主机暴露任何端口。

## 2. 安装位置与数据布局

项目根目录：`/kvm/knowledge`（所有代码、数据、模型、依赖均在此目录内，**不污染系统环境**）

```
/kvm/knowledge/
├── docker-compose.yml          # 服务编排（唯一入口 ./deploy/start.sh）
├── .env                        # 机密配置（600 权限，随机生成）
├── backend/                    # FastAPI 后端 + Celery worker 源码
├── frontend/                   # React 前端源码（构建进 nginx 镜像）
├── services/model-server/      # Embedding/Reranker 共用服务源码
├── models/                     # 模型文件（只读挂载进容器）
│   ├── embedding/bge-m3/                 # dense 1024 维
│   ├── reranker/bge-reranker-v2-m3/
│   └── llm/Qwen3-8B-Q4_K_M.gguf          # SHA256 见 offline/manifests/
├── configs/nginx/              # 网关路由配置
├── data/                       # ★ 全部运行时数据（备份只需打包此目录+models）
│   ├── postgres/               #   PostgreSQL 数据文件
│   ├── qdrant/                 #   向量与快照
│   ├── redis/                  #   队列持久化
│   ├── documents/              #   上传的原始文档（永久保留）
│   ├── extracted/              #   解析出的文本（带页码）
│   ├── temporary/              #   上传临时文件
│   ├── logs/                   #   nginx 等日志
│   └── backups/                #   备份输出
├── deploy/                     # 运维脚本
├── offline/manifests/          # 模型 SHA256 清单
└── docs/                       # 文档
```

系统级变更仅有两处（均为 Docker GPU 支持所必需，不存业务数据）：
1. apt 安装 `nvidia-container-toolkit`（含 `/etc/docker/daemon.json` 注册 nvidia runtime）
2. Docker 镜像存储（默认 /var/lib/docker，属 Docker 自身管理）

## 3. GPU 分工

| 设备 | 负载 | 说明 |
|------|------|------|
| GPU 0 | kb-embedding + kb-reranker | bge-m3 与 reranker 各占约 3GB 显存 |
| GPU 1 | kb-llm | Qwen3-8B Q4_K_M（约 5GB + KV cache），llama.cpp `-ngl 99` |

Tesla P4 为 Pascal 架构（sm_61）：
- PyTorch 使用 **cu124** 轮子（cu128 起不再支持 Pascal）
- llama.cpp 使用 `ghcr.io/ggml-org/llama.cpp:server-cuda`，若 Pascal 不兼容，
  备选方案：`-ngl 0` 回退 CPU（40核 CPU 推理 8B Q4 约 8-15 token/s）

## 4. 启动 / 停止 / 运维

```bash
./deploy/check-environment.sh  # 自检（Docker/GPU/模型/端口/.env）
./deploy/start.sh              # 构建+启动+健康检查
./deploy/stop.sh               # 停止（数据保留）
./deploy/restart.sh
./deploy/status.sh
./deploy/logs.sh backend       # 跟踪指定服务日志
./deploy/backup.sh             # 一致性备份到 data/backups/<时间戳>/（目录权限 700，含数据库与 .env 副本）
./deploy/restore.sh data/backups/<时间戳>   # 先校验 SHA256 并要求输入 yes；不会覆盖当前 .env
./deploy/check-models.sh       # 模型 SHA256 校验
```

开机自启（可选）：

```bash
sudo cp deploy/systemd/knowledge-base.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable knowledge-base
```

## 5. 首次启动流程

1. `start.sh` 自检环境 → 构建镜像 → `docker compose up -d`
2. backend 容器启动时自动：建库表（Alembic/create_all）→ 创建 admin 账号
3. 模型服务加载权重需 1-3 分钟，健康检查通过前 `/api/health/dependencies` 会显示 degraded
4. 访问 `http://<IP>:8080` 登录（账号密码见 `.env` 的 ADMIN_USERNAME/ADMIN_PASSWORD）
5. Web 端创建知识库 → 上传文档 → 等待状态变为 ready → 检索测试 / 智能问答

## 6. 验证清单

```bash
curl http://127.0.0.1:8080/api/health                 # {"status":"ok"}
curl http://127.0.0.1:8080/api/health/dependencies    # 各依赖 ok
# Swagger: http://<IP>:8080/docs
```

功能验收：登录 → 建库 → 上传 PDF/DOCX/MD/TXT/图片 → 处理完成 →
检索测试（Dense+Sparse→RRF→Rerank）→ 智能问答（流式+引用）→
创建 API Key → 用 curl 验证 `/v1/chat/completions`。

## 7. 故障排查

| 现象 | 排查 |
|------|------|
| embedding/reranker 反复重启 | `./deploy/logs.sh embedding`；显存不足时确认无其他进程占用 GPU0 |
| llm 启动失败 | `./deploy/logs.sh llm`；Pascal 不兼容时把 compose 中 `-ngl 99` 改为 `-ngl 0`（CPU 推理） |
| 文档处理卡在 processing | `./deploy/logs.sh worker`；确认 embedding 服务健康 |
| OCR 中文效果差 | 镜像内置 chi_sim+eng；扫描质量差时建议提高源文件 DPI |
| 检索无结果 | 确认文档状态为 ready；`/api/health/dependencies` 全部 ok |
| 忘记管理员密码 | 修改 `.env` 的 ADMIN_PASSWORD 并删除 users 表中旧记录后重启，或直接在 postgres 容器内改 |
