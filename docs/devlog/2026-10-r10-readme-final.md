# 第 10 轮任务 3：readme-final

## 环境与决策

Windows 11 / PowerShell 7.6.5 / 现有 .venv Python 3.12.10 / NVIDIA GeForce RTX 3050 Laptop GPU。
README 测试结果收敛为一张当前候选表；Windows 使用本任务实际 pytest 结果，Linux 写以评审复现为准，不搬用历史提交数字。
端到端观察只保留任务 2 那次，注明非基准、重跑会变；任务 2 后未改变报告运行代码。
CHANGELOG 同步仅保留写作提示的方案，发布日期留空。ROADMAP 标明待作者补 Word 图并确认；不打 tag。

## 文档卫生

README 和 docs 下 Markdown 的用户目录前缀统一换为 `$env:LOCALAPPDATA\Temp\...`；评审引用中的示例路径也规范化，避免卫生测试遗漏。
README 与 devlog 的非代码说明补中英文和数字间空格；保留代码、引用原句、引用标记和链接目标，避免破坏可执行命令或审计原文。
新增卫生测试扫描 README 和 docs/**/*.md，不允许 Windows 用户目录绝对路径重新进入文档。

## 测试

`python -m pytest -q -rs -p no:cacheprovider --basetemp=$env:LOCALAPPDATA\Temp\d2r-pytest-r10`

186 passed / 11 skipped / 1 warning，9.82 s。11 项为原生 Windows 不支持 Milvus Lite；warning 为既有 LangChain 弃用预告。

## 坑与人工确认

本机 WSL 检查提示需安装，因此 Linux 当前 HEAD 全量测试仍以评审复现为准，不能称已通过。
历史 devlog 保留历史实测数字，README 只展示本轮最终结果。先前独立 UI 截图与 CLI 输出不是同一次模型响应，但使用相同运行代码。
作者仍需使用任务 2 的 DOCX 拍 Word 打开图，并确认发布日期与 tag；代理不生成占位图、不打 tag。
用户已有未跟踪观察 JSON 原样保留；不提交 PDF、密钥、模型、output 或 DOCX。

连接恢复后核对任务 2 暂存及远端，未重复 CLI。任务 2 首次推送遇到 TLS 错误，按要求 pull --rebase 后普通 push 成功，无强推。
