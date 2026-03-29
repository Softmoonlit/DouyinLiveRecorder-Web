# Phase 4 验收基线

本基线用于验证以下能力：

1. 容器以 Web 入口正常启动。
2. 任务 CRUD 接口可正常工作。
3. 任务启动/停止在 disable=true/false 两种模式下行为正确。
4. 容器优雅关闭时可触发运行时清理。
5. 容器重启后可从 URL_config.ini 恢复任务状态。
6. 可选：在提供真实直播地址时，手动启动可进入录制状态。

## 前置条件

- Linux 主机，已安装 Docker Engine 与 Docker Compose 插件。
- 仓库代码已拉取到主机。
- 当前目录位于仓库根目录。

## 执行方式

若服务器上镜像命名冲突，先设置自定义镜像名：

1. export DOUYIN_RECORDER_IMAGE=your-registry-or-local-name:phase4

然后执行基线脚本：

1. chmod +x scripts/phase4_baseline.sh
2. ./scripts/phase4_baseline.sh

若需包含端到端录制断言（推荐在云主机且具备 ffmpeg 与真实直播间时执行）：

1. export LIVE_TEST_URL='https://live.douyin.com/904715492544'
2. export LIVE_TEST_QUALITY='原画'  # 可选，默认原画
3. export LIVE_TEST_TIMEOUT=120     # 可选，等待进入录制状态秒数
4. ./scripts/phase4_baseline.sh

## 通过标准

- 脚本退出码为 0。
- 最后一行包含：[PASS] Phase 4 baseline completed successfully
- 若设置了 LIVE_TEST_URL，脚本还必须通过直播任务断言：record_started=true、recording_status=recording、started_at 非空。

## 说明

- 脚本会创建一个临时任务，并在结束时删除。
- 若设置 LIVE_TEST_URL，会额外创建并清理一个直播校验任务。
- 脚本会通过检查 config/URL_config.ini 验证禁用任务持久化。
- 脚本通过应用日志标记 runtime shutdown requested= 验证优雅停机。
