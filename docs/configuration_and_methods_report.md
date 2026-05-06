# 企业知识助手项目配置与方法细节报告

## 1. 报告目的

本文档用于总结 Enterprise Knowledge Assistant 项目的关键工程配置与方法细节，重点说明数据清洗、文档分块、索引构建、向量检索、关键词召回、混合召回、高精度重排、Embedding 模型选型、Prompt 拼接、生成评估、问题路由、结构化 SQL 查询与拒答机制。

当前系统的主力问答链路为：

```text
用户问题
  -> LangGraph Router
  -> Query Rewrite
  -> BGE-M3 向量召回
  -> BM25 关键词召回
  -> RRF 融合
  -> BGE Cross-Encoder Rerank
  -> Grounded Generation
  -> Citation / Trace / Evaluation
```

默认检索策略为：

```text
vector_bm25_rerank
```

即：

```text
BAAI/bge-m3 Embedding + FAISS + BM25 + RRF + BAAI/bge-reranker-v2-m3
```

## 2. 数据来源与数据清洗

### 2.1 数据来源

系统当前支持三类数据源：

1. 自建模拟企业制度文档。
2. 公开企业 handbook 文档，包括 GitLab Handbook 与 Sourcegraph Handbook。
3. 少量结构化业务数据，存储在 SQLite 中。

默认样例文档位于：

```text
data/raw/
```

包括：

```text
travel_reimbursement.md
leave_policy.md
onboarding.md
engineering_review.md
gitlab_handbook_sample.md
sourcegraph_handbook_sample.md
```

结构化数据由 `src/eka/sql_tool.py` 初始化到：

```text
data/structured/business.sqlite
```

### 2.2 公开 Handbook 拉取

公开 handbook 通过脚本拉取：

```bash
uv run python scripts/fetch_handbooks.py --name gitlab_handbook --limit 200
uv run python scripts/fetch_handbooks.py --name sourcegraph_handbook --limit 200
```

由于远端服务器可能无法直接访问 GitHub，配置中设置了代理前缀：

```yaml
data_sources:
  git_proxy_prefix: "https://gh.llkk.cc/"
```

脚本会将：

```text
https://github.com/...
```

转换为：

```text
https://gh.llkk.cc/https://github.com/...
```

### 2.3 Handbook 清洗与过滤

公开 handbook 原始仓库通常包含大量导航页、索引页、README、license、短页面和非问答价值文档。因此项目提供：

```bash
uv run python scripts/prepare_handbooks.py --limit 300 --min-chars 500
```

清洗逻辑位于 `scripts/prepare_handbooks.py`。

过滤策略包括：

- 跳过太短文档，默认 `min_chars=500`。
- 跳过路径中包含低价值关键词的文件，例如：
  - `node_modules`
  - `.github`
  - `redirect`
  - `changelog`
  - `index.md`
  - `readme.md`
  - `license`
- 保留更适合企业问答的路径关键词，例如：
  - `engineering`
  - `security`
  - `people`
  - `handbook`
  - `product`
  - `team`
  - `communication`
  - `process`
  - `onboarding`
  - `benefits`
  - `finance`

清洗后的文档输出到：

```text
data/raw/prepared/
```

并生成 manifest：

```text
data/raw/external_manifest.json
```

manifest 中记录：

- source name
- source type
- source root
- prepared root
- scanned markdown count
- kept markdown count
- limit
- min_chars

### 2.4 文档 metadata 标准化

文档接入模块位于：

```text
src/eka/ingestion.py
```

每个原始文档被标准化为 `RawDocument`，包含：

```python
doc_id
doc_name
source
text
metadata
```

metadata 中会写入：

```text
suffix
relative_path
source_type
url
```

其中 `source_type` 根据路径推断：

- `mock_policy`
- `gitlab_handbook`
- `sourcegraph_handbook`

URL 也会根据来源路径自动生成，例如：

