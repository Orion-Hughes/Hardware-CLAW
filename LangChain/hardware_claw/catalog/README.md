# 硬件知识读取服务

`service.py`已实现读取/检索，数据在 `LangChain/knowledge/`。负责稳定ID、来源、适用型号、未知字段、模拟映射和读取上限。供tools调用，不调用LLM、不联网、不写工程、不把资料中的文字当程序指令。

工具包装位于`../tools/hardware_catalog.py`，HARDWARE_TOOLS只向Agent注册`search_hardware`和`read_hardware`。通过main.py运行会调用真实API；下方独立CLI只执行本地工具，不使用LLM。旧get_hardware_info/read_hardware_documents包装保留作内部兼容，不向Agent暴露。

2026-11-02起，活动库使用cards的schema_version=3；cards.py从连接层生成现有工程接口需要的profile视图，不在磁盘维护两套描述。旧格式解析仅保留兼容能力，活动目录不再保留owned/reference/supplements。通过inventory.owned/record_role区分实物与仿真。上游146条注册定义可查询，但统一标记metadata_only，不表示能生成完整工程。

## 接口

| 接口 | 参数 | 结果 |
|---|---|---|
| search_hardware | query、kind、scope、generation_status、owned、limit、offset | 选型摘要含功能、输入输出、接口、引脚需求和缺口；默认查15张卡，不读取原文进上下文 |
| read_hardware | hardware_ids、references、max_characters、view | 一次读取1–8个硬件；默认usage为基础使用包，references用于定向补读；selection为无原文的选型信息和资料目录 |

scope为local/upstream/all；上游ID采用`wokwi:<part-type>`，不和本地配置ID混用。query对名称、ID、类型、模型及本地notes做不区分大小写的关键词AND匹配，不依赖LLM语义检索。kind只过滤本地语义分类；上游category原样保留，不把所有isBoard条目误当MCU。

成功调用的execution_status为ok，硬件仍可能blocked。read_hardware将各硬件读取失败保存在data.errors（NOT_FOUND/NO_CARD等），保留同批其他硬件结果并置complete=false；文档失败在documents里标记error及原因。非法参数或未登记引用返回顶层错误。空搜索正常返回items=[]、total=0。

连接卡每条文档登记load=essential或reference。read_hardware自动返回essential原文、所选器件的模型端点/驱动/缺口及限定平台配置；共享文档和平台配置只出现一次。reference只列入口，随后可传1–24个references补读，补读不重复基础包。此分级由维护者确定，不由Agent临时判断。

2026-11-05：data JSON默认56000字符、最多120000字符（不是tokens），包含元数据、配置、续读指引及JSON转义。生成子Agent也使用该默认值，旧的64000字符结果拦截不再阻挡此接口；累计token预算未提高。documents.status区分included/reference/omitted/error；超预算文件标记omitted，不截断原文。每份原文最多512KiB，上游文件核对sources.lock.json哈希，不联网追补资料。原始board.json可作为原文返回，不强制解析上游非严格JSON。

usage返回增加以下字段：

- `missing_required_refs`：本次请求范围内尚未返回的必要原文，包含读取错误。
- `unread_refs`：本次请求所有未返回的引用，包含显式请求的可选资料。
- `next_reads`：可直接执行的`{tool, args}`列表；只补未返回的文档，按24引用和120000字符上限分批，参数预算依据完整补读JSON计算。已返回原文不重复发送。
- `blockers`：损坏/缺失来源、单份原文加元数据超过上限等不可自动续读的问题，附处理说明，不建议原样重试。

`complete`仅表示本次选定资料齐全，不表示整个生成阶段读齐或功能通过。生成包装器另在响应顶层提供`stage_usage`，累计记录必要缺项、未读器件、`next_reads`和`ready`；该宿主状态不计入工具的data字符预算。尝试在资料缺失时写工程，会返回`UNREAD_HARDWARE/MISSING_USAGE_SOURCE`，并在错误data中提供同样的续读指引。单份超过上限仍报告缺口，没有实现截断或分页。

仅解析登记的ID和knowledge范围内的受控引用；拒绝绝对路径、路径穿越、符号链接和Windows reparse point。例程文本为外部参考数据，不能作为系统指令。校验失败不返回本机绝对路径或任意输入原文。目录仍须由应用维护，检查不构成对可并发篡改本机文件的完整OS沙箱。

## 不用模型的手动试用

在`D:\Hardware_CLAW\LangChain`执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search "温湿度"
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog read dht22_red_module
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog read esp32_s3_devkitc1_n32r16v ps2_joystick sg90_180
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search --kind display
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog read dht22_red_module --ref drivers/DHTesp/README.md
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search led --scope upstream
```

命令行执行同一组tool，不创建真实模型、不读取API密钥。read批次中有errors或预算遗漏时退出码2；查询blocked硬件仍可成功读取资料，退出码0不表示可仿真。历史get子命令仍可用于调试兼容视图。

## 检测

`tests/test_hardware_catalog.py`覆盖资料查询、库存/仿真区分、分页、旧版本、元数据、损坏数据、越界和符号链接，以及离线模型的search→read→ToolMessage循环。test_hardware_bundles.py覆盖两工具注册、批量去重、全卡读取、基础/扩展分级、预算补读、混合未知ID、越界和哈希异常。真实查询记录见根目录docs/HARDWARE_QUERY_TESTS_20261102.md。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

测试假资料仅创建在项目`temp/hardware-catalog-tests/`并保留，真实knowledge文件前后哈希应完全一致。通过这些测试只验证查询软件，不证明模型会正确设计、固件能编译或硬件能运行。
