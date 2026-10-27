# 第 3 轮任务 2：混合召回与 search_chunks

日期：2026-10-27；基线：401ab56 [index]。仅完成任务 2，保留任务 1 的去噪与双 Retriever，未实施任务 3。

## 要解决什么

替换临时字符分词和混合分数相加，实现中文 BM25、可配置 embedding 与 RRF；让 search_chunks 通过 Retriever 接口返回可溯源命中及工具日志。

## 决定

- memory / milvus 共享 jieba 分词、BM25 和 RRF，向量评分仍走各自后端。先过滤文档，对全部候选分别排名，再按 1/(60+rank) 求和、取 top_k；同分按 chunk_id 排序。零分候选保留参与排名，评分不是置信度。暂无召回阈值或大规模性能优化。
- EmbeddingProvider 使用批量 callable 协议，保留 embedder 注入兼容性。默认 local / BAAI/bge-small-zh-v1.5，sentence-transformers 放 embedding extra；fake 使用确定性 hash。未实现 openai 后端。
- 本地模型懒加载，CUDA 可用时选 GPU，否则 CPU，EMBED_DEVICE 可覆盖。运行期 local_files_only=True，用户需提前下载模型或提供本地路径，避免检索工具隐式联网。当前统一 encode 文档与查询，未添加查询专用指令，质量待实测。
- search_chunks 保留 SearchHit 的全部来源字段，成功/失败均遵循 ToolResult；日志只记查询长度、文档数、top_k、mode、耗时、ok。无全局 Retriever 实例，由调用方注入已索引实例。
- 保留会话级索引、不做持久化恢复；未改 core/parse 或应用页面。现有 .gitignore 修改保留，不纳入提交。

## 环境、坑与测试

原生 Windows，`.venv` Python 3.12.10。本机有 RTX 3050（用户提供）；本轮测试只用假 embedding 与模型替身，未使用 GPU，未下载模型或安装大模型依赖。安装 jieba 0.42.1，复用 numpy/rank-bm25。

PowerShell 首次读中文采用默认编码导致乱码，改为 UTF-8 重读。pytest 有 1 个旧 .pytest_cache 权限 warning，按要求保留，不修改 ACL；指定 basetemp 后测试无 setup 错误。

执行命令：

```powershell
.venv\Scripts\python.exe -m pytest -q -rs --basetemp=C:\Workplace\Work\30.doc2report-agent\.tmp\pytest
```

检索实现后的原有回归：62 passed, 24 skipped。补齐检索/工具测试：77 passed, 26 skipped, 0 failed。26 个 skip 为 Windows 上 Milvus 契约 11 项、引用核验占位 1 项、其他工具占位 14 项；search_chunks 已解除 skip。数据均为原创合成文本和测试生成 PDF。

验证涵盖原有去噪、双后端契约框架、中文三模式、RRF 精确分值和截断、来源字段、文档过滤、工具成功/失败日志、默认模型配置和设备分支（替身）。没有把被跳过的 Milvus 测试当成通过。

## 需人工确认 / 低置信

- **未验证**：Linux/macOS/WSL 上真实 Milvus 客户端运行，需安装 milvus extra 复跑契约。
- **未验证**：本地模型加载和 RTX 3050 实际推理、显存/性能、CUDA 安装适配。
- **低置信**：真实年报召回质量、无相关片段时的返回效果；假向量测试不能提供语义效果结论。任务 1 去噪启发式仍需公开年报人工抽查。
- 未编造召回率、延迟或 GPU 性能数字。API 依据为 [SentenceTransformer 官方文档](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)；模型来源为 [BAAI 模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)。