```text
https://handbook.gitlab.com/...
https://handbook.sourcegraph.com/...
```

## 3. 文档分块策略

### 3.1 为什么使用层级感知分块

企业 handbook 和制度文档天然具有标题层级，例如：

```text
# 差旅报销制度
  ## 实习生差旅标准
  ## 正式员工差旅标准
```

如果只用固定长度切块，会丢失章节边界与语义结构，导致引用不清晰。项目采用 heading-aware chunking，即先解析 Markdown 标题，再在章节内部做长度控制。

### 3.2 标题解析

标题解析位于：

```text
src/eka/chunking.py
```

使用正则：

```python
HEADING_RE = re.compile(r"^(#{1,6})\\s+(.+?)\\s*$", re.MULTILINE)
```

系统会维护一个 `heading_stack`，将标题层级转换为完整路径：

```text
差旅报销制度 > 实习生差旅标准
```

该路径写入：

```python
chunk.section
chunk.metadata["heading_path"]
```

### 3.3 Chunk 大小与 overlap

分块参数定义在 `src/eka/settings.py`：

```python
chunk_size = 900
chunk_overlap = 120
```

含义：

- `chunk_size=900`：单个 chunk 最大字符长度约 900。
- `chunk_overlap=120`：当段落超过 chunk size 需要滑窗切分时，相邻 chunk 保留 120 字符重叠。

选择理由：

- 企业制度文档的一个章节通常较短，900 字符能容纳完整规则描述。
- 过小 chunk 会破坏制度条款上下文。
- 过大 chunk 会引入无关内容，降低 rerank 和 generation 的精度。
- 120 overlap 可以缓解长段落切断造成的信息丢失。

### 3.4 分块流程

分块函数：

```python
chunk_documents(docs, chunk_size=900, chunk_overlap=120)
```

流程：

1. 对每个文档调用 `split_by_headings`。
2. 得到章节级文本。
3. 对章节内部按空行切段。
4. 尽量将多个段落合并到不超过 900 字符的 chunk。
5. 如果单个段落超过 900 字符，则用滑动窗口切分，步长为：

```text
chunk_size - chunk_overlap = 780
```

6. 每个 chunk 使用 `doc_id + section + index + text prefix` 生成稳定 `chunk_id`。

### 3.5 Chunk 对象字段

每个 chunk 结构如下：

```python
Chunk(
    chunk_id=...,
    doc_id=...,
    doc_name=...,
    section=heading_path,
    source=source_path,
    text=chunk_text,
    metadata={
        "relative_path": ...,
        "source_type": ...,
        "url": ...,
        "section_index": ...,
        "heading_path": ...
    }
)
```

## 4. 索引构建配置

索引构建入口：

```bash
uv run eka build-index
```

构建向量索引：

```bash
uv run eka build-index --with-embeddings
```

索引构建代码位于：

```text
src/eka/indexing.py
```

生成产物：

```text
data/indexes/chunks.jsonl
data/indexes/tfidf.pkl
data/indexes/bm25.pkl
data/indexes/faiss.index
data/indexes/embedding_manifest.json
data/indexes/manifest.json
```

其中：

- `chunks.jsonl`：全部 chunk 和 metadata。
- `bm25.pkl`：BM25 索引。
- `tfidf.pkl`：TF-IDF baseline 索引。
- `faiss.index`：BGE-M3 向量索引。
- `embedding_manifest.json`：embedding 模型、维度、chunk 数等信息。

当前 embedding manifest 示例：

```json
{
  "model_name": "BAAI/bge-m3",
  "chunks": 17,
  "dimension": 1024,
  "normalize_embeddings": true
}
```

## 5. Embedding 模型选型

### 5.1 当前模型

当前核心 embedding 模型：

```text
BAAI/bge-m3
```

配置位于 `config/default.yaml`：

```yaml
embedding:
  provider: sentence_transformers
  model_name: BAAI/bge-m3
  device: auto
  batch_size: 32
  normalize_embeddings: true
  index_type: faiss
```

