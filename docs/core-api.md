# 核心接口清单（问答页拆仓准备）

> 本文只描述**当前代码现状**（第 8 轮 [readme-v1prep]），不改代码结构。
>
> 目的：v1 完成后要把独立问答页 `app/rag.py` 拆成一个依赖本库 `core` 的薄仓库（见 `docs/ROADMAP.md`）。这里列出它届时要依赖的公开接口，作为拆分前的约定基线。
>
> 签名以源码为准；如果与本文不一致，以源码为准并回改本文。

## 1. 问答页当前实际 import

`app/rag.py` 现在只依赖下面 5 个名字：

```python
from core.index import get_retriever
from core.qa import answer_question, load_dotenv_config
from core.qa.answer import Citation, split_cited_citations
from core.tools.parse_document import ParseDocumentInput, parse_document
```

间接依赖：`core.models`（`Chunk` / `SearchHit` / `ToolResult`）、`core.index.embeddings`、`core.qa.llm`、`core.index.relevance`、`core.tools.search_chunks`。

## 2. 解析与入库（parse / ingest）

| 接口 | 位置 | 说明 |
|---|---|---|
| `parse_document(request: ParseDocumentInput) -> ToolResult[ParseDocumentData]` | `core/tools/parse_document.py` | 问答页入库入口。内部调用 `parse_pdf` → 去噪 → `chunk_document`，并 `put_document` 到进程内存储。 |
| `ParseDocumentInput(file_path: str, engine: "pymupdf" \| "mineru" = "pymupdf")` | 同上 | MinerU 未安装时自动回退 PyMuPDF。 |
| `ParseDocumentData` | 同上 | 字段：`doc_id`、`pages`、`sections`、`tables`、`chunks: list[Chunk]`、`engine`。 |
| `parse_pdf(file_path, engine="pymupdf") -> ParsedDocument` | `core/parse/pdf.py` | 底层解析，保留页码。 |
| `chunk_document(document, *, min_chars=500, max_chars=800, overlap=100) -> list[Chunk]` | `core/parse/chunking.py` | 按标题内切块，跳过目录页。 |
| `put_document / get_document / list_document_ids / clear_documents` | `core/parse/store.py` | 进程内文档存储（非持久化）。 |

入库流程是 `parse_document(...)` 拿到 `data.chunks`，再调 `retriever.index_chunks(data.chunks)`（见 `app/rag.py::_ingest`）。

## 3. 检索（retrieval）

| 接口 | 位置 | 说明 |
|---|---|---|
| `get_retriever(backend=None, *, embedder=None, uri="data/index/milvus.db") -> Retriever` | `core/index/__init__.py` | `backend` 取参数或环境变量 `RETRIEVER`；原生 Windows 默认 `memory`，其他平台默认 `milvus`。 |
| `Retriever` Protocol | `core/index/retriever.py` | `index_chunks(chunks)`：按 `chunk_id` upsert。`search(query, doc_ids=None, top_k=8, mode="hybrid") -> list[SearchHit]`：分数降序，`doc_ids=[]` 不匹配任何文档。 |
| `MemoryRetriever` / `MilvusRetriever` | `core/index/memory.py` / `core/index/milvus.py` | 均为向量 + BM25 + RRF 混合检索；Milvus 版依赖 milvus-lite（原生 Windows 不可用）。 |
| `search_chunks(SearchChunksInput, *, retriever) -> ToolResult[SearchChunksData]` | `core/tools/search_chunks.py` | 工具层包装，`answer_question` 内部使用。 |
| `filter_relevant_hits(query, hits, *, embedder=None, min_vector_score=None, ...)` | `core/index/relevance.py` | 相关性门槛：BM25 无重叠**且**余弦 < `MIN_VECTOR_SCORE` 的片段丢弃。 |
| `get_embedding_provider()` / `download_embedding_model()` | `core/index/embeddings.py` | `EMBEDDING_BACKEND=local\|fake`；运行时不静默联网，缺模型需显式 `--download-model`。 |

