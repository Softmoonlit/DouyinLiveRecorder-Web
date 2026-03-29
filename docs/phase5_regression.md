# Phase 5 回归基线

本基线用于验证以下内容：

1. 兼容性回归：旧版 config/URL_config.ini 行格式可正确解析，且 # 禁用语义保持不变。
2. 功能回归：任务 CRUD、启动/停止、不支持平台异常恢复、看板接口结构稳定。
3. 部署回归：容器启动、重启恢复、优雅停机整体健康。

## 前置条件

- Linux 主机，已安装 Docker Engine 与 Docker Compose 插件。
- 仓库代码已拉取到主机。
- 当前目录位于仓库根目录。

## 执行方式

若服务器上镜像命名冲突，先设置自定义镜像名：

1. export DOUYIN_RECORDER_IMAGE=your-registry-or-local-name:phase5

然后执行基线脚本：

1. chmod +x scripts/phase5_regression.sh
2. ./scripts/phase5_regression.sh

## 通过标准

- 脚本退出码为 0。
- 最后一行包含：[PASS] Phase 5 regression completed successfully。
- 执行过程中所有兼容性/功能/部署断言全部通过。

## 说明

- 脚本会临时改写 config/URL_config.ini 为旧格式样例，并在退出时（成功或失败）恢复原文件。
- 脚本结束后会保留 app 容器运行，便于人工复核。
- 不支持平台恢复断言使用 https://example.com/... 地址，避免依赖特定环境的真实直播源。