### 5.2 选型原因

选择 BGE-M3 的原因：

1. 支持中英文与多语言，适合中文制度文档 + 英文 handbook 混合知识库。
2. 适合短 query 到长文档 chunk 的语义匹配。
3. 输出向量维度为 1024，能提供较强语义表达能力。
4. 社区在 RAG 场景中使用广泛。
5. 可以与 BGE reranker 组成一致的检索技术栈。

### 5.3 向量归一化与相似度

配置：

```yaml
normalize_embeddings: true
```

FAISS 使用：

```python
faiss.IndexFlatIP(dim)
```

由于 embedding 已归一化，inner product 等价于 cosine similarity。这样检索时可以直接使用内积排序。

### 5.4 Safetensors 加载

由于新版 Transformers 对 `torch<2.6` 加载 `.bin` 权重有限制，项目强制使用 safetensors：

```python
SentenceTransformer(
    settings.embedding_model,
    device=resolve_device(settings.embedding_device),
    model_kwargs={"use_safetensors": True},
)
```

这避免了 `torch.load` 安全限制问题，也更适合公开部署说明。

## 6. 召回与检索算法

检索模块位于：

```text
src/eka/retrieval.py
```

核心类：

```python
HybridRetriever
```

### 6.1 Query Rewrite

多轮追问通过 `memory.py` 保存最近会话主题。当问题较短或以代词开头时，例如：

```text
那住宿标准呢？
```

系统会拼接上一轮 document QA 问题作为 topic hint：

```text
实习生差旅报销标准是什么？ 那住宿标准呢？
```

该方法避免把完整对话历史塞入检索，同时保留追问所需上下文。

### 6.2 支持的检索策略

当前支持：

```text
bm25
tfidf
hybrid
hybrid_rerank
vector
vector_bm25
vector_bm25_rerank
```

默认策略：

```yaml
retrieval:
  strategy: vector_bm25_rerank
```

### 6.3 BGE-M3 向量召回

`vector` 策略使用：

```text
BAAI/bge-m3 -> normalized embedding -> FAISS IndexFlatIP
```

配置：

```yaml
retrieval:
  vector_top_k: 20
```

含义：先从 FAISS 召回最多 20 个向量候选。

### 6.4 BM25 关键词召回

`bm25` 使用 `rank_bm25.BM25Okapi`。

配置：

```yaml
retrieval:
  bm25_top_k: 12
```

BM25 对以下问题很重要：

- 精确制度名。
- 金额、天数、日期。
- 部门名。
- 英文状态词，如 `blocked`。
- 表字段相关问题。

### 6.5 TF-IDF baseline

TF-IDF 是轻量 baseline 和 fallback：

```yaml
retrieval:
  dense_top_k: 12
```

当 FAISS 不存在或 embedding 加载失败时，系统回退到 TF-IDF + BM25。

### 6.6 RRF 融合

`vector_bm25` 与 `vector_bm25_rerank` 使用 RRF 融合向量召回和 BM25 召回。

配置：

```yaml
retrieval:
  rrf_k: 60
```

RRF 公式：

```text
score(doc) += 1 / (k + rank)
```

项目代码中还加入了一个很小的原始分数补充项：

```python
scores[idx] += 1.0 / (k + rank + 1) + min(score, 1.0) * 0.01
```

这样既以 rank fusion 为主，又保留一点原检索分数信息。

### 6.7 文档重复限制

配置：

```yaml
retrieval:
  max_chunks_per_doc: 3
```

作用：避免 top-k 被同一文档过度占据，提高证据多样性。

### 6.8 最终 top-k

配置：

```yaml
retrieval:
  final_top_k: 5
```

最终返回 5 个 evidence 给生成模块、UI 和评测系统。

## 7. 高精度重排方案

### 7.1 当前 rerank 模型

当前高精度重排模型：

