# 审核分级、实现选择与编译记录调整

日期：2026-10-29。本轮修改Hardware-CLAW自身的检查和执行流程，不修改Codex的自动审批规则，不安装依赖，也不运行付费LLM实验。

## 1. 分阶段判断

`check_project_files`现在返回`validator_version=2`、`stage_verdicts`和带`severity/blocks`的`issues`：

- `error`：只阻断`blocks`列出的阶段。
- `warning`：需要注意，但不阻断工具执行。
- `unverified`：现有静态检查不能确认；不阻断，也不提升为功能通过。

阶段为`build`、`simulation`、`delivery`。全局`verdict=fail`仍表示至少有阶段被阻断，但编译器只看`build`，CLI/MCP看`simulation`，导出看`delivery`。执行入口重新检查当前文件；旧版检查报告不能直接授权操作。VS Code导出仍需要真实构建记录和匹配的二进制哈希。

| 情况 | 调整后的处理 |
|---|---|
| README缺失 | warning；不阻断编译、仿真或导出 |
| INI/TOML注释、键顺序、等价格式 | 按解析后的值比较，不再逐字比模板 |
| diagram端点/连线错误、电源短接 | 阻断仿真和交付，允许先获得编译反馈 |
| 不推荐GPIO | warning；明确不可用或已占用GPIO仍阻断相关阶段 |
| 头文件未在源码中直接出现 | unverified；不以文本匹配替代编译器头文件解析 |
| 分文件源码、间接include、常量表达式、条件编译 | 扫描全部源码/头文件；无法确认时保留unverified |
| 明显的简单GPIO字面量与设计冲突 | 阻断仿真/交付，编译阶段仍可运行 |
| 固定启动文字或串口面板显示方式 | 不强制固定日志；面板显示方式只作提示 |
| 任意构建脚本、外部路径、未登记依赖、变更目标板卡 | 仍拒绝，不属于格式自由 |

源码扫描屏蔽注释和字符串，避免把日志内容当代码；它仍是保守的文本提示，不是C++语义分析或电气验证。当前ESP32-S3 UART0、受控固件路径等平台约束保持明确适用范围。

## 2. 器件与实现方案分开

在设计中增加`implementations`，以元件实例ID为键：

```json
{
  "implementations": {
    "device": {
      "mode": "framework",
      "api_refs": ["get_driver_api(detail=full)实际返回的framework_api_refs路径"]
    }
  }
}
```

这是接口形状说明，路径占位符不能直接提交。

- 未声明时沿用`catalog`：保留登记驱动的固定依赖要求，兼容现有设计。
- `framework`：显式使用板卡框架API；须引用当前器件或板卡已经登记的API原文，并同步依赖、配置和源码。
- 保存设计时核对引用来源，将原文SHA256存入`implementation_evidence`。来源匹配不证明协议、时序或功能实现正确。
- 资料由既有上游文件派生，本轮未修改硬件原文或加入某工程的修复策略。

精简API目录保留获取完整引用列表的提示，不为每个器件重复展开所有路径。

仍未实现任意库搜索、库别名审核或注册表包坐标自动解析。版本范围、下载URL、未登记包名继续拒绝。**原ESP32Servo依赖未成功获取的根因尚未解决**；增加实现选择接口不等于舵机替代实现已经可用，也不代表所需API资料全部齐备。

## 3. 构建身份、复用与停止条件

新的构建指纹带`fingerprint_version=2`。它覆盖源码、头文件、构建配置及其他可能参与构建的工程文件；仅排除未被源码引用的README、diagram和Wokwi配置。存在计算式include等不确定情况时保留所有文件。该规则仅用于当前受控适配器，不是通用C++依赖分析。

- 只改说明：重新检查并重新导出，可复用匹配的编译记录。
- 只改电路：可复用编译，仿真证据仍需匹配新的电路。
- 改源码/构建输入或安装环境身份：需要匹配的新构建。
- 复用结果保留`built_version`、`reused_from_version`、`cached`和原始attempt；二进制哈希仍会核验，不伪称再次编译。
- 老指纹记录保留为历史，不能直接按新算法复用；必要时重新编译。

