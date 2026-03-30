# Web录制控制台与Docker落地计划（含config.ini适配）

## 一、目标
在保持现有录制能力稳定的前提下，继续沿用“Web状态层 + URL_config.ini双写”的低风险路径推进；并将“加载并适配 config.ini”纳入独立阶段，分批接入录制参数、推送参数与凭据参数，确保兼容 CLI 旧行为。

## 二、阶段规划

### Phase 1 - 架构梳理与服务化边界（阻塞后续）
1. 抽离 main.py 中任务调度、状态管理、录制生命周期逻辑，形成可复用接口（启动任务、停止任务、状态查询、配置重载）。
2. 固化任务状态机：未开播、监测中、开播未录制、录制中、停止中、失败。
3. 明确线程与子进程治理：任务句柄可追踪、可优雅停止、具备超时兜底。

### Phase 2 - 后端API与状态层（依赖 Phase 1）
1. 提供 REST 接口：任务列表、新增、编辑、删除、手动开始、手动停止、汇总看板。
2. 将全局状态封装为线程安全状态服务。
3. 双写 URL_config.ini，兼容 # 注释停录语义，并支持冷启动恢复。
4. 提供前端聚合字段：平台、主播名、直播状态、录制状态、开始时间、错误信息。

### Phase 3 - 前端控制台（并行于 Phase 2.4）
1. 完成任务表格、状态标签、操作按钮的单页管理台。
2. 支持任务增删改、暂停/恢复（映射 # 注释）、手动启停。
3. 提供状态看板与平台筛选。
4. 使用轮询实现实时刷新（后续可升级 WebSocket）。

### Phase 4 - Docker与运行模型（依赖 Phase 2/3）
1. 容器入口切换到 Web 服务。
2. compose 保留卷挂载并完善端口与运行参数。
3. 统一 shutdown，确保停止时可优雅清理任务与 ffmpeg 子进程。

### Phase 5 - 回归验证与发布（依赖全部前置）
1. 兼容性回归：CLI 历史 URL 配置与 # 语义不破坏。
2. 功能回归：任务 CRUD、启停、异常恢复。
3. 部署回归：容器启动可访问、重启后任务可恢复。

### Phase 6 - config.ini 加载与适配（后续开发）
1. 建立 config.ini 配置读取层（从 main.py 迁移 read_config_value 语义），支持默认值、类型转换与变更重载。
2. 按优先级分批接入：
- 第一批（录制核心）：视频保存路径、画质默认值、分段录制、输出格式、转码相关参数、循环间隔。
- 第二批（网络与稳定性）：代理开关与代理地址、并发线程数、HTTPS 强制录制、空间阈值。
- 第三批（通知与凭据）：推送渠道与模板、Cookie、Authorization、账号密码。
3. 定义生效策略：新增任务使用当前生效配置；运行中任务按“下一轮探测生效/显式重启任务生效”两级策略。
4. 增加配置可观测性：暴露“当前生效配置快照（敏感字段脱敏）”与“最后重载时间/结果”。
5. 保持兼容：若缺失配置项或格式异常，回退到默认值并记录可诊断错误，不阻塞服务主流程。

## 三、当前状态（2026-03-30）
1. Phase 4 验收通过：Phase 4 baseline PASS。
2. Phase 5 验收通过：Phase 5 regression PASS。
3. Phase 6 第一批专项验证通过：Phase 6 config validation PASS。
4. Phase 6.2 第二批专项验证通过：Phase 6.2 network stability validation PASS。
5. 下一步：进入 Phase 6 第三批（通知与凭据参数）接入与验证。

## 四、关键文件
1. d:/Code/DouyinLiveRecorder/main.py：现有 config.ini 读取与运行时参数来源（迁移参考）。
2. d:/Code/DouyinLiveRecorder/config/config.ini：目标适配配置源。
3. d:/Code/DouyinLiveRecorder/config/URL_config.ini：任务双写与禁用语义配置源。
4. d:/Code/DouyinLiveRecorder/app.py：Web 生命周期、配置加载与探测调度接入点。
5. d:/Code/DouyinLiveRecorder/src/runtime/api_manager.py：任务状态聚合与配置生效入口。
6. d:/Code/DouyinLiveRecorder/src/runtime/live_probe.py：探测与配置接入点。
7. d:/Code/DouyinLiveRecorder/src/utils.py：现有 read_config_value/update_config 可复用逻辑。

## 五、验证标准
1. 配置加载验证：服务启动后能读取 config.ini，并按默认值兜底缺失项。
2. 参数生效验证：修改核心录制参数后，新启动任务按新参数执行。
3. 兼容验证：旧版 config.ini 不完整时服务仍可运行，且错误可观测。
4. 安全验证：配置查询接口对 Cookie/Token/密码做脱敏输出。
5. 回归验证：URL_config.ini 与 config.ini 同时变更时状态与行为一致且无冲突。

## 六、决策与范围边界
1. 已确认：config.ini 适配纳入后续开发阶段，不阻塞 Phase 4/5 收口。
2. 已确认：继续保留 URL_config.ini 作为任务清单唯一事实源。
3. 已确认：config.ini 接入采用分批迁移，不一次性替换 main.py 全量逻辑。
4. 明确排除：本阶段不引入多用户权限与在线文件管理。

## 七、文档规范
1. 从本文件起，仓库后续新增与维护文档统一使用中文。
