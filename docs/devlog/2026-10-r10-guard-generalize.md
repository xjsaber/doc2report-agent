# 第 10 轮任务 1：guard-generalize

## 环境

Windows 11，PowerShell 7.6.5，现有 .venv Python 3.12.10，NVIDIA GeForce RTX 3050 Laptop GPU。git pull 后基线 b72cd9e；邮箱已核对。

## 决策

选择用户允许的第二种方案：v1 整体删除逐字句式守卫及其 14 项专用测试，移除 verify 节点接入；保留写作提示规则。通用矛盾检测列入 ROADMAP v2。
理由：表格可能跨块拆列，页级有数字不等于实际召回块足够归因。将两条精确正则扩大为否定词正则仍可能误标，v1 不在缺乏标注集时引入一般语义自动处理。
写作提示禁止对已提供相关表格行的片段声称未披露、未包含、未显示或无法确认；只有表头或列关系不明时说明片段证据不足，不推断整份年报缺失。
现有提示契约测试补查上述约束，不依赖某次模型输出原句。无程序化语义标记、无自动正文改写；提示能否被模型遵守仍以实跑观察和人工核验为准。

## 测试

`python -m pytest -q -rs -p no:cacheprovider --basetemp=$env:LOCALAPPDATA\Temp\d2r-pytest-r10`

185 passed / 11 skipped / 1 warning。11 项为原生 Windows 不支持 Milvus Lite；warning 为既有 LangChain 弃用预告。

## 坑与人工确认

删除守卫后测试数减少，不解释为覆盖率或效果提高。当前 README 历史测试表会在任务 3 收敛。
下一任务必须在本提交代码上重跑 CLI 和真实截图；作者使用新的 DOCX 拍 Word 图，不由代理生成，不打 tag。
已有未跟踪观察 JSON 保留，不读取或输出密钥，不提交 PDF、output 或模型。
