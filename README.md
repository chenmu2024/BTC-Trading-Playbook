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

## 可以直接运行的公开行情研究引擎（2026-11-21 新增）
- 入口：`python -m engine.cli --config config/strategy.yaml --output-dir output`（Python 3.11+；`pip install -r requirements.txt`）。
- 输出：同时保存 **原始行情快照 JSON、结构化分析 JSON、中文 Markdown 报告**，方便下一次复盘。
- GitHub 页面操作：打开 **Actions → BTC market snapshot (manual, research only) → Run workflow**，运行结束下载 artifacts 中的报告，无需本地电脑、交易API密钥或付费行情服务。GitHub Actions资源额度和交易所网络访问以实际平台为准。
- 运行状态与限制见 [docs/ENGINE_USAGE.md](docs/ENGINE_USAGE.md)；此引擎仅有 **EMA/前高前低/扫盘代理/合约K线Delta与OI/费率**。并未复刻v3.3/Eric/V1.1完整信号。不要把代理读数当成原指标。
- 离线自动测试在每次push运行： [Actions](https://github.com/chenmu2024/BTC-Trading-Playbook/actions)；仅编译和单元测试通过不能证明策略盈利或原Pine一致。

## 负资金费率历史研究（已执行，2026-11-21）
- **最新结果与局限**：[2026-11-21 负费率事件研究](research/RESULTS_2026-11-21.md)。
- **研究代码**：[research/funding_event_study.py](research/funding_event_study.py)；**冻结公开数据**：[research/data](research/data)。
- 复算：`python -m research.funding_event_study --data research/data/binance_btcusdt_2026-05-01_to_2026-11-20.json --output-dir output/study`。
- CI使用固定快照对全部研究结果做回归校验，提供 JSON/Markdown 报告 Artifact，不依赖实时 API。
- **研究发现**：负资金费率单独作为BTC做多条件，在本次2026年5—11月样本中未展示可靠正期望；结构过滤事件过少，不能宣称组合盈利。资金费率仍保留为高优先级**观察指标**，不是买入信号。

## 2022—2026 资金费率与价格确认专项研究（已执行）
**最新正式结论**：[近五年资金费率 × SH/BMS/RTO 研究报告](research/RESULTS_2022_2026.md)。

- 冻结了2022—2026五份Binance USDⓈ-M年度数据：**42,839根完整1小时K线、5,355次Funding结算，负费率818次**。
- [跨年度Funding事件分析](research/multiyear_event_study.py)：按年度比较结算后24小时、72小时、7天模拟多头净收益，并做非重叠事件敏感性。
- [独立因果结构策略研究](research/causal_structure_backtest.py)：扫盘→微结构突破→可选回踩，按下一小时开盘、预设止损/2R目标和最多48小时退出进行模拟；对比负Funding过滤与未过滤。
- [4H双Pivot支撑代理](research/mtf_support_proxy.py) 必须经确认后才生效，**尚不等于用户的Strong MTF SR v3.3**，也未复刻 Eric v1.9.10。
- 结果不支持宣称整体有稳定盈利优势。GitHub CI会逐次复算并保存多年度事件/结构研究的JSON与Markdown结果，可在Actions Artifacts查看。
- 运行：`python -m research.multiyear_event_study`；`python -m research.causal_structure_backtest`。

## Pine 原始规则逐K数据核验（V0.1，已构建工具）
- **具体说明与数据导出方法**：[docs/TRADINGVIEW_PARITY.md](docs/TRADINGVIEW_PARITY.md)。
- **三份独立Pine遥测导出版**：[pine/validation](pine/validation)。原版 v3.3 / Eric v1.9.10 / Sweep V1.1 未被修改。
- **核验程序**：[research/audit_tradingview_csv.py](research/audit_tradingview_csv.py)，可检查Binance 1小时OHLC/时间戳是否与TradingView CSV一致、来源周期是否提前收盘，以及Eric数学D3是否接近。
- **Eric D3数学核心**：[engine/eric_core.py](engine/eric_core.py) 已按原脚本LC2→RSI20→Stoch26→K4→D3计算并接入日常行情报告，但**未完成真正的Pine导出逐K对照**；Episode/反转/严格背离仍不可替代为代理。
- 无CSV导出时只能声称“验证工具完成、数据尚未核验”，**不可声称完整指标等价**。
