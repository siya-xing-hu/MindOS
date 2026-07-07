# MindOS 项目总结

本文档是 MindOS 从需求到设计的完整脉络梳理，可作为项目背景资料或个人学习记录。

## 1. 项目定位

MindOS 是一个本地多知识库系统：把任意目录下的 Markdown 文档导入到向量数据库，提供语义搜索和 RAG 问答，通过 Web UI 访问。

核心特点：

- **多知识库**：一个实例支持多个独立 KB，每个 KB 独立配置（数据目录、embedding、LLM）
- **配置可视化**：KB 配置通过 Web UI 管理，存 SQLite，支持一键复制
- **模型可混用**：每个 KB 独立绑定 embedding / LLM，本地 oMLX 或外部 API 均可
- **单库检索**：每个 KB 独立搜索/问答，不做跨库
- **手动管理**：前端目录树勾选 + 三色入库状态标记，手动触发导入/更新
- **应用与数据分离**：数据路径由用户在 KB 配置里指定，应用仓库可公开

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI (浏览器)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 文档 tab │  │ 搜索 tab │  │ 问答 tab │  │ 管理 tab │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP
┌──────────────────────┴──────────────────────────────────────┐
│                  FastAPI Server (server.py)                  │
│    /api/kbs  /api/{kb}/tree /file /ingest /search /ask      │
└──────┬───────────────┬───────────────┬──────────────────────┘
       │               │               │
┌──────┴──────┐  ┌─────┴──────┐  ┌─────┴──────┐
│ file_reader │  │  Embedder  │  │    LLM     │
│ (扫目录 .md)│  │ (向量化)   │  │ (问答生成) │
└──────┬──────┘  └─────┬──────┘  └─────┬──────┘
       │               │               │
       │         ┌─────┴──────┐         │
       │         │  Milvus    │         │
       └────────→│ (向量存储) │←────────┘
                 └────────────┘

KB 配置 ──→ SQLite (kb_config 表)
```

## 3. 技术栈

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 向量库 | Milvus 2.x | localhost:19530，多 collection 物理隔离 |
| KB 配置存储 | SQLite | 单文件零运维，只存 KB 配置 |
| 本地推理 | oMLX | Apple Silicon 专用，托管 embedding + LLM + reranker |
| Embedding | bge-m3-mlx-fp16（经 oMLX `/v1/embeddings`） | 1024 维，中文优秀 |
| LLM | Qwen2.5-7B-Instruct-4bit MLX（经 oMLX `/v1/chat/completions`） | 4bit 量化，Mac 流畅跑 |
| 后端 | FastAPI | Python 异步 Web 框架 |
| 前端 | 单文件 HTML + 原生 JS | 无构建链 |
| Markdown 渲染 | marked.js | 浏览器端渲染 |

## 4. 目录结构

```
MindOS/
├── README.md
├── requirements.txt
├── .gitignore
├── docs/
│   ├── DESIGN.md          # 完整设计文档
│   ├── OMLX_DEPLOY.md     # oMLX 部署指南
│   └── SUMMARY.md         # 本文
└── src/
    ├── config.py          # 全局配置（Milvus / oMLX / 切分参数 / 支持的 provider 列表）
    ├── kb_store.py        # SQLite: kb_config 表 CRUD
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

## 5. 关键设计决策

### 决策 1：多 KB 隔离 vs 单库

**选**：多 KB 隔离。每个 KB = 一个 Milvus collection + 一套 embedder/llm 配置。

**理由**：
- 不同 KB 可以用不同 embedding 模型，维度不同时 Milvus collection 维度固定，天然要分库
- 敏感数据可用本地模型，非敏感可外部 API，每 KB 独立绑定
- 一个 KB 出问题不影响其他

### 决策 2：跨库搜索

**选**：不支持，单库检索。

**理由**：
- 不同 embedding 模型的相似度分数不可直接比较，跨库需要 reranker 重排，复杂度高
- 实际场景中用户在单一 KB 内搜索就够了

