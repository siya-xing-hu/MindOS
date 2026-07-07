# MindOS 设计文档

## 1. 背景与目标

搭建一个本地多知识库系统，把任意目录下的 Markdown 文档导入到向量数据库，提供语义搜索和 RAG 问答能力，通过 Web UI 访问。

### 核心诉求

- **多知识库**：一个应用实例支持多个独立知识库，每个 KB 独立配置（数据目录、embedding、LLM）
- **配置可视化**：知识库配置通过 Web UI 管理，存 SQLite，支持一键复制
- **模型可混用**：每个 KB 独立绑定 embedding / LLM，本地 oMLX 或外部 API 均可
- **单库检索**：每个 KB 独立搜索/问答，不做跨库；同一文档可导入到多个 KB
- **手动管理**：前端目录树勾选 + 三色入库状态标记，手动触发导入/更新
- **本地渲染**：文档在 Web UI 内渲染，不跳转外部链接
- **可公开**：应用代码与数据完全分离，应用仓库可公开，数据路径由用户在 KB 配置里指定

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

## 3. 多知识库设计

### 知识库（KB）作为隔离单位

每个知识库独立拥有：
- 一个 Milvus collection（物理隔离）
- 一个数据目录 workspace（存放 .md 文件）
- 一个 embedder（向量化模型，决定 collection 维度）
- 一个 LLM（RAG 问答模型）

### 配置存 SQLite，前端管理

KB 配置不硬编码在代码里，存 SQLite `kb_config` 表，通过 Web UI 管理。这带来几个好处：

- 部署方无需改代码就能新建/修改/删除 KB
- **一键复制**：复制 KB 配置，collection 名自动加后缀，workspace 路径手动改。适合「多个知识库配置一样、只是数据不同」的场景
- 应用启动时空库引导，首次创建 KB 后即可使用

### kb_config 表结构

```sql
CREATE TABLE kb_config (
    kb_name            TEXT PRIMARY KEY,
    display_name       TEXT NOT NULL,
    source             TEXT NOT NULL,         -- 数据源类型，目前只有 file
    collection         TEXT NOT NULL,         -- Milvus collection 名
    workspace          TEXT NOT NULL,         -- 数据目录绝对路径
    embedding_provider TEXT NOT NULL,
    embedding_model    TEXT NOT NULL,
    embedding_base_url TEXT,
    llm_provider       TEXT NOT NULL,
    llm_model          TEXT NOT NULL,
    llm_base_url       TEXT,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);
```

### Embedding 维度隔离

不同 embedding 模型向量维度不同（bge-m3-mlx-fp16 是 1024，OpenAI text-embedding-3-large 是 3072）。Milvus 一个 collection 的 vector 字段维度固定，因此**不同 embedding 模型必须用不同 collection**——这与「知识库隔离」天然对齐，无需额外处理。

### 同文档多 KB 导入

去重范围是「KB 内」而非全局。同一文档导入到多个知识库时，各 collection 独立存储，互不干扰。Milvus collection 本身就是隔离边界。

## 4. 模块设计

### 目录结构

```
src/
├── config.py          # 全局配置（Milvus / oMLX / 切分参数 / 支持的 provider 列表）
├── kb_store.py        # SQLite kb_config 表 CRUD
├── kb_registry.py     # 从 SQLite 加载 KB 配置，装配 embedder / llm / milvus
├── file_reader.py     # 通用文件读取：扫目录 .md + content hash
├── chunker.py         # Markdown header-aware 切分
├── milvus_store.py    # 多 collection 管理（建表/upsert/search）
├── ingest.py          # 手动导入 + refresh
├── search.py          # 语义检索
├── rag.py             # RAG 问答
├── server.py          # FastAPI 路由
├── embedders/
│   ├── base.py        # BaseEmbedder
│   └── omlx.py        # 走 oMLX /v1/embeddings
├── llms/
│   ├── base.py        # BaseLLM
│   └── omlx.py        # 走 oMLX /v1/chat/completions（流式）
└── templates/
    └── index.html     # 单文件 Web UI
```

### 不再有 adapter 抽象

最初设计里有 `adapters/` 抽象层，按数据源（confluence / github / ...）分 adapter。实际分析后发现：

- 所有数据源最终都是「扫目录下 .md 文件」
- 不依赖 frontmatter（用文件内容 hash 做版本）
- 没有真实的多态需求

因此删除 adapter 抽象，统一用 `file_reader.py` 处理所有数据源。未来如果真有特殊数据源（如代码文件按函数切分），再按需加抽象。

### BaseEmbedder

```python
class BaseEmbedder:
    def __init__(self, model: str, base_url: str | None = None):
        self.model = model
        self.base_url = base_url

    def dim(self) -> int:
        """返回向量维度，用于 Milvus schema。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。"""
```

### BaseLLM

