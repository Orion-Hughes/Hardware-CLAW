# 正式评估

保留 benchmark 定义、固定验收条件和正式实验结果。记录模型与工具版本、Token、耗时、修正轮数、项目版本和实际证据。

当前 LangChain 的两个在线查询案例由用户运行并在对话中报告；它们验证了工具调用，不是完整工程生成能力。程序单元测试位于 `../LangChain/tests/`。

已建立 [cases](cases/README.md) 与 [results](results/README.md) 的职责目录，尚无正式案例或运行结果。日常工程运行记录由workspace项目的.hwclaw/runs保存；本目录用于正式验收基准与选定评估证据，避免将临时日志当成已完成的评估。