现状备注：`app/rag.py` 目前写死 `get_retriever("memory")`，没有读 `RETRIEVER`。拆仓时是否改为读配置，需另行决定（本轮不改）。

## 4. 问答（answer_question）

```python
answer_question(
    question: str, *, retriever: Retriever, chat_model: ChatModel | None = None,
    doc_ids: Sequence[str] | None = None, top_k: int = 8, mode: str = "hybrid",
    auto_build_model: bool = True, embedder: EmbeddingProvider | None = None,
    min_vector_score: float | None = None,
) -> AnswerResult
```

- 流程：混合检索 → 相关性过滤 → 无相关片段则拒答 → 调模型 → 校验回答里的 `[文件名 p页码]` 都落在召回片段内，否则拒答。
- `AnswerResult`：`question`、`answer`、`citations: list[Citation]`、`refused`、`retrieval_only`（未配置 `API_KEY` 时只返回检索结果）、`message`。
- `Citation`：`file`、`page`、`chunk_id`、`text`、`score`、`doc_id`、`section`；`label` 属性返回 `[file pN]`。
- `split_cited_citations(answer, citations) -> (cited, uncited)`：按 (file, page) 区分回答实际引用的片段和仅召回的片段。问答页用它把「已引用」排在前面。
- `parse_citation_markers(text) -> list[(file, page)]`、`validate_answer_citations(answer, citations)`：引用解析与校验。
- 模型：`core/qa/llm.py`
  - `ChatModel` Protocol（`complete(messages) -> str`）；
  - `build_chat_model(api_key=None, base_url=None, model=None)`：未配置 Key 时返回 `None`；
  - `OpenAICompatibleChat`；
  - `FakeChatModel`（测试用）。

## 5. 配置（config）

- `load_dotenv_config(path=None) -> dict[str, str]`（`core/qa/answer.py`）：读取 `.env` 的 `KEY=VALUE` 写入 `os.environ`，**不覆盖**已有环境变量。
- 问答页相关环境变量：

| 变量 | 默认 | 使用方 |
|---|---|---|
| `API_KEY` | 空（仅 `.env`） | `build_chat_model` |
| `BASE_URL` | `https://api.deepseek.com` | `OpenAICompatibleChat` |
| `MODEL` | `deepseek-flash` | `OpenAICompatibleChat` |
| `RETRIEVER` | Windows=`memory`，其他=`milvus` | `get_retriever`（问答页当前未读取，见上） |
| `EMBEDDING_BACKEND` | `local` | `get_embedding_provider` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | `LocalEmbeddingProvider` |
| `EMBED_DEVICE` | 自动 | `LocalEmbeddingProvider` |
| `EMBED_QUERY_INSTRUCTION` | BGE 中文检索前缀 | `core/index/query_instruction.py` |
| `EMBEDDING_ALLOW_DOWNLOAD` | 未设 | 允许首次下载模型 |
| `MIN_VECTOR_SCORE` | `0.35` | `filter_relevant_hits` |
| `PARSER` | `pymupdf` | 解析引擎 |

## 6. 拆仓时**不**需要的部分

`core/graph/*`（LangGraph 报告流程）、`core/tools/calc_financials.py`、`financial_extract.py`、`verify_claim.py`、`render_section.py`、`export_report.py`、`core/export/*`、`app/report.py`，都只服务报告生成。问答页不 import 它们。

## 7. 稳定性约定（建议，尚未落地）

- 第 2–5 节列出的名字视为对外接口，改签名时需同步本文与问答页。
- 目前没有版本号；`core/qa/__init__.py` 有 `__all__`，`core/index/__init__.py`、`core/tools/` 没有。也没有针对「对外接口」的独立契约测试（现有测试覆盖行为，不覆盖导出面）。拆仓前建议补上。