```python
class BaseLLM:
    def __init__(self, model: str, base_url: str | None = None):
        self.model = model
        self.base_url = base_url

    def stream(self, prompt: str, context: list[dict]) -> Iterator[str]:
        """基于 context（检索结果）流式生成答案，yield 文本块。"""
```

### kb_registry

按 kb name 从 SQLite 加载配置，按需装配 embedder / llm / milvus store：

```python
def get_embedder(kb_name: str) -> BaseEmbedder:
    cfg = get_kb(kb_name)
    return EMBEDDERS[cfg["embedding_provider"]](
        model=cfg["embedding_model"], base_url=cfg.get("embedding_base_url")
    )

def get_milvus(kb_name: str) -> MilvusStore:
    cfg = get_kb(kb_name)
    embedder = get_embedder(kb_name)
    return MilvusStore(cfg["collection"], embedder.dim())
```

## 5. Milvus Schema

每个知识库一个 collection，schema 结构一致，仅 vector 维度随 embedder 变化。

### collection: `kb_{name}`（实际名字由 KB 配置的 collection 字段决定）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pk` | VARCHAR(128) | 主键，`f"{page_id}:{chunk_idx}"`，KB 内去重 |
| `page_id` | VARCHAR(64) | 文件相对路径的 hash（稳定，不随内容变） |
| `content_hash` | INT64 | 文件内容 hash，增量比对用 |
| `title` | VARCHAR(512) | 文件名（去扩展名） |
| `section` | VARCHAR(1024) | section 路径，如 `接口说明 > 请求参数` |
| `path` | VARCHAR(1024) | workspace 内相对路径 |
| `chunk_idx` | INT64 | 页内 chunk 序号 |
| `text` | VARCHAR(8192) | chunk 原文 |
| `vector` | FLOAT_VECTOR(dim) | embedding 向量 |

### 索引

- `vector`：HNSW，metric 用 IP（bge-m3-mlx-fp16 推荐，需 L2 normalize）
- `pk`：主键，支持 upsert 去重

## 6. 增量同步机制

### 不依赖 frontmatter，用文件内容 hash 做版本

- **page_id**：文件相对路径的 MD5 前 12 位 hex 转整数（稳定，文件内容变 page_id 不变）
- **content_hash**：文件内容的 MD5 前 12 位 hex 转整数（内容变就变）

### 入库状态实时比对

不维护单独的状态表，入库状态实时从 Milvus 查 `(path, content_hash)` 比对：

1. 打开目录树时，扫目录算每个文件的 content_hash
2. 从 Milvus 查已入库记录的 `(path, content_hash)`
3. 内存比对得出三色状态：
   - Milvus 没该 path → 未入库（灰）
   - 有 path 且 hash 一致 → 已入库最新（绿）
   - 有 path 但 hash 不一致 → 已入库落后（黄）

### 性能

- 算 hash：1MB 文件约 1ms，Markdown 文档普遍几十 KB，微秒级
- Milvus 标量查询：通过 `list_indexed()` 分页查全量 `(path, content_hash)`，内存比对
- 真慢了再加缓存层，现在不过度设计

## 7. 切分策略

### Markdown header-aware 切分（chunker.py）

1. 按 `#`/`##`/`###` 标题切分
2. 每个 chunk 维护 section 路径（如 `接口说明 > 请求参数`）
3. 单 chunk 上限 ~500 字符，超出则按段落二次切分
4. 相邻 chunk 50 行重叠
5. plantuml 代码块作为整体 chunk，不拆分
6. frontmatter 在 file_reader 阶段已剥离，不参与切分

## 8. 入库流程

### 手动导入（/api/{kb}/ingest）

1. 前端勾选文件，POST 文件相对路径列表
2. 后端逐文件 read_file，取 `page_id` + `content_hash`
3. 与 Milvus 现有记录比对：
   - content_hash 不变 → 跳过
   - content_hash 变了或新文件 → 按 `page_id` 删除 Milvus 旧 chunk，重新切分 + embedding + upsert
4. 返回导入结果（新增/更新/跳过/失败 数量）

### 更新知识库（/api/{kb}/refresh）

1. 从 Milvus 查所有已入库的 `(path, content_hash)`
2. 扫本地 workspace，算每个文件的 content_hash
3. 本地存在但 hash 变了 → 重新入库（同 ingest 流程）
4. 本地不存在 → 从 Milvus 删除该 path 的所有 chunk
5. 本地新增 → 入库

## 9. 检索流程

### 语义搜索（/api/{kb}/search）

1. query → embedder 向量化
2. Milvus top-K（默认 10）
3. 返回结果：chunk 原文 + 标题 + section 路径 + 文件相对路径 + 分数
4. 前端展示，点击「查看」跳到文档 tab 并定位到对应文件 + section

### RAG 问答（/api/{kb}/ask）

1. query → 搜索 top-5 作 context
2. 拼 prompt 调用 LLM
3. 流式返回答案 + 引用来源列表（每条引用含文件路径 + section，可点击跳转）

