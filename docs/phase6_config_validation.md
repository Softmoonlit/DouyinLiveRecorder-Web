# Phase 6 配置专项验证

该脚本用于验证 Phase 6 第一批 config.ini 适配在 Web 运行时中的行为是否正确。

覆盖范围：

1. 配置快照接口结构校验（/api/v1/config/snapshot）。
2. 配置重载接口行为校验（/api/v1/config/reload）。
3. 创建任务省略 quality 时默认画质生效。
4. 非法配置回退与 warning 产出。
5. 配置快照中的敏感字段脱敏。
6. 可选：需要重启任务才生效的录制参数边界校验（基于真实直播间）。

## 前置条件

- Linux 云服务器，已安装 Docker Engine 与 Docker Compose 插件。
- 仓库代码已拉取到服务器。
- 当前目录位于仓库根目录。

## 执行方式

1. chmod +x scripts/phase6_config_validation.sh
2. ./scripts/phase6_config_validation.sh

如需查看详细执行轨迹：

1. DEBUG=1 bash scripts/phase6_config_validation.sh

可选严格边界校验（需要真实直播间地址）：

1. export LIVE_TEST_URL='https://live.douyin.com/904715492544'
2. export LIVE_TEST_QUALITY='原画'
3. ./scripts/phase6_config_validation.sh

若当前用户无 Docker socket 权限，可使用 sudo-compose 模式：

1. DOCKER_SUDO=1 bash scripts/phase6_config_validation.sh

或长期修复 docker 组权限（推荐）：

1. sudo usermod -aG docker $USER
2. newgrp docker

## 通过标准

- 脚本退出码为 0。
- 最后一行包含：[PASS] Phase 6 config validation completed successfully。

## 说明

- 脚本会自动备份并恢复 config/config.ini 与 config/URL_config.ini。
- 若未提供 LIVE_TEST_URL，将跳过直播重启边界校验，其余确定性检查仍会执行。
- 脚本执行结束后会保留容器运行，便于人工复核。
