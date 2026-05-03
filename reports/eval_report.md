# Enterprise Knowledge Assistant Eval Report

- run_at: `2026-05-02T17:01:47Z`
- retrieval_strategy: `hybrid_rerank`
- total: `7`

| metric | value |
| --- | ---: |
| route_accuracy | 1.0 |
| retrieval_hit_at_k | 1.0 |
| mrr | 1.0 |
| citation_rate | 0.571 |
| refusal_hit_rate | 1.0 |
| answer_contains_expected | 1.0 |

## Cases

- `document_qa` 实习生差旅报销标准是什么？ (expected_route=document_qa, expected_doc_rank=1)
- `document_qa` 实习生住宿标准是多少？ (expected_route=document_qa, expected_doc_rank=1)
- `document_qa` 年假制度总结成三条 (expected_route=document_qa, expected_doc_rank=1)
- `document_qa` 代码评审必须检查哪些内容？ (expected_route=document_qa, expected_doc_rank=1)
- `sql` 上个月销售额最高的是哪个区域？ (expected_route=sql, expected_doc_rank=None)
- `sql` 哪些项目处于 blocked 状态？ (expected_route=sql, expected_doc_rank=None)
- `refuse` 今天上海天气怎么样？ (expected_route=refuse, expected_doc_rank=None)
