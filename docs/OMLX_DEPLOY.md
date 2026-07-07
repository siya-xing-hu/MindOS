# oMLX 部署指南

本文档记录在 Apple Silicon Mac 上部署 oMLX 本地推理服务的完整步骤，作为知识库项目的本地模型后端。

## 1. 背景与定位

### 什么是 oMLX

oMLX 是专为 Apple Silicon Mac 设计的本地 LLM 推理服务，基于 Apple MLX 框架 + Metal GPU 加速。它提供 OpenAI/Anthropic 兼容的 HTTP API，一个服务同时托管：

- **LLM**（对话生成）
- **Embedding 模型**（向量化）
- **Reranker**（检索结果重排）
- **VLM / OCR**（视觉模型，本项目暂不用）

### 为什么选 oMLX（vs Ollama）

| 维度 | oMLX | Ollama |
| --- | --- | --- |
| 平台 | Apple Silicon 专用 | 跨平台 |
| 推理框架 | MLX + Metal | llama.cpp |
| Mac 性能 | 更优（统一内存利用好） | 一般 |
| Embedding 托管 | ✅ 原生（BGE-M3 等） | ❌ 只管 LLM |
| Reranker | ✅ 原生 | ❌ |
| KV cache SSD 持久化 | ✅ 重启后上下文不丢 | ❌ |
| 模型格式 | MLX | GGUF |
| 部署到 Linux | ❌ | ✅ |

**本项目选 oMLX 的理由**：
1. 开发环境是 Mac，性能更好
2. embedding + LLM + reranker 一站式，省组件
3. BGE-M3 原生支持，与选型对齐
4. 知识库项目通过 `BaseLLM` / `BaseEmbedder` 抽象解耦，未来要换 Ollama 写个 provider 即可

### 适用场景

- 个人/团队 Mac 上跑本地知识库
- 敏感数据不能走外部 API（银行内部文档等）
- 需要同时托管 embedding 和 LLM，不想装多个组件

## 2. 前置条件

| 项 | 要求 |
| --- | --- |
| 硬件 | Apple Silicon（M1/M2/M3/M4） |
| 系统 | macOS 15.0+（Sequoia） |
| Python | 3.10+（源码安装需要，Homebrew 装不需要） |
| 内存 | 16GB 起步（7B 4bit 模型约需 6-8GB） |
| 磁盘 | 至少 20GB 空闲（模型文件） |

检查命令：

```bash
sw_vers                 # 确认 macOS 版本
uname -m                # 应输出 arm64
sysctl -n hw.memsize    # 内存字节数（除以 1024^3 得 GB）
```

## 3. 安装

三种方式，推荐 Homebrew。

### 方式 A：Homebrew（推荐）

```bash
brew tap jundot/omlx https://github.com/jundot/omlx
brew install omlx
```

升级：

```bash
brew update && brew upgrade omlx
```

可选 MCP 支持：

```bash
/opt/homebrew/opt/omlx/libexec/bin/pip install mcp
```

### 方式 B：macOS App

