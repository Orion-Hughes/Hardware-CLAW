# ESP-Claw Skills、Tools 与 Lua 组织调研

本次直接检查本地源码版本 `345073d`（2026-10-28），路径为 `references/projects/ESP-CLAW/Git-Clone`。这是源码阅读结论，不是新一轮固件运行测试，也不代表远端最新版本。本次未调用 LLM API，未修改生产 Agent。

## 1. 调研范围与关键结论

枚举到 22 个静态 SKILL.md、36 个 lua_modules 子目录、19 个 claw_capabilities 子目录。目录数量不是运行时启用能力数量：构建配置、模块注册和会话工具可见性还会影响实际能力。自动生成的技能也不能仅靠静态 SKILL.md 数量统计。

重点通读技能包规范、组件技能构建规则、skill_creator、app_creator、lua_package_authoring、plan_mode、read_touch、HTTP demo、字体转换技能；检查 BLE 的选择条件、API、事件与错误说明；追踪技能激活、工具分发、Lua 描述符、GPIO 绑定和文档索引生成代码。

最值得借鉴的是：能力实现、API 参考、操作流程、目录发现和执行状态之间存在明确连接。丰富度不只是技能数量，还来自模块资料和已有实现。

## 2. 源码布局与职责

```text
components/
  common/app_claw/             应用系统提示词、Provider、能力及 Lua 模块注册
  common/skill_builder/        技能包规范、构建时收集和冲突检查
  common/lua_module_builder/   从参与构建的模块生成文档/示例索引
  claw_modules/claw_core/      上下文组装和 Agent 循环
  claw_modules/claw_skill/     技能发现、读取、会话激活状态
  claw_modules/claw_cap/       工具注册、授权、可见性和调用分发
  claw_capabilities/cap_*/     具体工具实现，可附带自己的 skills/
  lua_modules/lua_*/          模块实现、README、test/，部分附带 skills/
application/edge_agent/
  boards/                     板卡定义及板级资料
  fatfs_image/storage/skills/ 应用提供的技能源文件
```

源码中的技能可分散归属于组件，构建时统一收集到 SYSTEM 镜像。运行时区分只读 SYSTEM 和可写 DATA；同 ID 的 DATA 技能可覆盖 SYSTEM 技能。不能把源码所在的 storage 路径直接理解为所有技能的最终运行位置。

不建议 Hardware-CLAW 为复制该布局而迁移所有目录。我们规模较小，可以集中维护技能，但明确工具、平台和资料的归属。

## 3. Skill 是包，不只是一个 Markdown

```text
skill_id/
  SKILL.md
  references/   可选，按需阅读的详细规则
  scripts/      可选，确定性操作
  assets/       可选，真实资源文件
```

- 只有 SKILL.md 必需，不创建空占位目录。
- JSON frontmatter 包含 name、description，可含 metadata.cap_groups 等字段。
- description 描述用户意图和适用前提，用于选择技能。
- `{CUR_SKILL_DIR}` 由运行时替换，避免绑定源码或设备绝对路径。
- 技能不能直接引用其他技能或 App 所拥有的文件，但可以通过激活另一个技能使用其工作流程。
- 构建阶段检查重复 ID、输出路径冲突，避免静默覆盖。

对我们的启发：由当前五个平铺 Markdown 演进为包结构；为目录提供用途和触发条件；详细方法放 references。不是每种器件都必须新增 Skill。

## 4. 调用链：目录 → 激活 → 工具 → 运行时 → 模块

1. app_claw 的 System Prompt 指导模型按技能工作。
2. Skills List Provider 输出 `id: summary`，不注入全部正文。
3. 模型调用 activate_skill。
4. cap_skill_mgr 加载正文、记录会话激活状态，并同步该会话可见的工具组。
5. Core 后续组装模型输入时提供相应工具定义；上下文提供器可每轮刷新，也支持请求开始时缓存。
6. claw_cap_call 检查工具是否可用、是否向当前调用者暴露，再调用 execute。
7. 工具实现解析输入并返回真实结果；不是仅有 JSON Schema 就完成全部校验。

read_touch 的具体路径：