### 决策 3：同文档多 KB 导入

**选**：支持，去重范围是 KB 内。

**理由**：Milvus collection 本身就是隔离边界，同一文档导入到多个 KB 各存一份，互不干扰。

### 决策 4：手动管理 vs 自动扫描

**选**：手动管理。

**理由**：
- 用户需要精确控制哪些文档入库
- 前端目录树勾选 + 三色状态标记（未入库/已入库最新/已入库落后）符合直觉
- 自动扫描可能导致误导入或性能问题

### 决策 5：配置存 SQLite vs 代码硬编码

**选**：SQLite `kb_config` 表，Web UI 管理。

**理由**：
- 部署方无需改代码就能新建/修改/删除 KB
- **一键复制**：复制 KB 配置，collection 名自动加后缀，适合「多个知识库配置一样、只是数据不同」的场景
- 应用启动时空库引导，首次创建 KB 后即可使用

### 决策 6：入库状态实时比对 vs 状态表

**选**：实时比对，不维护单独的状态表。

**理由**：
- 算 hash 极快（1MB 文件约 1ms），Markdown 文档普遍几十 KB，微秒级
- Milvus 标量查询通过 `list_indexed()` 分页查全量 `(path, content_hash)`，内存比对
- SQLite 只存 KB 配置，不存状态，避免数据一致性维护
- 真慢了再加缓存层，不过度设计

### 决策 7：不依赖 frontmatter，用文件内容 hash 做版本

**选**：page_id 用文件相对路径的 hash（稳定），content_hash 用文件内容的 hash（随内容变）。

**理由**：
- 不依赖数据源写 frontmatter，通用性强
- hash 计算便宜，性能不是瓶颈
- page_id 与 content_hash 分离：page_id 稳定便于按文件 upsert，content_hash 变化触发重新入库

### 决策 8：不再有 adapter 抽象

**选**：删除 adapter 层，统一用 `file_reader.py` 处理所有数据源。

**理由**：
- 所有数据源最终都是「扫目录下 .md 文件」
- 不依赖 frontmatter（用文件内容 hash 做版本）
- 没有真实的多态需求
- 未来如果真有特殊数据源（如代码文件按函数切分），再按需加抽象

### 决策 9：oMLX vs Ollama

**选**：oMLX。

**理由**：
- 开发环境是 Mac，oMLX 性能更好（MLX + Metal）
- embedding + LLM + reranker 一站式，Ollama 只管 LLM
- BGE-M3 原生支持，与选型对齐
- KV cache SSD 持久化，RAG 长对话省 token
- 抽象层已解耦，未来要换 Ollama 写个 provider 即可

**风险**：
- oMLX 只支持 Apple Silicon，未来部署到 Linux 服务器要换后端
- 缓解：BaseLLM/BaseEmbedder 抽象 + 配置驱动，切换成本可控

### 决策 10：应用与数据分离

**选**：数据路径由用户在 KB 配置里指定。

**理由**：
- 应用仓库要公开，数据是敏感的不能进 git
- 部署方自行在 Web UI 配置 workspace 路径，灵活
- 应用代码与数据完全解耦

## 6. Milvus Schema

