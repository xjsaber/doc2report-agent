# 评审：0e76c5c [scaffold] 第 1 步接口与测试骨架

结论：**通过，8.8/10，无阻断项**，可进入第 2 轮。

## 已核对
- 无 .env / PDF / 向量库 / docx 入库，未见密钥；README 声明与红线一致。
- 本地复跑（Python 3.12）：`pytest -q` → 11 passed, 21 skipped，与 README 一致。
- Retriever Protocol 签名符合 AGENTS.md；8 工具契约 + 统一返回结构 + 独立 RAG 入口（app/rag.py）都有；未验证项写得诚实。

## 第 2 轮先修（小改，不阻断）
1. `SearchHit` 补 `doc_id`（按文档过滤与多文档引用需要）。建议 `SearchHit` 继承 `Chunk` 再加 `score`。
2. `Chunk` 补 `section`（所属标题，可空）和 `page_end`（跨页片段，可空，默认等于 page）。
3. `ToolResult` 加 model_validator：ok=True 时 error 必须为空；ok=False 时 error 必填、data 为空。补 2 个测试。
4. Python 3.11 目标：pyproject 写 `requires-python = ">=3.11"`，CI 或 README 注明 3.11 未验证即可。

## 第 2 轮范围（最多 2 个模块）
- core/parse：PyMuPDF 解析，保留页码，表格尽量抽出；MinerU 开关未安装时回退并记日志。
- 切块：按标题/段落 500–800 字带重叠，输出 Chunk；解开 test_chunking 的 skip，用仓库内自造的小 PDF（测试时用 PyMuPDF 生成，不提交真实年报）。
- 对应工具 parse_document 实现并解开其测试。