```text
读取板卡信息并选定可用触摸 GPIO
→ 激活 read_touch
→ lua_run_script(path, args)
→ Lua runtime 加载 read_touch.lua
→ arg_schema / 参数处理
→ touch.new → read → close
→ 捕获输出或错误
→ Agent 解释结果
```

read_touch.lua 用 xpcall 与 cleanup 组织错误传播和资源释放。它是预先编写的动作脚本，不是这次用户请求生成的固件。

## 5. Lua 对生成质量的真正贡献

GPIO 示例显示了三个层次：

```text
Skill：何时调用、需要什么资料、如何理解输出
Lua：require("gpio")，组合已公开的操作
C 绑定：luaopen_gpio 注册函数，底层调用 ESP-IDF gpio_set_level 等 API
```

lua_package_authoring 明确要求：

- 编写前激活 builtin_lua_modules，并读取每个要导入模块的文档。
- 仅在相关时阅读测试脚本，学习 API 和资源生命周期。
- 不凭模块名称猜函数；Lua 不能增加未编译的原生驱动或能力。
- 明确参数、错误、输出、资源释放、阻塞和异步运行方式。
- 生成后回读文件，再交还 owning creator 完成包验证和发布。

builtin_lua_modules 由构建脚本自动生成，内容是模块→文档→测试示例路径表。文档内容来自模块维护的 Markdown，不是从函数签名自动推导完整语义；构建清单匹配也不证明文档本身一定正确。

对应 Hardware-CLAW：应提供与选定 framework、驱动库版本、器件配置相匹配的 API 资料索引。继续使用本地维护的知识库，运行任务时不临时联网猜测资料。缺失资料明确标记，离线维护后再支持相应能力。

## 6. 值得参考的具体技能

| ESP-Claw 来源 | 可借鉴内容 | 在我们这里的处理 |
|---|---|---|
| lua_package_authoring | 读 API 后生成、生命周期、参数与错误、回读 | 改写为通用固件编写方法，合并进现有 firmware skill |
| skill_creator / app_creator | 区分包结构和脚本实现；资源先写、入口后写；最终发布 | 借鉴工程文件组织和最终交付，不引入设备 App 管理 |
| board_hardware_info 生成器 | 从板卡数据生成资料摘要及占用 IO 信息 | 由现有知识库和工程记录派生，避免维护重复参数 |
| builtin_lua_modules 生成器 | 基于实际可用模块生成紧凑资料索引 | 参考实现驱动/API 索引，标注版本和适用平台 |
| plan_mode | 能力缺口、必要澄清、部分完成状态 | 提炼需求与可行性方法，不照搬所有操作都需确认的规则 |
| read_touch / take_picture 一类动作技能 | 前置条件、参数契约、输出含义和失败处理 | 学习描述结构，不复制成生成某个示例的答案 |
| ble | 区分 BLE 与 HID，说明不支持能力、共享资源和事件 | 提炼接口与资源冲突方法；具体 Lua API 不提供给 C++ 生成 |
| bdf_font_converter | 固定格式转换交给确定性程序 | 借鉴资源处理边界；其 DFN1 输出只适用对应显示模块 |
| cap_lua 异步工具族 | start/get/tail/stop、超时、独占组、增量日志 | 长时间编译/仿真/监控的参考，不要求立即新增整套工具 |

## 7. 推荐的技能组织方向

优先整理已有五个技能，不一次性增加大量文件：

1. **工程生成总流程**：明确设计、生成、检查、交付的职责和其他技能入口。
2. **需求与可行性**：输入输出、触发条件、时序、关键未知和默认值；可先做总流程的 reference。
3. **硬件与接口设计**：扩充 hardware_selection，覆盖电气/仿真管脚映射、占用和接口约束。
4. **固件编写**：扩充 firmware_and_observation，强调先读驱动 API，再设计状态、时序、数据流和错误处理。
5. **构建与交付**：保留 build_and_delivery，区分格式合同、平台配置和实际构建证据。
6. **已有工程修改**：读取现状、评估影响、同步代码/连线/依赖；可先做总流程的 reference。
7. **仿真反馈**：保留已有 simulation_feedback，本阶段不扩大审查功能。

