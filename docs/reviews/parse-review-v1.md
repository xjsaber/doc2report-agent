# 评审：0e250bf [parse] PDF 解析、切块与 parse_document

结论：**通过，9.0/10，无阻断项**。

## 已核对
- 第 1 轮 4 个小改全部落实：SearchHit 继承 Chunk（含 doc_id）；Chunk 加 section、page_end 并校验 page_end ≥ page；ToolResult 成功/失败一致性校验；requires-python ≥3.11。
- 解析：PyMuPDF 按字号/编号识别标题，表格抽取失败退回原文并记日志；无文本 PDF 明确告警（未做 OCR）；MinerU 懒加载，未安装或失败都回退 PyMuPDF。
- 切块：按标题分组、段落优先、句末次之，500–800 字带重叠，跨页片段记录 page/page_end，chunk_id 稳定哈希。
- 测试用现场生成的小 PDF，无真实年报、无 .env/PDF/密钥入库。
- Hark 沙箱复跑（Python 3.12）：51 passed, 18 skipped，与 README 一致。

## 第 3 轮必须先处理
1. **Milvus Lite 不支持 Windows**（官方仅 Ubuntu ≥20.04、macOS ≥11）。作者台式机是原生 Windows。处理方式：
   - Retriever 增加 `RETRIEVER=memory` 实现：numpy 余弦 + rank_bm25 内存检索，可选 pickle 落盘；作为 Windows 和测试的默认回退。
   - `RETRIEVER=milvus` 保留为默认演示实现，在 Linux/macOS/WSL/Docker 下跑；在 Windows 上选 milvus 时给出清晰报错并提示改用 memory 或 Docker。
   - 两个实现跑同一组契约测试（参数化），保证可替换。
2. 页眉页脚去噪：年报每页重复的公司名/「年度报告」/页码会污染切块和 BM25。加简单规则：同一行文本在 ≥30% 页面的顶部或底部重复出现即剔除；补测试。

## 第 3 轮范围
- core/index：上面两个 Retriever 实现 + 混合召回（向量 + BM25，RRF 融合，k=60）；embedding 走配置，默认本地 bge-small-zh-v1.5，测试用假 embedding 不下载模型。
- search_chunks 工具接通 Retriever，解开 test_retrieval 及其工具测试的 skip。
- 中文 BM25 分词用 jieba，测试覆盖中文查询。
