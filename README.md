# MindOS

本地多知识库系统：把任意目录下的 Markdown 文档导入到向量数据库，提供语义搜索和 RAG 问答，通过 Web UI 访问。

## 特性

- **多知识库**：一个实例支持多个独立知识库，每个 KB 独立配置（数据目录、embedding、LLM）
- **配置可视化**：知识库配置通过 Web UI 管理，存 SQLite，支持一键复制
- **模型可混用**：每个 KB 独立绑定 embedding / LLM，本地 oMLX 或外部 API 均可
- **单库检索**：每个 KB 独立搜索/问答，不做跨库
- **手动管理**：前端目录树勾选 + 三色入库状态标记，手动触发导入/更新
- **本地渲染**：文档在 Web UI 内渲染，不跳转外部链接
- **应用与数据分离**：数据路径由用户在 KB 配置里指定，应用仓库可公开

## 架构

```
Web UI (文档 / 搜索 / 问答 / 管理)
        ↓
FastAPI Server
        ↓
file_reader (扫目录 .md) → Embedder (向量化) → Milvus (向量存储)
                                                 ↓
                                              Search / RAG (LLM)

KB 配置 → SQLite (kb_config 表)
```

详细设计见 [docs/DESIGN.md](docs/DESIGN.md)。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 向量库 | Milvus 2.x |
| KB 配置存储 | SQLite |
| 本地推理 | oMLX（Apple Silicon） |
| Embedding | bge-m3-mlx-fp16（经 oMLX `/v1/embeddings`，1024 维） |
| LLM | Qwen2.5-7B-Instruct-4bit MLX（经 oMLX `/v1/chat/completions`） |
| 后端 | FastAPI |
| 前端 | 单文件 HTML + 原生 JS + marked.js |

## 目录结构

```
MindOS/
├── README.md
├── requirements.txt
├── .gitignore
├── docs/
│   ├── DESIGN.md          # 完整设计文档
│   ├── OMLX_DEPLOY.md     # oMLX 部署指南
│   └── SUMMARY.md         # 项目总结
└── src/
    ├── config.py          # 全局配置（Milvus / oMLX / 切分参数）
    ├── kb_store.py        # SQLite: kb_config 表
    ├── kb_registry.py     # 装配 embedder / llm / milvus
    ├── file_reader.py     # 通用文件读取 + content hash
    ├── chunker.py         # Markdown header-aware 切分
    ├── milvus_store.py    # 多 collection 管理
    ├── ingest.py          # 手动导入 + refresh
    ├── search.py          # 语义检索
    ├── rag.py             # RAG 问答
    ├── server.py          # FastAPI 路由
    ├── embedders/
    │   ├── base.py
    │   └── omlx.py
    ├── llms/
    │   ├── base.py
    │   └── omlx.py
    └── templates/
        └── index.html
```

## 部署

### 1. 前置依赖

