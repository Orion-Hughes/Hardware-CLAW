# 外部工具适配（预留）

封装编译、Wokwi、串口等外部接口，输入受控工程/修订与运行上下文，返回执行结果和证据。命令使用参数数组；检查墙钟超时、取消、子进程树回收及输出大小。

现有参考执行器在Wokwi/runner/run_wokwi_test.py，本轮保持原位且未执行。接入前审查路径和报告，不向Agent开放任意shell。Wokwi CLI默认依赖远程Simulation API。