每个实际尝试在`.hwclaw/builds/<attempt>/result.json`保存不可变结果，包括失败。启动错误、取消、编译期间版本变化也保留记录；过期结果不绑定当前工程。

跨修订匹配相同编译输入和工具链：

1. 确定性编译错误：修改后又还原为同一输入会报`NO_PROGRESS`，不会因为版本号或README变化再跑一次。
2. 依赖/网络/其他环境失败：同一身份在300秒窗口内最多两次；工具链登记状态变化或窗口结束后可重试。错误摘要保留包获取失败信息，不只返回最后的缺头文件错误。

环境身份来自受控编译器及已安装平台/工具包的版本清单；不读取凭据，也不宣称能检测任意工具文件篡改或网络恢复。这是局部无进展检测，尚不是识别任意语义等价代码或所有无效Agent循环的机制。原有总token、模型次数、超时和取消边界保持不变。

## 4. 验证与保留的失败

完整离线回归**170项通过，41.101秒**，其中本轮新增23项。覆盖分阶段门槛、配置等价性、危险构建参数拒绝、两个不同器件的实现声明、来源哈希、跨修订重复失败、有限环境重试、构建复用、旧指纹/旧检查拒绝、固件篡改、取消和过期结果。495份上游原文的锁定来源校验同时通过。

测试还通过真实LangChain工具循环接通检查与编译适配器；模型和编译进程使用测试替身，没有付费API、实际固件编译或Wokwi运行。测试二进制明确是fixture，不作可验收工程。

- 完整回归日志：`temp/review-rules/regression-release.log`。
- 旧工程只读核对：`temp/review-rules/historical-readonly-check.json`。
- 原工程/运行证据哈希：`temp/review-rules/preserved-files.json`，用于确认最后整理与服务重启未修改这些文件。

对历史v3和v6仅在内存中运行新检查，未更新其保存的检查报告或文件。新检查不再因v6缺少直接驱动include而阻断，但保留`DRIVER_USAGE_UNVERIFIED`；未重新编译或仿真，也没有自动替它声明framework方案。旧失败仍是原始失败。

本轮LLM API调用 **0次**，API耗时 **0秒**；没有提供方token统计或新增项目API费用。之后需要单独进行真实Agent实验，确认模型能使用新接口并记录实际成本；不能用本次离线结果推断生成成功率。

收尾核对：原工程及该次实验的21个文件哈希保持不变；Markdown本地链接和`git diff --check`通过。已重启原本运行中的Chainlit服务，健康接口正常，首页返回HTTP 200；未提交或推送Git。旧工程须重新运行当前检查，旧指纹构建记录需要重新编译后才能授权仿真/导出。

## 5. 代码入口与后续

| 文件 | 职责 |
|---|---|
| [validation/report.py](../LangChain/hardware_claw/validation/report.py) | 分级报告与阶段判断 |
| [validation/files.py](../LangChain/hardware_claw/validation/files.py) | 结构、连线及分阶段检查 |
| [validation/build_config.py](../LangChain/hardware_claw/validation/build_config.py) | 配置语义检查 |
| [validation/source_hints.py](../LangChain/hardware_claw/validation/source_hints.py) | 保守源码提示 |
| [projects/implementations.py](../LangChain/hardware_claw/projects/implementations.py) | 实现声明、API来源和依赖要求 |
| [adapters/build_state.py](../LangChain/hardware_claw/adapters/build_state.py) | 编译身份、历史与重复失败判断 |
| [tests/test_review_policy.py](../LangChain/tests/test_review_policy.py) | 通用机制反例与Agent工具循环测试 |

优先后续工作：核对已登记库到实际构建包的来源与可获取性；在预算内重测不同器件组合；再完善独立需求验收。路径、来源、版本、真实固件和证据检查保留，不为了通过某个工程而添加特例。

后续记录：用户“自行测试”后已另做一次[真实Agent续接测试](AGENT_REVIEW_LIVE_TEST_20261029.md)。旧v6实际编译通过并由宿主交付，但模型未使用新的framework声明，完整验收未完成。该实验有独立的API统计，不改写本报告所述离线改造阶段的0次调用及当时保留的失败。
