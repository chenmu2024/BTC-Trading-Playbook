# BTC 纯五步交易漏斗｜默认分析规范 v0.4

**正式分析默认不使用 Eric。** Eric v1.9.10 只作为显式开启的研究附录，不参与入场、否决、状态转换或方向选择。仓库仅用于公开数据研究，不下单、不承诺盈利。

## 五步与数据证据

| 步骤 | 核心问题 | 研究边界 |
|---|---|---|
| 1 大周期环境 | 已收盘1D/4H上涨、下跌还是矛盾？ | EMA50/200与K线结构是代理，分歧明确标记 |
| 2 流动性位置 | 过去已完成K线的前高、前低、平行高低在哪里？ | 未见真实止损簿不能称已证实止损分布；不能把前高低冒充v3.3强区 |
| 3 SH → BMS → RTO | 哪根K下扫/上扫收回？何时突破微结构，何时回踩？ | 仅收盘确认；必须有截止时间、失效理由；过期信号不能事后补确认 |
| 4 量能与衍生品 | Volume、K线taker Delta、OI、已结算Funding支持还是反证？ | 不是指标同向投票；负Funding不等于买点；OI变化不代表净增空头 |
| 5 执行与风险 | 失败价、净2R空间、成本与仓位预算是否可核验？ | 缺失任何关键条件则WAIT。只用于研究，不自动下单 |

## 价格行为状态机（1H价格数据代理）

`engine/five_step.py` 独立跟踪每个候选：

`WAIT_BMS → WAIT_RTO → CONFIRMED_RTO`

另可能出现：
`INVALIDATED_BEFORE_BMS`、`EXPIRED_BMS`、`INVALIDATED_BEFORE_RTO`、`EXPIRED_RTO`。

默认参数（源自`config/strategy.yaml`）：

- **SH**：前20根已收盘1H高低点。刺破至少0.1ATR，收回至少0.05ATR，影线占比≥30%，成交量≥此前20根均量×0.8。
- **BMS**：扫盘K之后4根完整1H K以内，方向性实体≥0.2ATR；多头需收盘超过扫盘K及扫盘前3根高点，空头对称。扫盘K不能同时视作BMS。
- **RTO**：BMS之后5根内回踩其参考水平，多头低点位于该水平附近（-0.35ATR到+0.15ATR）并阳线收回；空头对称。
- **失效**：后续K线破扫盘极值，保守优先判失效；超时后不允许未来行情倒填确认。
- **时间**：任何事件只有该根K收盘后才可以确认。独立计算的“历史CONFIRMED_RTO”不是当前就能执行的交易。
- **风险**：A顺势研究预算每笔权益上限0.5%，B逆势上限0.25%；仅在新信号和足够入场/止损/目标空间可核验时才讨论风险。没有已验证交易信号仍返回WAIT。

**限制**：上述为价格行为观察代理，不是原`pine/liquidity_sweep_v1_1_diagnostic.pine`逐K等价性证明；真实逐笔CVD、长期OI与v3.3原脚本强区也未全部接入。

## Eric研究与主流程隔离

```yaml
analysis:
  primary_method: pure_five_step
swing:
  research_overlay_enabled: false  # 默认不计算Eric
  entry_gate_enabled: false        # 强制禁止Eric触发/否决
```

若仅为研究Eric的增量价值，`research_overlay_enabled: true`会在最终报告后添加**未验证Pine一致性的D3数学核心研究附录**，并且不改变`decision`、`five_step_funnel`或任何风险参数。设为`entry_gate_enabled: true`，CLI明确拒绝。

## 五年回测与版本隔离

- 冻结历史回测使用**BMS确认5根、扫盘量比1.0×**，而当前日常报告是**4根、0.8×**。
- 两者不能互相套用历史收益；研究旧代码与归档数据保持不变。
- 最新独立方向结果 `research/RESULTS_LONG_FUNDING_FOCUS_V0_2.md` 尚无稳定的统计优势证据。
- 当前策略状态`research_only`：未完成原Pine逐K核验、真实下单验证或样本外正期望证明。

## 验收

```bash
python -m unittest discover -s tests -v
python -m engine.cli --config config/strategy.yaml --output-dir output
```

默认Markdown应只有纯五步：趋势/位置/SH-BMS-RTO/量能与Funding/风险，**无Eric D3段落**。只有研究选项开启才出现附录。每次需保存数据与仓库commit、时间戳、失效/超时理由，禁止改写过去记录。
