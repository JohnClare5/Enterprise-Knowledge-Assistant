# Retrieval Strategy Comparison

- run_at: `2026-05-03T07:12:31Z`
- best_strategy: `bm25`

| strategy | route_acc | hit@k | mrr | citation_rate | refusal_hit | answer_hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 **best** | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |
| tfidf | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |
| hybrid | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |
| hybrid_rerank | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |
| vector | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 0.857 |
| vector_bm25 | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |
| vector_bm25_rerank | 1.0 | 1.0 | 1.0 | 0.571 | 1.0 | 1.0 |

## Case-Level Diff

### 实习生差旅报销标准是什么？
- `bm25` route=document_qa doc_rank=1
- `tfidf` route=document_qa doc_rank=1
- `hybrid` route=document_qa doc_rank=1
- `hybrid_rerank` route=document_qa doc_rank=1
- `vector` route=document_qa doc_rank=1
- `vector_bm25` route=document_qa doc_rank=1
- `vector_bm25_rerank` route=document_qa doc_rank=1

### 实习生住宿标准是多少？
- `bm25` route=document_qa doc_rank=1
- `tfidf` route=document_qa doc_rank=1
- `hybrid` route=document_qa doc_rank=1
- `hybrid_rerank` route=document_qa doc_rank=1
- `vector` route=document_qa doc_rank=1
- `vector_bm25` route=document_qa doc_rank=1
- `vector_bm25_rerank` route=document_qa doc_rank=1

### 年假制度总结成三条
- `bm25` route=document_qa doc_rank=1
- `tfidf` route=document_qa doc_rank=1
- `hybrid` route=document_qa doc_rank=1
- `hybrid_rerank` route=document_qa doc_rank=1
- `vector` route=document_qa doc_rank=1
- `vector_bm25` route=document_qa doc_rank=1
- `vector_bm25_rerank` route=document_qa doc_rank=1

### 代码评审必须检查哪些内容？
- `bm25` route=document_qa doc_rank=1
- `tfidf` route=document_qa doc_rank=1
- `hybrid` route=document_qa doc_rank=1
- `hybrid_rerank` route=document_qa doc_rank=1
- `vector` route=document_qa doc_rank=1
- `vector_bm25` route=document_qa doc_rank=1
- `vector_bm25_rerank` route=document_qa doc_rank=1

### 上个月销售额最高的是哪个区域？
- `bm25` route=sql doc_rank=None
- `tfidf` route=sql doc_rank=None
- `hybrid` route=sql doc_rank=None
- `hybrid_rerank` route=sql doc_rank=None
- `vector` route=sql doc_rank=None
- `vector_bm25` route=sql doc_rank=None
- `vector_bm25_rerank` route=sql doc_rank=None

### 哪些项目处于 blocked 状态？
- `bm25` route=sql doc_rank=None
- `tfidf` route=sql doc_rank=None
- `hybrid` route=sql doc_rank=None
- `hybrid_rerank` route=sql doc_rank=None
- `vector` route=sql doc_rank=None
- `vector_bm25` route=sql doc_rank=None
- `vector_bm25_rerank` route=sql doc_rank=None

### 今天上海天气怎么样？
- `bm25` route=refuse doc_rank=None
- `tfidf` route=refuse doc_rank=None
- `hybrid` route=refuse doc_rank=None
- `hybrid_rerank` route=refuse doc_rank=None
- `vector` route=refuse doc_rank=None
- `vector_bm25` route=refuse doc_rank=None
- `vector_bm25_rerank` route=refuse doc_rank=None
