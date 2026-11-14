# Hardware-CLAW 硬件资料入口

现有 17 张索引卡（9 类已购、1 个明确仿真变体、7 个非采购参考），另有 146 个原始 Wokwi 元件定义。新增或更新卡片请按[新硬件入库指南](../../docs/HARDWARE_ONBOARDING.md)操作，实际验证记录与卡片状态分开看。

## 目录

```text
knowledge/
  cards/                 人工维护的薄连接层：选型信息、信号映射、三个资料入口
  guidance/              有来源的器件注意事项和统一阅读规则
  platforms/             当前程序需要的明确平台配置；不是所有 MCU 通用参数
  schemas/               索引卡机器格式
  upstream/
    wokwi-diagram-lint/   官方元件端点和属性定义
    wokwi-docs/           官方文档完整 docs 快照，保留引用的图像
    wokwi-boards/         所选板卡/显示模块原始定义
    drivers/             驱动维护者源码、README、例程、库元数据和许可
    platform/            固定版本 Arduino/PlatformIO 原文
    models/              第三方仿真芯片原文
    vendor/              厂家与平台网页原文
  catalog.json           ID 到索引卡、Wokwi 类型到原始定义的目录
  sources.lock.json      上游来源、版本、哈希、原获取记录
  library.json           库格式与来源校验开关
```

不再保留旧 owned/reference 手写全量 profiles 或 supplements 混合目录。旧资料整体移到根目录 backups 中，不参与运行时查询。上游原文按原字节保存，哈希可核对；其 JSON/Markdown/HTML 可能包含上游语法、相对链接或已过时说明，不假定每份文件可无损转成严格 JSON。

## 一张卡提供什么

- `selection`：功能、输入输出、接口、关键约束、引脚资源要求、来源。
- `inventory` / `record_role`：实物采购、仿真变体或参考，不能按文件夹判断已购。
- `simulation`：模型类型、逻辑信号到模拟端点、实例属性及差异。
- `programming`：当前整理的平台范围、库元数据入口、头文件和明确的仿真供电配置。库名/版本从原始 library.properties 读取；不把声明兼容写成验证通过。
- `documents.simulation` / `api` / `guidance`：每项有 ref、purpose、read_when、load，分别说明文件位置、作用、何时阅读、是否基础必读。load只能为essential或reference，维护时确定，不由模型临时判断。三组均保留；缺少来源可以为空并写缺口，不伪造链接。
- `availability`：资料级可用状态、缺口和三个独立验证状态。
- `observation_controls`：已有来源支持的模型观测入口，不由 attrs 自动推断。

卡内 `ref` 统一相对本目录。`provenance.inventory_ref` 相对项目根目录；采购事实不是厂家规格。平台当前仍是 ESP32-S3/Arduino 2.0.17 仿真基线，多板卡扩展尚未完成。

## 首批卡

已购：ESP32-S3 N32R16V、DHT22 红板、ST7789 240×320、8灯 WS2812 灯环、SG90、PS2 摇杆、USB 摄像头、驻极体咪头、8Ω/1W 扬声器。

参考：ST7789 240×240 仿真变体、SSD1306、MPU6050、DS1307、HC-SR04、电位器、12mm 轻触按钮、BMP180。连接线和面包板按之前决定不纳入索引卡。

摄像头/咪头/扬声器没有完整可靠的对应模型，采购 ST7789 与当前模拟尺寸不符，保留 blocked；不能为了增加“支持数”改用不等价元件。

## 读取与旧接口适配

Agent仅注册两个硬件工具：`search_hardware`返回可用于选型的功能、输入输出、接口、资源约束和缺口；`read_hardware`一次接收1–8个已选硬件，自动提供基础原文、模型元数据、驱动依赖和平台配置。同一个文档和平台配置在一次结果中只出现一次。

`read_hardware`默认读取load=essential的文件，load=reference的文件只列出入口。documents.status区分included/reference/omitted/error；预算不足的文件不截断，标为omitted。补读时传references，只读指定原文，不重复基础包和平台说明。JSON预算默认56000字符，最多60000，包含元数据；单份原文过大仍可能无法装入，不能重复调用冒充已读。complete不表示足以编程或验证通过。

`KnowledgeCatalog`仍为现有工程服务派生兼容profile，不在磁盘维护第二套资料。旧get_hardware_info/read_hardware_documents包装仅留作内部兼容及测试，不再向Agent注册。阶段和子Agent机制尚未实现。

完整上游数据保留在本地，不代表全部发送给模型。索引卡负责选型，后续仅按任务需要读取对应入口。更进一步的阶段上下文和子 Agent 系统尚未实现。

来源调研见 [调研报告](../../docs/WOKWI_LIBRARY_SOURCE_SURVEY.md)。旧库备份位于 `backups/hardware-cards-20261102/knowledge`（相对项目根目录），仅保留作回溯，不参与运行。

初次建库完成116项离线测试；双工具接口改造后126项离线测试通过，覆盖批量组合、共享去重、补读、路径拒绝、哈希异常和预算遗漏。真实Agent查询结果另见[双工具测试记录](../../docs/HARDWARE_QUERY_TESTS_20261102.md)。未编译目标固件、运行器件仿真或验证实物。SSD1306仍为unreviewed；其余10张资料级配置为documented_not_tested，4张为blocked。
