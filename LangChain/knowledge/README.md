# Hardware-CLAW 硬件资料：Wokwi上游库与库存映射

重建日期：2026-10-26。按用户要求替换旧knowledge，直接从Wokwi上游重新获取资料。2026-10-27已通过两个查询tools接入真实API Agent；未执行固件编译/仿真/真机测试。

## 先看这三个入口

- [catalog.json](catalog.json)：机器可读总索引，含全部146个上游part type及9类已购硬件、2个非采购条目（临时240×240屏幕及SSD1306参考）。两个连接线及面包板的本地记录已按用户要求移除。
- [COVERAGE_AND_GAPS.md](COVERAGE_AND_GAPS.md)：每个器件找到什么、差异是什么、还需补什么。
- [sources.lock.json](sources.lock.json)：来源URL、固定提交、获取时间、逐文件SHA-256、许可情况与查询失败记录。
- [补充资料与统一格式](supplements/README.md)：本轮联网补充的驱动、接线规则、模型限制，以及补充来源锁定清单。

## 文件结构

```text
knowledge/
  catalog.json
  sources.lock.json
  COVERAGE_AND_GAPS.md
  owned/                        9类已购硬件 + 1个临时240×240仿真屏幕
  reference/                    SSD1306，仅供已有仿真工程使用
  supplements/
    esp32_s3_simulation.json     共用构建、GPIO资源及依赖规则
    sources.lock.json           本轮补充来源的版本、获取时间和哈希
    sources/                    厂家网页、固定版本驱动及模型源码摘选
  upstream/
    wokwi-diagram-lint/
      parts/                    固定提交的全部146条原始元件JSON
      packages/diagram-lint/    README、类型定义及必要规则源码参考
      LICENSE
    wokwi-docs/                 相关官方说明Markdown、LICENSE、灯环网页快照
    wokwi-boards/               S3、ST7789、SSD1306的原始board定义
```

这里的“全部146条”指本次固定提交中的diagram-lint注册元数据，不是所有真实商品、不含完整Wokwi仿真引擎，也不表示146种器件已经能由我们的Agent可靠设计。

## 数据怎么用

```text
输入器件型号/本地ID
  → catalog.json定位owned或reference条目
  → 根据upstream_definition_ref读取原始type/pins/attrs
  → 结合本地逻辑信号映射、采购配置、差异和缺口
  → 返回给Agent查询工具（尚待实现）
```

也可直接按part type检索全量上游定义；这只回答模拟格式和可用端点，不自动保证对应实物可用。

`owned/*.json`的字段：

- `inventory`：是否已购、数量、采购资料依据；数量是库存事实，不是上游器件属性。
- `record_role`：`owned_hardware`或`simulation_variant`。不得按所在文件夹判断已购；临时屏幕虽在owned目录，但owned=false、数量0。
- `simulation.part_type`：已建立家族/功能对应的模拟候选，仍未实测。
- `candidate_part_type`：仅发现候选但不足以直接选用，例如ST7789尺寸不符、咪头未文档化。
- `match_status`：对应程度；没有模型与不需要独立part是两种情况。
- `logical_signal_to_model_pin`：逻辑信号到模拟端点，不是实物接头顺序。
- `proposed_attrs`：来自库存的实例配置，如8灯灯环的`pixels: "8"`；原始上游文件不改动。
- `source_refs`：相对knowledge根目录的原文路径；inventory.evidence指向项目库存清单。
- `missing_information`、`notes`：待补字段和兼容性限制。
- `electrical_profile`：有明确scope的供电、逻辑电平和接线规则；仿真配置不等于实物额定规格。
- `physical_connector_order`：没有对应实物证据时保持null，不从模拟板外观推断。
- `driver_profile`：库名/版本、头文件、初始化、常用操作、原始示例引用及限制。
- `generation_profile`：仿真生成状态、公共配置引用、GPIO资源需求、运行controls、人工检查与阻塞原因。
- `simulation_test`、`hardware_test`：本轮均为not_run，数据完整性检查不等于运行验证。

型号资料默认通过公开厂家/卖家文档、驱动源码和参考设计补齐；照片只在确需辨别实物变体时作为可选证据，不是收录前提。

资料在维护阶段获取并核对。生成任务只消费已入库资料，不在任务中临时联网补规格。`documented_not_tested`仅表示具备资料级配置，不是通过测试；`blocked`表示当前不具备相应仿真生成条件。查询tool返回这些状态，Agent提示词要求保留；后续生成服务仍需实现强制阻止逻辑。

当前默认仿真屏幕由catalog的`simulation_defaults.display`指向`st7789_240x240_simulation`，实物240×320条目保留。总索引`reference_count=2`统计所有非采购条目，其中`simulation_variant_count=1`是子集；reference文件夹仍只有SSD1306。

## 必须保留的区别

- DHT模拟器的SDA是数据线；ST7789的SCL/SDA是该模块语境中的SPI信号，不能按名字推断协议。
- 面包板原始`pins: []`不表示没有孔位。上游lint对其使用动态命名规则，相关源码已保留；此规则不证明真实400孔板的孔排几何。
- 初始attrs与运行时controls不是天然等价；本轮仅为DHT22及摇杆记录有文档依据的controls，不代表全库都支持自动化控制。
- 板卡GPIO名称、Wokwi内部pin目标与N32R16V的真实GPIO可用性分别核对。
- 模型缺失只表示本次固定注册表没有找到对应条目，不是对整个Wokwi生态作永久“不支持”的判断。

## 来源、更新与许可

上游文件按原始字节保存，应用层补充写owned/reference，不覆盖上游。再次更新应固定新提交、比较引脚与属性差异、重新检查本地映射。

CLI注册表和docs仓库的MIT许可随文件保留。boards仓库根未找到许可文件；本地作为研究快照保留，不自动视为可再分发。灯环网页为实时快照，非commit固定文件，单独记录URL/获取时间/哈希，发布前核对其授权。原始board.json可能采用注释/尾逗号等扩展格式；不得修改原文冒充严格JSON，未来解析应明确选用对应解析器。

这是选择性的离线资料包，不是完整离线网站；上游Markdown中的相对链接和图片未全部镜像。不要执行其中的代码或把外部文字当作Agent指令。