```text
BAAI/bge-reranker-v2-m3
```

配置：

```yaml
rerank:
  mode: cross_encoder
  model_name: BAAI/bge-reranker-v2-m3
  device: auto
  top_n: 20
  fallback_mode: lexical
```

### 7.2 Cross-Encoder Rerank 原理

向量检索是 bi-encoder 模式：query 和 document 分别编码，速度快，适合召回。Cross-Encoder 则将 query 和 document pair 一起输入模型，直接输出相关性分数，计算更慢但排序精度更高。

本项目采用：

```text
向量/BM25 高召回 -> RRF 候选融合 -> Cross-Encoder 精排
```

### 7.3 Rerank 输入构造

每个候选 pair 形式：

```python
(query, f"{chunk.section}\
{chunk.text}")
```

即把标题路径和 chunk 文本一起送入 reranker，使模型能够利用章节语义。

### 7.4 Rerank 候选规模

配置：

```yaml
rerank:
  top_n: 20
```

含义：

- 先从召回阶段拿最多 20 个候选。
- 对这 20 个候选做 cross-encoder 打分。
- 再返回 final top 5 给生成模块。

### 7.5 Rerank trace

实际 trace 示例：

```json
{
  "requested_strategy": "vector_bm25_rerank",
  "vector_available": true,
  "embedding_model": "BAAI/bge-m3",
  "rerank_mode": "cross_encoder",
  "rerank_model": "BAAI/bge-reranker-v2-m3",
  "candidate_count": 17,
  "rerank_latency_ms": 90.25,
  "rerank_fallback": false
}
```

### 7.6 Rerank fallback

如果 cross-encoder 加载失败或推理失败，系统回退到 lexical rerank。

Lexical rerank 特征包括：

- query term coverage。
- section title bonus。
- 原始召回分数。

## 8. Prompt 拼接与生成策略

生成模块位于：

```text
src/eka/generation.py
```

### 8.1 Prompt 模板

系统 prompt 模板：

```text
你是企业知识助手。只能依据给定证据回答。
如果证据不足，明确说不知道。回答要简洁，关键结论必须在句末引用来源编号，例如 [1]。
不要使用证据之外的事实、数字、人名、政策或推断。

问题：{question}

证据：
{context}
```

### 8.2 Evidence context 拼接

每个证据块拼接为：

```text
[1] {doc_name} / {section} / {source}
{chunk.text}

[2] ...
```

实现函数：

```python
def _context(evidences):
    for idx, ev in enumerate(evidences, 1):
        lines.append(f"[{idx}] {doc_name} / {section} / {source}\
{text}")
```

这样 LLM 可以直接用 `[1]`、`[2]` 引用证据。

### 8.3 生成模式

支持三种模式：

```text
extractive
deepseek
openai
```

默认：

```yaml
generation:
  mode: extractive
```

DeepSeek 配置：

```yaml
generation:
  deepseek_base_url: "https://api.deepseek.com"
  deepseek_model: "deepseek-chat"
  max_tokens: 800
  temperature: 0.0
```

环境变量：

```bash
export EKA_GENERATION_MODE=deepseek
export DEEPSEEK_API_KEY=...
```

### 8.4 Extractive fallback

当没有 LLM key 或 LLM 调用失败时，系统使用 extractive composer：

1. 从 top evidence 中选择最多 3 个相关 evidence。
2. 将 chunk 切成句子。
3. 根据问题类型选择最相关句子。
4. 自动附加引用编号。

例如：

```text
实习生住宿标准为一线城市每晚不超过 350 元，其他城市每晚不超过 260 元。 [1]
```

### 8.5 Grounding score

生成前先计算证据充分性：

```python
score = lexical_overlap * 0.7 + max_retrieval_score * 3.0
```

配置阈值：

```yaml
generation:
  min_grounding_score: 0.18
```

低于阈值时拒答：

