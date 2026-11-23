# Git协作

默认分支为`main`。模型密钥和本机运行数据不随公开代码分发。

## 新成员

```powershell
git clone https://github.com/Orion-Hughes/Hardware-CLAW.git
cd Hardware-CLAW
git switch -c feature/your-change
```

按[环境配置](SETUP.md)准备自己的API和编译环境，阅读[约束](../../AGENTS.md)。没有写权限时通过GitHub Fork提交Pull Request；不共享账号或API密钥。

## 提交

```powershell
git status --short
git diff
# 先运行相关离线测试
git add <本次修改的文件或目录>
git diff --cached --stat
git diff --cached
git commit -m "说明功能与验证范围"
git push -u origin feature/your-change
```

每个功能形成可解释的提交，Pull Request写清测试、未验证部分和失败证据。真实模型测试需先约定预算，统计调用、耗时和token；不把离线fixture当成功能验收。

更新主分支前确认无未提交修改，再`git pull --ff-only`。冲突或分叉先分析，不覆盖他人改动、不强制推送。Codex默认功能分支用`codex/`前缀。

## 不提交什么

- API文件、`.secrets/`、`.env`、Wokwi token；
- `workspace/`真实工程、聊天、任务数据库、固件；
- `temp/`日志和缓存；
- `.venv/`、`tools/`、`pio/`、`node_modules/`等安装目录；
- 私人材料、历史研究/实验归档、无关的外部项目克隆。

保留知识库上游原文、来源锁、许可和可重复的软件机制测试。忽略不会移除已跟踪文件，也不能消除历史凭据。若误提交密钥，先吊销/更换，再协调历史清理；不能只删当前文件就声称安全。

知识库按原始字节校验哈希，`.gitattributes`关闭自动换行转换。第三方许可不因公开而改变，见[来源说明](../../THIRD_PARTY_NOTICES.md)。

## 查看版本

GitHub的Commits显示已推送提交。本地可运行`git log --oneline --decorate -20`和`git show <提交ID>`；未提交或未推送内容不会出现在GitHub。
