# 通用Wokwi MCP返回格式补丁

这是对固定上游提交`940b7237d26f`的本地补丁，不是官方发行版。不修改固件、元件参数或生成工程，不绕过仿真服务。

改动仅包括：

1. 截图从截断的文本前缀改成标准MCP PNG image块。
2. 引脚读取保留原始响应，声明只读数字高低电平、不能读取电压/ADC/PWM；不猜测电压。
3. MCP服务标识包含补丁版本，仿真服务握手仍使用原版版本号和提交。

## 安装/重建

前提：已安装Node.js、npm，以及项目已有Python环境和Wokwi CLI。根目录运行：

```powershell
.\LangChain\.venv\Scripts\python.exe -X utf8 -B LangChain/integrations/wokwi_mcp/build_backend.py
```

脚本校验上游归档和原文件哈希，使用固定pnpm版本及上游lockfile安装构建依赖，默认不执行依赖安装脚本。源码、npm/pnpm缓存与编译文件均留在根目录temp；只有CLI bundle、上游许可证和manifest安装到tools/wokwi-mcp/0.29.0-hwclaw.1。不提交下载依赖或二进制，也不覆盖用户原先的wokwi-cli.exe。

修改补丁必须更新版本号，不能覆盖同版本的不同bundle。服务运行时验证bundle哈希；修改后需要重新安装与测试。构建成功后重启Agent服务。

没有安装修复版时使用原版CLI，保留原版截图截断限制；安装文件损坏时明确报错，不静默回退。当前ST7789模型的framebuffer接口问题未解决，此补丁不能创造服务没有提供的图像。

测试和证据见[集成文档](../../../docs/WOKWI_MCP_INTEGRATION.md)。测试夹具仅验证通用接口，绝不作为生产Agent生成答案。