1. 去 [Releases 页面](https://github.com/jundot/omlx/releases) 下载 `.dmg`
2. 拖到 Applications
3. App 会自动在 `~/.omlx/bin/omlx` 装一个 CLI shim，终端也能用 `omlx` 命令
4. 自带 Sparkle 自动更新

### 方式 C：源码

```bash
git clone https://github.com/jundot/omlx.git
cd omlx
pip install -e .          # 核心功能
# 或 pip install -e ".[mcp]"   带 MCP
# 或 OMLX_WITH_CUSTOM_KERNEL=1 pip install -e .   带自定义内核
```

## 4. 启动服务

### 后台服务（推荐）

```bash
omlx start
# 或等价命令
brew services start omlx
```

后台运行，开机自启。

### 前台运行（调试用）

```bash
omlx serve --model-dir ~/models
```

直接看实时日志，Ctrl+C 退出。

### 默认配置

| 项 | 默认值 |
| --- | --- |
| HTTP 端口 | 8000 |
| 模型目录 | `~/.omlx/models` |
| 配置文件 | `~/.omlx/settings.json` |
| 服务日志 | `$(brew --prefix)/var/log/omlx.log` |
| 应用日志 | `~/.omlx/logs/server.log` |
| Admin dashboard | `http://localhost:8000/admin` |
| 内置聊天 UI | `http://localhost:8000/admin/chat` |

## 5. 下载模型

oMLX 自动从模型目录加载，模型类型（LLM/Embedding/Reranker/VLM）自动识别。

### 方式 A：Admin Dashboard（推荐）

1. 浏览器打开 `http://localhost:8000/admin`
2. 进入 Model Downloader
3. 搜索 HuggingFace 上的 MLX 格式模型
4. 一键下载，自动放到 `~/.omlx/models/`

### 方式 B：手动放置

```bash
mkdir -p ~/.omlx/models
cd ~/.omlx/models
# 用 huggingface-cli 或 git clone
huggingface-cli download <model-repo> --local-dir <model-name>
```

### 本项目需要的模型

| 用途 | 模型 | 大小 | 说明 |
| --- | --- | --- | --- |
| Embedding | `BAAI/bge-m3-mlx-fp16` | ~2GB | 1024 维，oMLX EmbeddingEngine 原生支持 |
| LLM | `mlx-community/Qwen2.5-7B-Instruct-4bit` | ~5GB | 4bit 量化，16GB 内存可跑 |
| Reranker（可选） | 未来按需加 | - | 提升检索质量 |

### 网络问题

如果直连 HuggingFace 慢，启动时加镜像：

```bash
omlx serve --hf-endpoint https://hf-mirror.com
```

或后台服务模式下，编辑 `~/.omlx/settings.json` 加 `hf_endpoint` 字段。

### 模型目录结构

```
~/.omlx/models/
├── bge-m3-mlx-fp16/                          # Embedding 模型
│   ├── config.json
│   ├── model.safetensors
│   └── ...
└── Qwen2.5-7B-Instruct-4bit/        # LLM
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── ...
```

支持两级结构（如 `mlx-community/Qwen2.5-7B-Instruct-4bit/`）。

## 6. 验证部署

### 检查服务状态

```bash
# 进程状态
brew services info omlx
# 或
omlx status
```

### 列出已加载模型

```bash
curl http://localhost:8000/v1/models
```

应返回：

```json
{
  "data": [
    {"id": "bge-m3-mlx-fp16", "object": "model", ...},
    {"id": "Qwen2.5-7B-Instruct-4bit", "object": "model", ...}
  ]
}
```

### 测试 Embedding

```bash
curl -X POST http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3-mlx-fp16","input":"测试向量化"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('dim:',len(d['data'][0]['embedding']))"
```

期望输出：`dim: 1024`（bge-m3-mlx-fp16 维度，与 Milvus schema 对齐）

### 测试 LLM（非流式）

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"Qwen2.5-7B-Instruct-4bit",
    "messages":[{"role":"user","content":"你好，用一句话介绍自己"}],
    "max_tokens":50
  }'
```

### 测试 LLM（流式）

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"Qwen2.5-7B-Instruct-4bit",
    "messages":[{"role":"user","content":"讲个笑话"}],
    "stream":true
  }'
```

应看到 SSE 格式的增量输出。

## 7. 与知识库项目对接

### 配置

oMLX 服务地址通过环境变量作前端默认值参考：

`src/config.py`：

```python
import os

OMLX_BASE_URL = os.environ.get("OMLX_BASE_URL", "http://localhost:8000")
```

实际的 embedding / LLM 配置按知识库独立绑定，存 SQLite `kb_config` 表，通过 Web UI 管理。新建知识库时填入：

| 字段 | 值 |
| --- | --- |
| `embedding_provider` | `omlx` |
| `embedding_model` | `bge-m3-mlx-fp16` |
| `embedding_base_url` | `http://localhost:8000` |
| `llm_provider` | `omlx` |
| `llm_model` | `Qwen2.5-7B-Instruct-4bit` |
| `llm_base_url` | `http://localhost:8000` |

**注意**：`model` 字段必须与 oMLX `/v1/models` 返回的 `id` 一致。如果 oMLX 里给模型起了 alias，用 alias 也行。

### API 端点对应关系

| 知识库用途 | oMLX 端点 | 说明 |
| --- | --- | --- |
| Embedding（向量化文档/查询） | `POST /v1/embeddings` | bge-m3-mlx-fp16，1024 维 |
| LLM 生成（RAG 问答） | `POST /v1/chat/completions` | 流式 SSE |
| Reranker（可选，检索重排） | `POST /v1/rerank` | 未来 Phase 5 |

### 环境变量

如果 oMLX 跑在非默认端口或远程机器：

```bash
export OMLX_BASE_URL=http://localhost:8000
# 或
export OMLX_BASE_URL=http://192.168.1.100:8000
```

## 8. 性能调优

跑起来后如果 RAG 问答慢，调这几个参数：

```bash
omlx serve \
  --memory-guard-gb 48 \                       # 给系统留 48GB，按你内存调
  --memory-guard safe \                        # safe | balanced（默认）
  --paged-ssd-cache-dir ~/.omlx/cache \        # 开 SSD KV cache
  --hot-cache-max-size 20% \                   # 内存热缓存占比
  --max-concurrent-requests 16                 # 并发数，默认 8
```

后台服务模式下，编辑 `~/.omlx/settings.json` 或通过 `/admin` 改。