跨工程通用的显示布局、字体编码、采样时序、按钮事件等可以成为按需参考资料。是否独立成 Skill，取决于是否有独立触发条件和足够内容；不要针对某个具体生成工程建立专用 Skill。

## 8. 可以直接取用什么，不能直接取用什么

- 可采用包结构、目录优先/按需读取、路径占位符、输入输出说明等设计。
- 通用文字可以保留适用段落并注明来源；完整工作流通常需改写工具名、平台、路径和交付对象。
- Python 索引/构建脚本可作为适配起点，但依赖 ESP-Claw 构建清单，不能宣称直接可用。
- Lua 驱动文档、Lua 业务脚本和设备管理 C 代码不适用于当前 Arduino/C++ 生成环境，暂不作为生产 Agent 指令导入。
- 上游根许可证为 Apache-2.0。实际复制文件时检查文件级声明，保留适用版权/许可、标注修改，并处理上游 NOTICE（如有）；本次只阅读与记录，没有复制上游代码进入生产实现。

## 9. 不能把上游当成无误标准

源码中也有可见的不一致：read_touch 的文档 schema 声明 GPIO 为整数，而脚本接受 number 后执行 math.floor；HTTP demo 说明 replace=true，而通用 lua_package_authoring 对替换运行中任务要求明确用户意图。二者提示我们必须核对文档、实现及适用场景，不能因为来源是上游就直接信任。

可见性控制不等于业务正确性；脚本启动不等于任务完成；Skill 的文字约束也不是程序强制检查。

## 10. 下一步实现顺序

1. 先确定 Skill 包格式和目录字段，以及只读参考资料读取方式。当前 load_skill 只返回正文，包结构单独迁移后模型未必能读取 references，必须同时检查访问链路。
2. 拆分独立 System Prompt；Context Provider 提供真实工程摘要、能力/资料索引与技能目录。
3. 整理并加强现有生成技能；派生 API 索引，避免再手写一套重复硬件库。
4. 按需记录激活技能状态；工具分组先建立映射，是否动态隐藏等有使用证据后再决定。
5. 选择不同类型需求进行真实 Agent 对比，记录生成质量、错误、调用次数、耗时和 token，不手工修补输出。

## 源码定位（相对本地 ESP-Claw 根目录）

- `components/common/skill_builder/skills/skill_creator/references/skill-package-spec.md`
- `components/common/skill_builder/COMPONENT_SKILL_BUILD.md`
- `components/common/skill_builder/skills/skill_creator/SKILL.md`
- `components/common/lua_module_builder/skills/lua_package_authoring/SKILL.md`
- `components/common/lua_module_builder/tools/generate_builtin_modules_skill.py`
- `components/common/app_claw/app_claw.c`：APP_SYSTEM_PROMPT_COMMON、Skills List Provider
- `components/claw_modules/claw_core/src/claw_core_context.c`：claw_core_build_iteration_context
- `components/claw_capabilities/cap_skill_mgr/src/cap_skill_mgr.c`：cap_skill_activate_execute
- `components/claw_modules/claw_cap/src/claw_cap.c`：claw_cap_call
- `components/claw_capabilities/cap_lua/src/cap_lua.c`：s_lua_descriptors
- `components/claw_capabilities/cap_lua/src/cap_lua_runtime.c`：cap_lua_runtime_execute_file
- `components/claw_capabilities/cap_boards/tools/generate_board_skill.py`
- `components/lua_modules/lua_driver_touch/skills/read_touch/`：技能与脚本
- `components/lua_modules/lua_driver_gpio/`：README 与 C API 绑定
- `components/claw_capabilities/cap_app_mgr/skills/app_creator/SKILL.md`
- `components/lua_modules/lua_module_ble/skills/ble/SKILL.md`
- `components/lua_modules/lua_module_http_server/skills/http_server_lua_demo/SKILL.md`
- `components/lua_modules/lua_module_display/skills/bdf_font_converter/SKILL.md`
- `application/edge_agent/fatfs_image/storage/skills/plan_mode/SKILL.md`
