# BTC Trading Playbook

基于多周期结构、强支撑/压力、Eric Swing Filter、流动性扫盘与订单流的 **BTCUSDT 交易研究与人工决策支持仓库**。

> ⚠️ Research only / 非实盘自动下单系统。历史回测曾出现亏损；不能将脚本信号视为获利保证。仓库不存放 API 密钥、交易账号或个人持仓。

## 从这里开始
1. 阅读 [MASTER_STRATEGY.md](MASTER_STRATEGY.md)：交易理念、两种交易模型、模块责任。
2. 阅读 [ANALYSIS_SOP.md](ANALYSIS_SOP.md)：每次按仓库规则分析行情的标准流程；报告必须注明数据时间、来源和缺口。
3. 阅读 [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md)：触发条件、失效、仓位、成本和观望规则。
4. 查看 [config/strategy.yaml](config/strategy.yaml)：研究默认值，不是最优参数。
5. 按 [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) 输出有证据级别的现况与条件交易计划。
6. 对照 [RESEARCH_STATUS.md](RESEARCH_STATUS.md)：区分已读取、已编译、已回测和未验证的模块。

## 代码与来源
- `pine/strong_support_resistance_v3_3.pine`：用户提供的多周期确认强支撑与强压力 v3.3，保留原始源码。
- `pine/eric_swing_filter_v1_9_10.pine`：用户提供的 Eric Swing Filter v1.9.10，**实验版，未完成该版本平台编译/回放验证**。
- `pine/liquidity_sweep_v1_0.pine`：早期5步策略研究版，已有亏损回测证据。
- `pine/liquidity_sweep_v1_1_diagnostic.pine`：修改结构确认与回踩、仍须独立回测的诊断版。
- `docs/original_strategy_v1_0.md`：2026-11-20 原始综合交易体系文档。

以上脚本是独立指标/策略，**没有合并为单个策略，也没有完成跨脚本信号同步**。不应宣称仓库当前能自动执行全部决策。

## 每次分析的输入与输出
**输入**：本仓库当前 commit 和配置、BTCUSDT 指定交易所/市场、带时间戳的已收盘 K 线、必要时可获得的 OI/资金费率/成交数据。

**输出**：数据时间和完整度、日线/4H趋势、已确认支撑/压力、Eric状态、SH/BMS/RTO状态、成交量与订单流证据、多空情景、明确触发/否决条件、止损/目标与风险预算、最终状态（可评估/等待/禁止），以及下次需复核的事项。

不能读取的指标必须标为 **未知/未验证**，不能以其他信号替代并声称已经验证。

## 执行原则
- 价格结构触发，订单流用于寻找支持和反证，不设“全部同向”强制投票。
- 严格区分“预测场景 / 形成候选 / 已确认触发 / 已失效”。
- 不在未确认 Pivot、未收盘的高周期 K 线上回填交易信号。
- 当前只允许 **人工研究和模拟验证**，真实下单须另行评估。
- 策略版本化，复盘不允许用事后数据修改过去的判断。

更新记录见 [CHANGELOG.md](CHANGELOG.md)。