### 推荐配置（16GB Mac，单人使用）

```json
{
  "memory_guard": "balanced",
  "memory_guard_gb": 4,
  "max_concurrent_requests": 4,
  "hot_cache_max_size": "10%"
}
```

### 推荐配置（32GB+ Mac，团队使用）

```json
{
  "memory_guard": "balanced",
  "memory_guard_gb": 8,
  "max_concurrent_requests": 16,
  "paged_ssd_cache_dir": "~/.omlx/cache",
  "hot_cache_max_size": "20%"
}
```

## 9. 日常管理

### 启停

```bash
omlx start       # 启动后台服务
omlx stop        # 停止
omlx restart     # 重启
omlx serve --foreground   # 前台跑，看实时日志
```

macOS 菜单栏 app 也能启停 + 看状态，不用开终端。

### 查看日志

```bash
# 服务日志（stdout/stderr）
tail -f $(brew --prefix)/var/log/omlx.log

# 应用结构化日志
tail -f ~/.omlx/logs/server.log
```

### 加载/卸载模型

通过 `/admin` 面板：
- 手动 load/unload 模型
- 设 per-model TTL（多久不用自动卸载）
- pin 常用模型（不被 LRU 淘汰）

### 模型管理策略

oMLX 默认 LRU 淘汰，内存不够时自动卸载最久没用的模型。对于本项目：
- **bge-m3-mlx-fp16**：建议 pin（embedding 调用频繁，每次入库/搜索都要）
- **LLM**：可设 TTL（30 分钟不用就卸载，省内存）

## 10. 故障排查

### 服务起不来

```bash
# 看服务日志
cat $(brew --prefix)/var/log/omlx.log

# 常见原因
# 1. 端口 8000 被占用：lsof -i :8000
# 2. macOS 版本太低：sw_vers
# 3. 不是 Apple Silicon：uname -m 应为 arm64
```

### 模型加载失败

```bash
# 确认模型目录结构
ls ~/.omlx/models/<model-name>/
# 必须有 config.json + safetensors 文件

# 确认模型格式是 MLX（不是 PyTorch 原版）
# MLX 模型在 HuggingFace 一般带 -mlx 后缀或位于 mlx-community 组织下
```

### Embedding 维度不对

```bash
# 重新检查
curl -X POST http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3-mlx-fp16","input":"test"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('dim:',len(d['data'][0]['embedding']))"
```

bge-m3-mlx-fp16 必须返回 1024。如果返回其他维度，可能下错模型了。

### LLM 响应慢

- 检查内存是否够：`vm_stat` / Activity Monitor
- 模型量化太低：换 4bit 版本
- 并发太高：降 `max_concurrent_requests`
- 开 SSD KV cache：`--paged-ssd-cache-dir ~/.omlx/cache`

### 内存不足 OOM

```bash
# 调低内存上限
omlx serve --memory-guard-gb 8   # 给模型更少内存
```

或卸载不用的模型。

## 11. 卸载

```bash
# Homebrew 装
brew uninstall omlx
brew untap jundot/omlx

# 清理数据（可选）
rm -rf ~/.omlx
```

## 12. 参考资源

- 项目仓库：https://github.com/jundot/omlx
- Releases：https://github.com/jundot/omlx/releases
- Admin Dashboard：启动后访问 `http://localhost:8000/admin`
- 内置聊天 UI：`http://localhost:8000/admin/chat`
- MLX 模型社区：https://huggingface.co/mlx-community
- bge-m3-mlx-fp16 模型：https://huggingface.co/BAAI/bge-m3-mlx-fp16
- Qwen2.5 MLX 版本：https://huggingface.co/mlx-community/Qwen2.5-7B-Instruct-4bit

## 13. 快速开始 Checklist

部署时按这个清单逐项打勾：

- [ ] `sw_vers` 确认 macOS 15.0+
- [ ] `uname -m` 确认 arm64
- [ ] `brew tap jundot/omlx https://github.com/jundot/omlx`
- [ ] `brew install omlx`
- [ ] `omlx start`
- [ ] 浏览器开 `http://localhost:8000/admin` 能访问
- [ ] Admin 里下载 `BAAI/bge-m3-mlx-fp16`
- [ ] Admin 里下载 `mlx-community/Qwen2.5-7B-Instruct-4bit`
- [ ] `curl http://localhost:8000/v1/models` 能看到两个模型
- [ ] Embedding 测试返回 dim: 1024
- [ ] LLM 测试能正常对话
- [ ] 流式输出测试通过
- [ ] 知识库 Web UI 新建 KB 时，`embedding_base_url` / `llm_base_url` 填 `http://localhost:8000`，model 名与 oMLX `/v1/models` 返回一致
