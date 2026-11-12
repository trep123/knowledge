# 模型下载与校验（Models）

模型权重体积大（合计约 9 GB），**不纳入 Git 仓库**（`.gitignore` 已排除 `models/*`）。部署前需自行下载到项目 `models/` 目录下。三个模型全部本地推理，运行时无需联网。

| 用途 | 模型 | 目标目录 | 大小 |
|------|------|----------|------|
| Embedding（稠密 1024 维） | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | `models/embedding/bge-m3/` | ~2.3 GB |
| Reranker（交叉编码精排） | [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | `models/reranker/bge-reranker-v2-m3/` | ~2.3 GB |
| LLM（生成回答） | [Qwen/Qwen3-8B-GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF) 的 `Qwen3-8B-Q4_K_M.gguf` | `models/llm/` | ~4.7 GB |

> 各模型权重遵循其原始许可证（bge 系列为 MIT，Qwen3 见其模型卡），请自行确认合规使用。

## 目标目录结构

```
models/
├── embedding/bge-m3/
│   ├── pytorch_model.bin              # 注意：bge-m3 仓库无 safetensors，用 .bin
│   ├── config.json                    # ★ 必含 model_type，否则加载报错
│   ├── tokenizer.json / tokenizer_config.json / special_tokens_map.json
│   ├── sentencepiece.bpe.model
│   ├── modules.json / config_sentence_transformers.json
│   └── 1_Pooling/config.json
├── reranker/bge-reranker-v2-m3/
│   ├── model.safetensors
│   ├── config.json                    # ★ 同上
│   ├── tokenizer.json / tokenizer_config.json / special_tokens_map.json
│   └── sentencepiece.bpe.model
└── llm/
    └── Qwen3-8B-Q4_K_M.gguf
```

## 方式一：huggingface CLI（推荐）

国内网络 `huggingface.co` 常被墙，用镜像 `hf-mirror.com`：

```bash
# 建一个独立工具虚拟环境（不污染系统 Python）
python3 -m venv .tools-venv
./.tools-venv/bin/pip install -U "huggingface_hub[cli]"
export HF_ENDPOINT=https://hf-mirror.com

# Embedding：显式列出所需文件（--include 比 --exclude 更可靠）
./.tools-venv/bin/hf download BAAI/bge-m3 \
  --local-dir models/embedding/bge-m3 \
  --include "pytorch_model.bin" "config.json" "tokenizer.json" "tokenizer_config.json" \
            "special_tokens_map.json" "sentencepiece.bpe.model" "modules.json" \
            "config_sentence_transformers.json" "1_Pooling/*"

# Reranker
./.tools-venv/bin/hf download BAAI/bge-reranker-v2-m3 \
  --local-dir models/reranker/bge-reranker-v2-m3 \
  --include "model.safetensors" "config.json" "tokenizer.json" "tokenizer_config.json" \
            "special_tokens_map.json" "sentencepiece.bpe.model"

# LLM（GGUF 量化）
./.tools-venv/bin/hf download Qwen/Qwen3-8B-GGUF \
  --local-dir models/llm \
  --include "Qwen3-8B-Q4_K_M.gguf"
```

> 提示：`hf download` 的 `--include` 请用**明确的文件名列表**；用 `--exclude` 通配易被误解析导致漏文件。下载完务必确认 `config.json` 存在（见下方“常见坑”）。

## 方式二：直接 curl 单文件

```bash
BASE=https://hf-mirror.com/BAAI/bge-m3/resolve/main
mkdir -p models/embedding/bge-m3/1_Pooling
for f in pytorch_model.bin config.json tokenizer.json tokenizer_config.json \
         special_tokens_map.json sentencepiece.bpe.model modules.json \
         config_sentence_transformers.json; do
  curl -L "$BASE/$f" -o "models/embedding/bge-m3/$f"
done
curl -L "$BASE/1_Pooling/config.json" -o models/embedding/bge-m3/1_Pooling/config.json

RBASE=https://hf-mirror.com/BAAI/bge-reranker-v2-m3/resolve/main
mkdir -p models/reranker/bge-reranker-v2-m3
for f in model.safetensors config.json tokenizer.json tokenizer_config.json \
         special_tokens_map.json sentencepiece.bpe.model; do
  curl -L "$RBASE/$f" -o "models/reranker/bge-reranker-v2-m3/$f"
done

curl -L https://hf-mirror.com/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf \
  -o models/llm/Qwen3-8B-Q4_K_M.gguf
```

## 完整性校验

本仓库附带 SHA256 清单 `offline/manifests/models.sha256`（路径相对项目根目录，任意部署目录均可直接校验）：

```bash
./deploy/check-models.sh          # 等价于 sha256sum -c offline/manifests/models.sha256
```

当前清单参考值（用于比对下载是否完整）：

| 文件 | SHA256 |
|------|--------|
| `models/embedding/bge-m3/pytorch_model.bin` | `b5e0ce34…cf6aad38` |
| `models/reranker/bge-reranker-v2-m3/model.safetensors` | `d9e3e081…cedb5286` |
| `models/llm/Qwen3-8B-Q4_K_M.gguf` | `d98cdcbd…82c5745785` |

## 常见坑

- **`Unrecognized model … Should have a model_type key`**：`config.json` 缺失或为空。bge-m3 / bge-reranker 的 `--include` 若没列出 `config.json` 就会漏下，需单独补齐（`model_type` 为 `xlm-roberta`）。
- **bge-m3 没有 `model.safetensors`**：官方仓库只提供 `pytorch_model.bin`，用 `.bin` 即可。
- **下载慢/中断**：优先用 `hf-mirror.com`；GGUF 大文件可用 `curl -C -` 续传。
- **换其它 LLM**：把任意 GGUF 放入 `models/llm/`，并同步修改 `docker-compose.yml` 中 llm 的 `-m` 路径与 `.env` 的 `LLM_MODEL`；非 Qwen3 模型可去掉 `--reasoning-budget 0`。
- **换其它 Embedding 模型**：需保证输出维度与 `.env`/建库时的 `embedding_dimension` 一致，否则要重建知识库 Collection。
