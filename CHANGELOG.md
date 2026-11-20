# CHANGELOG

## 2026-11-20 — Research repository bootstrap
- 建立研究仓库及五步分析和双模型A/B责任边界。
- 原样收录用户的强支撑压力v3.3、Eric Swing Filter v1.9.10、Liquidity Sweep V1.0/V1.1，以及原创综合方案文档。
- 确立统一分析SOP、来源时间戳规范、仓位与失效要求、数据缺失协议、回测实验设计和分析报告模板。
- 明确说明早期V1.0回测亏损、新版仍待平台编译/回放、外部Python与Pine指标尚未证明等价。
- 该版本无实盘自动下单、无定时监控、无已验证正期望声明。

## 2026-11-21 — Public-data proxy engine 0.2
- 新增 Binance USDⓈ-M BTCUSDT 只读公开行情采集；完整K线过滤、EMA50/200、前高低代理、简单扫盘候选、K线主动成交Delta、OI及最近结算费率。
- 新增Markdown和JSON报告、原始快照归档、离线单元测试与GitHub CI。
- 新增可手动运行的GitHub Actions行情研究（不自动提交、交易或定时监控）。
- 所有v3.3、Eric、V1.1的Pine逐K一致性状态仍为UNKNOWN；持续使用WAIT而不是买卖信号。

## 2026-11-21 — Funding Contrarian Watch V0.3
- 将负资金费率提升为高优先级独立观察层，不允许仅凭费率开多。
- 新增历史结算费率分析、频率归一化、连续负费率、极端分位及回归测试。
- 已保存的Pine指标源码未修改，策略维持research_only且不自动下单。

## 2026-11-21 — Settled negative-funding event study V0.1
- 添加公开数据冻结快照（4,895根1h BTCUSDT期货K线、615次历史已结算Funding）。
- 添加研究程序与回归单元测试；入场在结算后下一小时开盘，使用固定24h/72h/7d持有、模拟手续费/滑点/持仓Funding。
- 新增非重叠事件检查、按2026-09-01切分的后段观察，以及2026-11-21正式研究结论。
- 目前不支持负Funding即可买入；组合过滤样本不足，待未来独立数据验证。
