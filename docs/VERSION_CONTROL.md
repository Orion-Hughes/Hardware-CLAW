# Git版本管理

根目录为Hardware-CLAW源码仓库，主分支main。GitHub默认使用私有仓库，当前本地基线不代表所有功能验收通过。

纳入：LangChain程序、知识库及来源/许可、skills、模板、测试、项目文档、参考索引和Wokwi实验源码。

不纳入：密钥、聊天数据库、workspace生成工程、temp日志与构建缓存、虚拟环境、已安装工具链、ESP-Claw独立克隆、学校报销和汇报材料。忽略不会删除本地文件。需要正式保留的基准工程或评估数据，应审核后加入examples或evaluations，而非整体提交workspace。

知识库锁文件包含原始文件哈希，.gitattributes关闭自动换行转换，避免clone后改变资料字节。第三方资料保留原有来源和许可；本次不替第三方资料重新授权。

## 日常流程

在D:\Hardware_CLAW执行：

```powershell
git status --short
git diff
git add <本次修改的文件或目录>
git diff --cached --stat
git commit -m "说明本次功能修改"
git push
```

每个完整功能或修复形成一个提交；先运行相关测试，确认暂存范围后提交。较大改动使用feature分支；不强制推送、不自动提交密钥或生成工程。跨电脑工作前先git pull --ff-only，有本地未提交修改或分叉时先处理，不能覆盖。

首个基线覆盖工程生成、编译、受限DHT22仿真评估、持续修改与聊天历史。已知DHT生成结果仍可能TIMEOUT，不能以提交或同步成功代表功能验收通过。

## 新电脑

源码同步不包含Python环境、PlatformIO安装、Wokwi CLI和API token。参考LangChain/README.md恢复环境；本地密钥按原约定另行配置，不写入Git。当前启动/编译流程仍有Windows和本机路径约束，不宣称已完成跨平台打包。