## 10. Web UI

### 布局

顶部：知识库切换下拉 + 「⚙ 管理」按钮
主体：四 tab 切换（文档 / 搜索 / 问答 / 管理）

### 文档 tab

- 左侧：workspace 目录树（可折叠）
  - 每个文件旁显示入库状态三色点：
    - 灰点：未入库
    - 绿点：已入库且 content_hash 一致
    - 黄点：已入库但内容变了
  - 支持 checkbox 多选（按目录批量选）
- 右侧：选中文件的 Markdown 渲染（marked.js，自动剥离 frontmatter）
- 顶部操作区：
  - 「导入到知识库」按钮：导入选中的文件
  - 「更新知识库」按钮：扫描所有已入库文件，更新内容变了的，删除本地已删除的

### 搜索 tab

- 搜索框 + top-10 结果列表
- 每条结果：chunk 原文（高亮） + 标题 + section 路径 + 分数

### 问答 tab

- 问题输入框
- 流式答案展示区
- 引用来源列表（每条可点击跳到文档 tab 对应文件 + section）

### 管理 tab

- 知识库列表：每条显示 display_name + kb_name + workspace + 模型配置
- 操作按钮：编辑 / 复制 / 删除
- 「新建知识库」按钮 → 弹出表单
- 表单字段：kb_name / display_name / workspace / collection / embedding 配置 / llm 配置
- **复制**：基于当前 KB 预填表单，collection 名自动加 `_copy` 后缀，workspace 需手动改

## 11. API 设计

### KB 管理

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/kbs` | GET | 列出所有知识库配置 |
| `/api/kbs` | POST | 创建知识库 |
| `/api/kbs/{kb_name}` | PUT | 更新知识库配置 |
| `/api/kbs/{kb_name}` | DELETE | 删除知识库（只删配置，Milvus 数据和文件不删） |
| `/api/kbs/{kb_name}/duplicate?new_name=xxx` | POST | 一键复制知识库配置 |
| `/api/options` | GET | 返回支持的 source / embedder / llm 列表 |

### KB 操作（按当前选中的 KB）

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/{kb}/tree` | GET | 返回 workspace 目录树 + 每个文件的入库状态 |
| `/api/{kb}/file?path=xxx` | GET | 返回某个 md 的原文（前端渲染） |
| `/api/{kb}/ingest` | POST | body: `{files: ["相对路径", ...]}`，导入选中文件 |
| `/api/{kb}/refresh` | POST | 扫描所有已入库文件，更新内容变了的，删除本地已删除的 |
| `/api/{kb}/search` | GET | `?q=xxx&top=10`，语义搜索 |
| `/api/{kb}/ask` | POST | `{question: "xxx"}`，RAG 流式问答（SSE） |

## 12. 扩展性

### 新增 embedding / LLM provider

1. 写 `src/embedders/{provider}.py` 实现 `BaseEmbedder`，或 `src/llms/{provider}.py` 实现 `BaseLLM`
2. 在对应 `__init__.py` 注册
3. 在 `src/config.py` 的 `SUPPORTED_EMBEDDERS` / `SUPPORTED_LLMS` 加入
4. Web UI 创建/编辑 KB 时即可选用

典型场景：未来部署到非 Mac 环境，加 Ollama 或 OpenAI provider 即可，不碰现有代码。

### 新增数据源类型

目前只有 `file`（扫目录下 .md）。如果未来有特殊数据源（如代码文件按函数切分），再加抽象层，目前不过度设计。

## 13. 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 向量库 | Milvus 2.x | localhost:19530 |
| KB 配置存储 | SQLite | 单文件零运维 |
| 本地推理服务 | oMLX | Apple Silicon 专用，托管 embedding + LLM + reranker |
| Embedding | bge-m3-mlx-fp16（经 oMLX `/v1/embeddings`） | 1024 维 |
| LLM | Qwen2.5-7B-Instruct-4bit MLX（经 oMLX `/v1/chat/completions`） | 本地，敏感数据用 |
| 后端 | FastAPI | Python 异步 Web 框架 |
| 前端 | 单文件 HTML + 原生 JS | 无构建链 |
| Markdown 渲染 | marked.js | 浏览器端渲染 |

## 14. 实现计划

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

## 15. 待定事项

- oMLX 服务部署方式（.app / homebrew / 源码）及启动端口确认
- oMLX 托管的 bge-m3-mlx-fp16 模型下载（通过 oMLX admin dashboard 从 HuggingFace 拉）
- oMLX 托管的 LLM 选型（Qwen2.5-7B-Instruct-4bit / 其他 MLX 格式模型）
- 切分参数调优（chunk size / overlap，跑通后用实际数据调）
- plantuml 在 Web UI 的渲染方案（保留代码块 / 引入 plantuml.js）
- 未来若需部署到非 Mac 环境，llms/embedders 层加 Ollama/OpenAI provider 可切换