- **Milvus**：按 [官方文档](https://milvus.io/docs/zh/install_standalone-docker-compose.md) 用 docker-compose 起一个 standalone 实例，默认 `localhost:19530`
- **oMLX**：Apple Silicon Mac 上的本地推理服务，部署步骤见 [docs/OMLX_DEPLOY.md](docs/OMLX_DEPLOY.md)
- **Python**：3.10+

### 2. 安装

```bash
git clone git@github.com:siya-xing-hu/MindOS.git
cd MindOS
pip install -r requirements.txt
```

### 3. 启动 oMLX

按 [docs/OMLX_DEPLOY.md](docs/OMLX_DEPLOY.md) 启动 oMLX 服务，确认：
- `curl http://localhost:8000/v1/models` 能列出 `bge-m3-mlx-fp16` 和 `Qwen2.5-7B-Instruct-4bit`
- embedding 测试返回 dim: 1024

### 4. 启动 MindOS

```bash
python -m src.server
# 或
uvicorn src.server:app --host 0.0.0.0 --port 9000
```

浏览器打开 `http://localhost:9000`。

### 5. 首次使用

首次启动时没有任何知识库。点击右上角「⚙ 管理」→「新建知识库」，填入：
- **kb_name**：英文唯一标识，如 `my_kb`
- **显示名称**：如 `我的知识库`
- **workspace**：存放 .md 文件的目录绝对路径，如 `/home/user/data/my_kb`
- **collection**：Milvus collection 名，如 `kb_my_kb`
- **embedding / LLM**：默认 oMLX + bge-m3-mlx-fp16 + Qwen2.5，按需改

创建后往 workspace 目录放 .md 文件，回到「文档」tab 勾选导入即可。

## 使用

### 管理 tab

- 新建 / 编辑 / 删除知识库（只删配置，Milvus 数据和文件不删）
- **一键复制**：复制 KB 配置，collection 名自动加 `_copy` 后缀，workspace 路径需手动改。适合「多个知识库配置一样、只是数据不同」的场景

### 文档 tab

1. 顶部选择知识库
2. 左侧目录树展示 workspace 下所有 .md 文件
   - 灰点：未入库
   - 绿点：已入库且内容 hash 一致
   - 黄点：已入库但内容变了
3. 勾选要导入的文件（支持全选）
4. 点「导入到知识库」→ 选中的文件切分 + 向量化 + 入库
5. 点「更新知识库」→ 扫描所有已入库文件，更新内容变了的，删除本地已删除的
6. 点击文件名 → 右侧渲染 Markdown 内容

### 搜索 tab

输入查询词，返回 top-10 相关 chunk，高亮匹配词。展示标题 + section 路径 + 分数。

### 问答 tab

输入问题，流式返回 LLM 答案，下方展示引用来源（点击可跳转到文档 tab 对应文件）。

## 配置

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MILVUS_HOST` | `localhost` | Milvus 主机 |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `MINDOS_SQLITE_PATH` | `$HOME/data/siya_kb/.mindos.sqlite` | KB 配置库路径 |
| `OMLX_BASE_URL` | `http://localhost:8000` | oMLX 服务地址（仅作前端默认值参考，实际每个 KB 独立配置） |
| `MINDOS_CHUNK_SIZE` | `500` | 切分上限（字符数） |
| `MINDOS_CHUNK_OVERLAP` | `50` | 切分重叠（行数） |
| `MINDOS_SEARCH_TOP_K` | `10` | 搜索返回数 |
| `MINDOS_RAG_TOP_K` | `5` | RAG context 数 |

### 知识库配置

KB 配置存 SQLite `kb_config` 表，通过 Web UI 管理，字段：

| 字段 | 说明 |
| --- | --- |
| `kb_name` | 唯一标识 |
| `display_name` | 显示名 |
| `source` | 数据源类型（目前只有 `file`） |
| `collection` | Milvus collection 名 |
| `workspace` | 数据目录绝对路径 |
| `embedding_provider` / `embedding_model` / `embedding_base_url` | Embedding 配置 |
| `llm_provider` / `llm_model` / `llm_base_url` | LLM 配置 |

### 新增 embedding / LLM provider

1. 写 `src/embedders/{provider}.py` 实现 `BaseEmbedder`，或 `src/llms/{provider}.py` 实现 `BaseLLM`
2. 在对应 `__init__.py` 注册
3. 在 `src/config.py` 的 `SUPPORTED_EMBEDDERS` / `SUPPORTED_LLMS` 加入
4. Web UI 创建/编辑 KB 时即可选用

## Milvus Schema

每个 KB 一个 collection，字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pk` | VARCHAR(128) | 主键，`page_id:chunk_idx` |
| `page_id` | VARCHAR(64) | 文件相对路径的 hash（稳定） |
| `content_hash` | INT64 | 文件内容的 hash，用于增量比对 |
| `title` | VARCHAR(512) | 文件名（去扩展名） |
| `section` | VARCHAR(1024) | section 路径（标题链） |
| `path` | VARCHAR(1024) | workspace 内相对路径 |
| `chunk_idx` | INT64 | 页内 chunk 序号 |
| `text` | VARCHAR(8192) | chunk 原文 |
| `vector` | FLOAT_VECTOR(1024) | bge-m3-mlx-fp16 向量 |

索引：HNSW + IP metric。

## 增量同步机制

不依赖 frontmatter，用文件内容 hash 做版本：

- **page_id**：文件相对路径的 hash（稳定，不随内容变）
- **content_hash**：文件内容的 hash（内容变就变）

入库状态实时从 Milvus 查 `(path, content_hash)` 比对，无需额外状态表：

- Milvus 没该 path → 未入库（灰）
- 有 path 且 hash 一致 → 已入库最新（绿）
- 有 path 但 hash 不一致 → 已入库落后（黄）

refresh 流程：扫本地文件算 hash → 与 Milvus 已有记录比对 → 变了的重入库，本地没的从 Milvus 删。

## 已知限制

- 只索引 .md 文件，附件内容不索引（仅附件名出现在正文里）
- plantuml 代码块在 Web UI 保留为代码块，不渲染成图（可引入 plantuml.js 增强）
- oMLX 只支持 Apple Silicon，未来部署到 Linux 需换 Ollama/OpenAI provider（抽象层已就绪）

## 文档

- [docs/DESIGN.md](docs/DESIGN.md) — 完整设计文档
- [docs/OMLX_DEPLOY.md](docs/OMLX_DEPLOY.md) — oMLX 部署指南
- [docs/SUMMARY.md](docs/SUMMARY.md) — 项目总结与脉络梳理

## License

见 [LICENSE](LICENSE)。
