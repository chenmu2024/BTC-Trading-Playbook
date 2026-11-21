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

## 2026-11-21 — Five-year negative Funding & causal structure proxy research
- 新增2022—2026五份公共期货小时K线与Funding年度历史快照，合计42,839根小时K / 5,355条Funding。
- 新增多年事件研究、4h双Pivot确认支撑代理、SH→BMS→RTO仅多头代理与仓位/成本/止损止盈/资金费用模拟。
- 自动CI复算研究报告并提供JSON/Markdown Artifacts；添加样本统计与信号数量回归测试。
- 研究输出显示负Funding与回踩组合样本不足、未证实稳定正期望；原始Pine v3.3/Eric/V1.1逐K等价性仍UNKNOWN。

## 2026-11-21 — Pine validation exports, chart-data audit, Eric D3 core
- 原样保留三份用户Pine原脚本；新增独立遥测版用于TradingView导出CSV，带1H/4H等周期状态和必要的来源收盘时点字段。
- 新增CSV审计脚本及安全要求：OHLC必须与Binance BTCUSDT永续价格/时间匹配，拒绝不明时区及明显未来信号；缺样本状态NOT_TESTED。
- 根据Eric v1.9.10源代码实现LC2→Wilder RSI20→StochRSI26→K4→D3数学核心，并在BTC行情报告中单独展示；完整Episode/背离状态不可推断。
- 添加全部相关单元测试；不调整历史亏损策略以迎合收益，不启用实盘自动交易。

## 2026-11-21 — Run full historic observable five-step long/short backtest
- 新增`research/five_step_observable_backtest.py`与自动测试；使用已归档2022—2026 Binance OHLCV及Funding研究多空对称交易。
- 研究顺势A、区间逆势B；BMS和RTO分组、逆向Funding及连续3期过滤；下一根K开盘成交、95%名义敞口、0.5%/0.25%风险、2R、最长48h、8hK冷却、手续费滑点和资金费用。
- 首轮实际执行结果无跨阶段稳定正收益；删除冗余B区域过滤变体，增加多空分别统计。
- 新增[回测结论与复算说明](research/RESULTS_FIVE_STEP_2026-11-21.md)；保留原Pine v3.3/Eric/V1.1并明示其信号尚未逐K等价。

## 2026-11-21 — Funding lookahead repair and independent LONG-only research V0.2
- 修复三期Funding`fi+1`未来结算泄漏；加入过去三次结算时间窗单元测试；**旧版此模块研究成果已替代**。
- 新增9种真正独立的单方向模拟账户，独立输出交易清单、年度费用/Funding归因与模型/方向/年度候选信号漏斗。
- 阐明历史模拟参数与日常分析策略默认值不相同；公开完整参数快照。
- 综合结果：A顺势LONG+RTO两个阶段小幅盈利，但2026无交易；B逆势LONG+负Funding仅2026两笔盈利，未证明稳健预期收益。