每个 KB 一个 collection，schema 结构一致，仅 vector 维度随 embedder 变化。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pk` | VARCHAR(128) | 主键，`page_id:chunk_idx`，KB 内去重 |
| `page_id` | VARCHAR(64) | 文件相对路径的 hash（稳定，不随内容变） |
| `content_hash` | INT64 | 文件内容 hash，增量比对用 |
| `title` | VARCHAR(512) | 文件名（去扩展名） |
| `section` | VARCHAR(1024) | section 路径，如 `接口说明 > 请求参数` |
| `path` | VARCHAR(1024) | workspace 内相对路径 |
| `chunk_idx` | INT64 | 页内 chunk 序号 |
| `text` | VARCHAR(8192) | chunk 原文 |
| `vector` | FLOAT_VECTOR(dim) | embedding 向量 |

索引：HNSW + IP metric（bge-m3-mlx-fp16 推荐，需 L2 normalize）。

## 7. 增量同步机制

不依赖 frontmatter，用文件内容 hash 做版本：

- **page_id**：文件相对路径的 MD5 前 12 位 hex 转整数（稳定，文件内容变 page_id 不变）
- **content_hash**：文件内容的 MD5 前 12 位 hex 转整数（内容变就变）

入库状态实时从 Milvus 查 `(path, content_hash)` 比对：

- Milvus 没该 path → 未入库（灰）
- 有 path 且 hash 一致 → 已入库最新（绿）
- 有 path 但 hash 不一致 → 已入库落后（黄）

refresh 流程：扫本地文件算 hash → 与 Milvus 已有记录比对 → 变了的重入库，本地没的从 Milvus 删。

## 8. 数据流

```
workspace 目录（.md 文件）
       │
       │ file_reader 扫目录 + 算 content hash
       ↓
┌─────────────┐         ┌─────────────┐
│   oMLX      │←────────│  embedder   │
│ /v1/embeds  │         └──────┬──────┘
└─────────────┘                │
       ↑                       ↓
       │                ┌─────────────┐
       │                │   Milvus    │
       │                │ kb_{name}   │
       │                └──────┬──────┘
       │                       │ 检索
       │                       ↓
┌─────────────┐         ┌─────────────┐
│   oMLX      │←────────│    rag.py   │
│ /v1/chat    │         └──────┬──────┘
└─────────────┘                │
                               ↓
                        ┌─────────────┐
                        │   Web UI    │
                        │ 搜索/问答   │
                        └─────────────┘
```

## 9. 切分策略

Markdown header-aware 切分（chunker.py）：

1. 按 `#`/`##`/`###` 标题切分
2. 每个 chunk 维护 section 路径（如 `接口说明 > 请求参数`）
3. 单 chunk 上限 ~500 字符，超出则按段落二次切分
4. 相邻 chunk 50 行重叠
5. plantuml 代码块作为整体 chunk，不拆分
6. frontmatter 在 file_reader 阶段已剥离，不参与切分

## 10. API 设计

### KB 管理

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/kbs` | GET | 列出所有知识库配置 |
| `/api/kbs` | POST | 创建知识库 |
| `/api/kbs/{kb_name}` | PUT | 更新知识库配置 |
| `/api/kbs/{kb_name}` | DELETE | 删除知识库（只删配置，Milvus 数据和文件不删） |
| `/api/kbs/{kb_name}/duplicate?new_name=xxx` | POST | 一键复制知识库配置 |
| `/api/options` | GET | 返回支持的 source / embedder / llm 列表 |

### KB 操作

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/{kb}/tree` | GET | 返回 workspace 目录树 + 每个文件的入库状态 |
| `/api/{kb}/file` | GET | 返回某个 md 的原文（前端渲染） |
| `/api/{kb}/ingest` | POST | body: `{files: ["相对路径", ...]}`，导入选中文件 |
| `/api/{kb}/refresh` | POST | 扫描所有已入库文件，更新内容变了的，删除本地已删除的 |
| `/api/{kb}/search` | GET | `?q=xxx&top=10`，语义搜索 |
| `/api/{kb}/ask` | POST | `{question: "xxx"}`，RAG 流式问答（SSE） |

## 11. Web UI

四 tab 切换：

- **文档 tab**：左侧目录树（三色状态标记 + checkbox 多选），右侧 Markdown 渲染，顶部「导入到知识库」/「更新知识库」按钮
- **搜索 tab**：搜索框 + top-10 结果列表，每条结果含 chunk 原文（高亮）+ 标题 + section 路径 + 分数
- **问答 tab**：问题输入框 + 流式答案展示区 + 引用来源列表（可点击跳转文档 tab）
- **管理 tab**：知识库列表 + 新建/编辑/删除/复制按钮