```text
我不知道。当前知识库中没有足够证据回答这个问题。
```

## 9. 生成结果评估与 Grounding 校验

Grounding 模块位于：

```text
src/eka/grounding.py
```

### 9.1 Unsupported numbers

检查回答中的数字是否出现在证据中。引用编号 `[1]` 和列表序号 `1.` 会先被清理，避免误报。

用途：防止模型编造金额、日期、天数等企业制度关键数字。

### 9.2 Citation precision

检查回答中的引用编号是否对应实际 evidence。

如果回答引用了 `[3]`，但只提供了两个 evidence，则 citation precision 会降低。

### 9.3 Lexical support

计算回答中的词项有多少能被证据覆盖。

当前 grounded 判断：

```python
grounded = not unsupported_numbers and lexical_support >= 0.35
```

### 9.4 Eval 指标

离线评测位于：

```text
src/eka/evaluation.py
```

主要指标：

- `route_accuracy`：路由是否正确。
- `retrieval_hit_at_k`：预期文档是否出现在 retrieved chunks 中。
- `mrr`：预期文档排名倒数均值。
- `citation_rate`：回答是否带引用。
- `refusal_hit_rate`：不可回答问题是否拒答。
- `answer_contains_expected`：回答是否包含预期关键词。

评测命令：

```bash
uv run eka eval --strategy vector_bm25_rerank
```

多策略对比：

```bash
uv run eka eval-compare --strategies bm25,tfidf,hybrid,hybrid_rerank,vector,vector_bm25,vector_bm25_rerank
```

当前对比结果摘要：

```text
bm25                hit@k=1.0 mrr=1.0 answer_hit=1.0
tfidf               hit@k=1.0 mrr=1.0 answer_hit=1.0
hybrid              hit@k=1.0 mrr=1.0 answer_hit=1.0
hybrid_rerank       hit@k=1.0 mrr=1.0 answer_hit=1.0
vector              hit@k=1.0 mrr=1.0 answer_hit=0.857
vector_bm25         hit@k=1.0 mrr=1.0 answer_hit=1.0
vector_bm25_rerank  hit@k=1.0 mrr=1.0 answer_hit=1.0
```

## 10. 路由设计

路由模块位于：

```text
src/eka/router.py
```

使用 LangGraph 实现受控 workflow。

### 10.1 Route 类型

系统定义四类路由：

```text
document_qa
sql
clarify
refuse
```

### 10.2 文档问答路由

默认大多数企业制度、流程、研发规范、handbook 问题进入：

```text
document_qa
```

执行链路：

```text
query rewrite -> vector/BM25 retrieval -> RRF -> rerank -> grounded generation
```

### 10.3 SQL 路由

包含以下关键词的问题会进入 SQL 分支：

```python
SQL_HINTS = (
    "销售额",
    "报销最多",
    "报销最高",
    "哪个部门报销",
    "blocked",
    "阻塞",
    "项目状态",
)
```

SQL 分支用于回答结构化业务问题，例如：

```text
上个月销售额最高的是哪个区域？
哪些项目处于 blocked 状态？
```

### 10.4 澄清路由

非常短或只有指代词的问题进入澄清：

```python
CLARIFY_HINTS = ("这个", "那个", "这些", "他们", "它", "怎么办", "怎么处理")
```

返回：

```text
我需要再确认一下：你想查询哪一类制度、时间范围或业务指标？
```

### 10.5 拒答路由

明显知识库外问题进入拒答：

```python
OUT_OF_SCOPE_HINTS = ("天气", "股票", "彩票", "娱乐新闻")
```

破坏性 SQL 请求也直接拒答：

```python
DESTRUCTIVE_SQL_HINTS = ("删除", "删掉", "drop", "truncate", "update", "insert", "alter")
```

例如：

```text
删除 sales_summary 表
```

返回：

```text
我无法回答这个问题。它不属于当前企业知识库或结构化业务数据范围。
```

