# Phase 6.2 第二批（网络与稳定性）专项验证

该脚本用于验证 Phase 6.2 第二批 config.ini 适配在 Web 运行时中的行为是否正确。

## 覆盖范围

1. 配置快照中包含第二批参数：并发线程数、空间阈值、HTTPS 强制录制。
2. 代理开关与代理地址配置可重载生效，且代理地址在快照中脱敏。
3. 并发线程数支持合法值、非法值回退与边界钳制。
4. 空间阈值支持浮点解析、非法值回退。
5. HTTPS 强制录制开启后，录制输入地址从 `http://` 转为 `https://`。
6. 直播探测层应用配置的并发线程数。
7. 当磁盘剩余空间低于阈值时，新录制启动会被阻止并返回明确错误信息。

## 执行方式

1. `chmod +x scripts/phase6_network_validation.sh`
2. `bash scripts/phase6_network_validation.sh`

## 常见问题

1. 若出现 docker.sock 权限错误，可用：
   `DOCKER_SUDO=1 bash scripts/phase6_network_validation.sh`
2. 如需详细日志：
   `DEBUG=1 bash scripts/phase6_network_validation.sh`

## 通过标准

1. 脚本最后输出：`[PASS] Phase 6.2 network stability validation completed successfully`
2. 脚本退出码为 `0`
3. 验证结束后会自动恢复 `config/config.ini` 与 `config/URL_config.ini`