## 12. 扩展性

### 新增 embedding / LLM provider

1. 写 `src/embedders/{provider}.py` 实现 `BaseEmbedder`，或 `src/llms/{provider}.py` 实现 `BaseLLM`
2. 在对应 `__init__.py` 注册
3. 在 `src/config.py` 的 `SUPPORTED_EMBEDDERS` / `SUPPORTED_LLMS` 加入
4. Web UI 创建/编辑 KB 时即可选用

典型场景：未来部署到非 Mac 环境，加 Ollama 或 OpenAI provider 即可，不碰现有代码。

### 新增数据源类型

目前只有 `file`（扫目录下 .md）。如果未来有特殊数据源（如代码文件按函数切分），再加抽象层，目前不过度设计。

## 13. 实现计划

### Phase 1: 基础设施 ✅
- config.py + kb_store.py + kb_registry.py
- milvus_store.py（多 collection 管理）
- file_reader.py（扫目录 + content hash）
- chunker.py（header-aware 切分）
- embedders/omlx.py

### Phase 2: 入库与搜索 ✅
- ingest.py（手动导入 + refresh）
- search.py
- /api/{kb}/tree /file /ingest /refresh /search

### Phase 3: Web UI ✅
- templates/index.html 四 tab
- 文档 tab 目录树 + md 渲染
- 搜索 tab 结果展示
- 管理 tab KB 配置 CRUD + 一键复制

### Phase 4: RAG 问答 ✅
- llms/omlx.py（走 oMLX /v1/chat/completions，流式）
- rag.py
- /api/{kb}/ask（SSE 流式）
- 问答 tab UI

## 14. 待定事项

- oMLX 服务部署方式（.app / homebrew / 源码）及启动端口确认
- oMLX 托管的 bge-m3-mlx-fp16 模型下载（通过 oMLX admin dashboard 从 HuggingFace 拉）
- oMLX 托管的 LLM 选型（Qwen2.5-7B-Instruct-4bit / 其他 MLX 格式模型）
- 切分参数调优（chunk size / overlap，跑通后用实际数据调）
- plantuml 在 Web UI 的渲染方案（保留代码块 / 引入 plantuml.js）
- 未来若需部署到非 Mac 环境，llms/embedders 层加 Ollama/OpenAI provider 可切换

## 15. 关键经验

### 设计层面

1. **抽象要早，但不要过度**：embedder/llm 抽象在多 KB 需求出现时是必要的，但单数据源单模型场景下不必先建抽象。adapter 抽象被删除就是这个教训——所有数据源最终都是扫目录下 .md，没有真实多态需求
2. **配置驱动多态**：KB 配置存 SQLite，新增 KB 零代码改动，还支持一键复制
3. **状态用实时比对**：算 hash 极快，Milvus 标量查询也够用，不必为了状态额外维护 SQLite 表
4. **应用与数据分离**：从一开始就避免数据进 git，数据路径由用户在 KB 配置里指定

### 选型层面

1. **本地优先**：敏感数据不出门，oMLX + Milvus 全本地栈
2. **Mac 优化**：oMLX 比 Ollama 在 Apple Silicon 上性能更好
3. **一站式**：oMLX 托管 embedding + LLM + reranker，省组件
4. **可切换**：抽象层让未来换 Ollama/OpenAI 成本可控

## 16. 文档索引

| 文档 | 用途 |
| --- | --- |
| [README.md](../README.md) | 项目说明 + 部署使用 |
| [docs/DESIGN.md](DESIGN.md) | 完整设计文档 |
| [docs/OMLX_DEPLOY.md](OMLX_DEPLOY.md) | oMLX 本地推理服务部署指南 |
| [docs/SUMMARY.md](SUMMARY.md) | 项目总结与脉络梳理（本文） |
