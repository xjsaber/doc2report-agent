# 2026-10 r6 screens

## 环境
- 系统：原生 Windows 10（非 WSL），PowerShell
- Python：3.12.10（仓库 .venv）
- GPU：RTX 3050 / torch 2.6.0+cu124
- 模型：DeepSeek deepseek-flash（.env 已有 API_KEY，不打印）
- 浏览器：Playwright + 系统 Chrome（channel=chrome，免下 bundled chromium）

## 决策
1. 删除四张示意截图；scripts/screenshots.py 启动真实 Streamlit，Playwright 驱动上传/入库/提问/生成。
2. 拒答时 UI 不渲染「命中原文」；nswer_question 在模型拒答/引用校验失败时清空 citations。
3. embedding 缺缓存时抛明确错误，不再静默联网；python -m core.index.embeddings --download-model、CLI --download-model、EMBEDDING_ALLOW_DOWNLOAD=1。
4. README 用 ![](docs/images/…) 直接展示；Word 打开图本轮不拍，docx 留在 output/r6/。

## 坑
- Playwright bundled chromium 版本与缓存不一致；改用系统 Chrome channel。
- --skip-qa 曾误删问答截图；改为只删除本轮将重拍的文件。
- ile_uploader 入库后需轮询侧边栏「已入库文档」出现「页/块」，不能只等 ephemeral success toast。
- 笔记本 GitHub 443 偶发；必要时 box bundle / HTTP/1.1。

## 人工确认项
- 四张截图目视：有侧边栏；无本机用户名/绝对路径/Key；qa-cited 有引用与「命中原文」；qa-refuse 无「命中原文」。
- Word 打开图如需补拍，打开 output/r6/ 中 docx 即可。

## 截图观察（实拍）
- qa-cited.png：侧边栏已入库 public-annual-report-2024.pdf（185 页 / 1646 块）；问主营业务有引用（如 p89/p28）与「命中原文」。
- qa-refuse.png：火星移民问题拒答；不展示「命中原文」。
- 
eport-progress.png：侧边栏上传+模板；主区「解析 PDF…」进度。
- 
eport-preview.png：报告预览+展开引用原文（真实片段，非示意文案）。

## 测试
`	ext
python -m pytest -q -rs --basetemp=.tmp/pytest/basetemp
131 passed, 11 skipped, 0 failed
`
