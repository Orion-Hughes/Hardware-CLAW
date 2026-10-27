# Agent通用仿真观察

2026-10-27更新：删除了只针对单个工程的固定刺激、专用日志解析、验收条件和业务模板。开发约束见根目录AGENTS.md。历史测试报告仅记录旧流程，不代表当前功能。

## 当前执行

`simulate_project(expected_version)`检查修订、基础检查和真实编译固件，在temp复制电路、配置与固件，调用Wokwi CLI进行限时观察。无需特定元件，不传scenario，不改变元件控制值，不要求业务串口格式。Token只进入子进程环境。

所有受支持构建配置的工程使用相同观察参数：25秒模拟窗口、90秒宿主墙钟、1MiB日志上限，每轮最多3次。CLI退出42表示模拟观察窗口到期，记录observation_limit；退出0为completed，其他退出为tool_error，宿主超时单独记录timeout。这些都是执行状态，不是功能判定。

保存原始serial.txt、cli.log和通用observation.json；固件、电路、观察配置和证据绑定哈希。相同输入可复用证据；修改或证据篡改使旧报告失效。超时/取消保留现有进程回收机制。

`evaluate_tests(expected_version)`核验当前证据并报告执行/覆盖状态。正常观察返回unsupported，checks为空、full_project_acceptance=not_evaluated；工具故障单独返回tool_error或timeout。**通用需求验收尚未实现，不会返回功能pass。** 不将启动日志或用户文本中的ERROR等关键词当成业务判定。

## 迁移与边界

旧工程的专用test_plan.json及历史报告不删除、不继续使用。当前报告必须匹配observation_v1；旧通过记录不能被用作新流程的结果。历史导出包保持原样。

默认输出仍为含固件的VS Code文件夹。宿主可打包已检查、编译的文件，不能把ready_for_vscode解释为功能通过。缺少验收能力时如实交付供人工验证。

当前构建基线仍为ESP32-S3，不宣称支持所有板卡。下一步只能建设需求驱动、可复用的验收机制及通用操作；不得新增某个示例专用的skills、模板、预期、解析器或补丁来制造成功。

## 本次验证

88项离线测试通过，覆盖无外设工程也进入仿真、CLI不携带专用scenario、任意业务日志不产生功能通过、旧专用报告失效、证据篡改及修订绑定。

真实CLI运行已有屏幕工程，未修改源码：采集到启动和业务串口日志，90.36秒触发宿主墙钟超时并回收进程，记录timeout/full_project_acceptance=not_evaluated。不能宣称屏幕功能通过。摘要留在本地temp/general-observation/result.json；没有调用LLM API。