## 11. 结构化 SQL 查询

### 11.1 SQL 数据表

SQLite 中有三张表：

```text
reimbursement_records
sales_summary
project_status
```

### 11.2 Text-to-SQL

SQL agent 位于：

```text
src/eka/sql_agent.py
```

DeepSeek 根据 schema 生成 JSON：

```json
{
  "is_sql": true,
  "sql": "SELECT ...",
  "reason": "...",
  "needs_clarification": false
}
```

### 11.3 SQL Guard

SQL Guard 位于：

```text
src/eka/sql_guard.py
```

校验规则：

1. SQL 不为空。
2. 不允许多语句。
3. 必须以 `SELECT` 开头。
4. 禁止破坏性关键字：
   - insert
   - update
   - delete
   - drop
   - alter
   - create
   - replace
   - attach
   - pragma
   - vacuum
5. 表名必须在白名单内。
6. 如果没有 `LIMIT`，自动补：

```sql
LIMIT 20
```

### 11.4 SQL trace

示例：

```json
{
  "sql_mode": "llm_guarded",
  "guard_passed": true,
  "guard_reason": null,
  "generated_sql": "SELECT region, sales_amount FROM sales_summary WHERE month = '2026-04' ORDER BY sales_amount DESC LIMIT 1",
  "rows": 1,
  "router": "sql_tool"
}
```

## 12. 关键配置总览

当前核心配置：

```yaml
retrieval:
  strategy: vector_bm25_rerank
  dense_top_k: 12
  bm25_top_k: 12
  vector_top_k: 20
  final_top_k: 5
  rrf_k: 60
  rerank: true
  max_chunks_per_doc: 3

embedding:
  model_name: BAAI/bge-m3
  batch_size: 32
  normalize_embeddings: true

rerank:
  mode: cross_encoder
  model_name: BAAI/bge-reranker-v2-m3
  top_n: 20

generation:
  mode: extractive
  min_grounding_score: 0.18
  deepseek_model: deepseek-chat
  max_tokens: 800
  temperature: 0.0

sql:
  mode: llm_guarded
  max_rows: 20
```

## 13. 运行与复现

初始化数据：

```bash
uv run eka init-data
```

构建基础索引：

```bash
uv run eka build-index
```

构建 BGE-M3 + FAISS 向量索引：

```bash
export HF_ENDPOINT=https://hf-mirror.com
uv run eka build-index --with-embeddings
```

检查系统：

```bash
uv run eka doctor
```

问答：

```bash
uv run eka ask "实习生住宿标准是多少？" --strategy vector_bm25_rerank
```

评测：

```bash
uv run eka eval-compare --strategies bm25,tfidf,hybrid,hybrid_rerank,vector,vector_bm25,vector_bm25_rerank
```

## 14. 小结

本项目的配置与方法可以概括为：

1. 数据层：Markdown / handbook / SQLite 多源接入，保留 source_type、URL、heading_path 等 metadata。
2. 分块层：基于 Markdown 标题层级的 heading-aware chunking，chunk size 900，overlap 120。
3. 召回层：BGE-M3 向量召回 + BM25 关键词召回，TF-IDF 保留为 baseline 与 fallback。
4. 融合层：RRF 融合向量和关键词候选。
5. 精排层：BGE Cross-Encoder Rerank 对候选证据做高精度重排。
6. 生成层：DeepSeek grounded generation + extractive fallback。
7. 校验层：unsupported numbers、citation precision、lexical support。
8. 路由层：LangGraph 控制 document QA、SQL、clarify、refuse 四类路径。
9. SQL 层：DeepSeek Text-to-SQL + SQL Guard + SQLite read-only execution。
10. 评测层：离线 eval 与多策略 eval-compare，持续验证检索、生成、拒答与路由效果。

该设计使系统不只是普通 RAG demo，而是一个围绕企业知识问答稳定性、可解释性、可回退性和可评测性构建的完整工程原型。