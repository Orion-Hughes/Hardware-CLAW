# 硬件知识读取服务

`service.py`已实现读取/检索，数据在 `LangChain/knowledge/`。负责稳定ID、来源、适用型号、未知字段、模拟映射和读取上限。供tools调用，不调用LLM、不联网、不写工程、不把资料中的文字当程序指令。

工具包装位于`../tools/hardware_catalog.py`，包含`search_hardware`、`get_hardware_info`及`HARDWARE_TOOLS`。2026-10-27已接入主Agent并更新查询Prompt，原教学get_board_info不再注册。通过main.py运行会调用真实API；下方独立CLI仍只执行本地工具、不使用LLM。

读取器支持owned的schema_version=2和历史reference的schema_version=1；后者没有生成配置时明确返回unreviewed。通过inventory.owned/record_role区分实物与仿真，不按文件夹推断库存。上游146条注册定义可查询，但统一标记metadata_only，不表示能生成完整工程。

## 接口

| 接口 | 参数 | 结果 |
|---|---|---|
| search_hardware | query、kind、scope、generation_status、owned、limit、offset | 摘要、匹配总数、下一页偏移；默认查本地11条 |
| get_hardware_info | hardware_id、include_shared、include_examples | 本地配置、原始引脚/属性、可选公共规则/例程、来源哈希 |

scope为local/upstream/all；上游ID采用`wokwi:<part-type>`，不和本地配置ID混用。query对名称、ID、类型、模型及本地notes做不区分大小写的关键词AND匹配，不依赖LLM语义检索。kind只过滤本地语义分类；上游category原样保留，不把所有isBoard条目误当MCU。

成功调用的execution_status为ok，但data.summary.generation_status仍可能是blocked。未知ID返回NOT_FOUND；资料损坏、引用缺失分别返回INVALID_JSON/INVALID_CATALOG/MISSING_REFERENCE等，不伪装成未知型号。空搜索正常返回items=[]、total=0。

默认不返回原始文档或重复的公共配置。查询板卡时可include_shared=true；原始例程按需最多2份、各8000字符，截断会标记truncated。不会把HTML整页载入上下文，也不解析含注释的原始board.json。每次JSON读取最多512KiB，tool结果最多64000字符，搜索每页最多30项。

仅解析登记的ID和knowledge范围内的受控引用；拒绝绝对路径、路径穿越、符号链接和Windows reparse point。例程文本为外部参考数据，不能作为系统指令。校验失败不返回本机绝对路径或任意输入原文。目录仍须由应用维护，检查不构成对可并发篡改本机文件的完整OS沙箱。

## 不用模型的手动试用

在`D:\Hardware_CLAW\LangChain`执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search "温湿度"
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog get dht22_red_module
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog get esp32_s3_devkitc1_n32r16v --shared
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search --kind display
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog get usb_camera
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search led --scope upstream
```

命令行执行同一组tool，未创建真实模型、读取API密钥或使用Token。未知ID/参数错误退出码为2；查询blocked硬件仍是成功查询，退出码0，不表示可仿真。

## 检测

`tests/test_hardware_catalog.py`覆盖真实资料查询、库存/仿真区分、分页、旧版本资料、原始元数据、例程截断、损坏数据、越界和符号链接，以及离线模型的search→get→ToolMessage回填循环。已有Agent/API配置测试保持不变。

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

测试假资料仅创建在项目`temp/hardware-catalog-tests/`并保留，真实knowledge文件前后哈希应完全一致。通过这些测试只验证查询软件，不证明模型会正确设计、固件能编译或硬件能运行。
