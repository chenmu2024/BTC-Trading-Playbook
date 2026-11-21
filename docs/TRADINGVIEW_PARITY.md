# TradingView Pine 指标逐K验证｜导出与数据审计 V0.1

> **本目录不是原指标算法等价性证明。** 当前完成的是：Pine原始计算过程旁路导出 → CSV数据对齐 → 排查未来时点、行情来源错误 → 等待真实导出数据后才能逐K复核。
> 
> 用户原始的三份Pine指标/策略不修改，生成独立的验证拷贝。脚本源码已在GitHub保留。

## 1. 为什么必须做这一层

此前2022—2026研究的 `research/mtf_support_proxy.py` 与 `research/causal_structure_backtest.py` 只是Python代理算法：
- `strong_support_resistance_v3_3.pine` 包含来源周期确认、独立测试、区间锁存、结构分与有效期，不能用简单前高前低替代。
- `eric_swing_filter_v1_9_10.pine` 包含 LC2→RSI20→Stoch26→K4→D3、反转/稳定状态、严格背离与MTF同步，不能靠直接算RSI或随机指标宣称已复现。
- `liquidity_sweep_v1_1_diagnostic.pine` 有动态设置信号状态机、扫盘/BMS/回踩及成交模型；现有Python独立实验也不等于逐K复刻。

## 2. 保留原版，新增导出版

| 原脚本（不修改） | CSV数据导出版（额外列） |
|---|---|
| `pine/strong_support_resistance_v3_3.pine` | `pine/validation/strong_support_resistance_v3_3_export.pine` |
| `pine/eric_swing_filter_v1_9_10.pine` | `pine/validation/eric_swing_filter_v1_9_10_export.pine` |
| `pine/liquidity_sweep_v1_1_diagnostic.pine` | `pine/validation/liquidity_sweep_v1_1_export.pine` |

每份导出版只更改脚本显示标题，并在源码末尾新增 `plot(..., display=display.data_window)` 遥测字段。**核心计算没有主动改写**；单元测试检查拷贝与原始源码在导出增量之前一致。 
注意：新增导出代码尚未在TradingView实际编译/回放；即使CI静态校验通过，仍需要平台运行验收。

### 支撑压力输出
每个30m/1h/4h/1d/1w周期：
- `SR_<tf>_support_center`、`support_halfwidth`、`support_score`
- `SR_<tf>_resistance_center`、`resistance_halfwidth`、`resistance_score`
- `SR_<tf>_source_close_unix_s`（来源周期最近收盘时间，UTC Unix秒）
- 新确认强区及失效事件计数 `new_event_count`、`invalid_event_count`

### Eric 输出
30m/1h/4h/1d/1w 的 `D3`、`STATE`；额外的1H/4H `PHASE` 和来源收盘时间；反转超买/超卖、底/顶背离、MTF共振新事件等布尔数字列（0或1）。

### Liquidity Sweep输出
`SWEEP_sweep_long` / `sweep_short`、`bms_up` / `bms_down`、`entry_long` / `entry_short`、阶段和方向、扫盘极值、BMS价位、止损/目标及估算Delta。

## 3. TradingView导出流程（首次需要浏览器操作）

1. 在 TradingView 新建**标准K线**图表，选择 **Binance BTCUSDT 永续**（通常可用 `BINANCE:BTCUSDT.P`，请确认实际上是USDⓈ-M BTCUSDT永续而非现货或其他交易所）、**1小时**周期。
2. 保持原代码默认参数，后续若更改参数必须同时保存参数版本、合约/交易所、脚本版本、K线图类型、时区与导出时点。暂不要使用 Heikin Ashi、Renko、连续合约或非标准K线。
3. 复制以上第一份 `pine/validation` 脚本，在 Pine Editor 保存并添加到图表；先核实脚本**编译通过、没有运行时错误、表格数值正常**。依次重复另外两份。
4. TradingView 图表右上角更多菜单选择 **Export chart data / 下载图表数据**，导出含脚本 `plot` 的CSV文件。TradingView官方说明会导出图表OHLC与脚本绘制的数据列；`display.data_window` 不会妨碍导出数值。
5. 导出尽可能多的2026历史小时K（图表必须实际加载；向左滚动以增加加载深度）；与数据 `research/data/multiyear/btcusdt_2026_through_2026-11-20.json` 发生时间交集即可。尽量保留CSV原始表头。
6. 一个图表每次仅加载一份验证脚本，以免指标列同名、导出表过大。CSV里不要包含个人账户、持仓、用户名等非公开信息。
7. 分别保存：
   - `research/parity/exports/sr_1h.csv`
   - `research/parity/exports/eric_1h.csv`
   - `research/parity/exports/sweep_1h.csv`
   
   如果不希望公开分享图表历史，**不要上传到公开GitHub**，也可以本地用命令行验证或作为聊天附件提供。只要在本地保存无私人信息就行。

## 4. 仓库自动核验（CSV存在时才可执行）

命令如下（任选其一）：

```bash
python -m research.audit_tradingview_csv --csv research/parity/exports/sr_1h.csv --kind sr --output output/parity_sr.json
python -m research.audit_tradingview_csv --csv research/parity/exports/eric_1h.csv --kind eric --output output/parity_eric.json
python -m research.audit_tradingview_csv --csv research/parity/exports/sweep_1h.csv --kind sweep --output output/parity_sweep.json
```

该审计：
- 精确匹配时间戳与Binance的1小时 `open/high/low/close`，默认价格误差≤0.2 USDT；
- 要求至少100根重合K，否则拒绝声称数据质量通过；
- 检查脚本来源周期的最近已收盘时间不能超前于主图K线收盘时间；
- 统计导出列非空数量和候选事件数，识别缺列、错合约、价格失配、时间错位；
- Eric导出另可比较 `ERIC_1h_D3` 与已移植的[数学核心](../engine/eric_core.py)：默认跳过年初首400根参考K线以降低Wilder RMA初始值影响，在可比100根以上的样本中按0.05 D3点容差列出偏差。状态可能是 `D3_MATH_MATCH`、`D3_MATH_MISMATCH` 或 `INSUFFICIENT_DATA`。这仅测试数学核心，不测试Eric的Episode、背离或多周期状态机。
- 输出 `CHART_DATA_VALIDATED` / `CHART_DATA_MISMATCH`，**完整算法一致性始终标 `NOT_TESTED`**，直到逐K比较独立实现的全部状态机；即便D3数学核心通过，也不能把整个Eric标为 `VERIFIED`。

### 匹配阈值、数据范围
- 单价容差 0.2 USDT 是审计阈值，不是原脚本参数；如果出现系统性偏差，应先查合约/交易所/时区，不建议随意放大容差。
- K线时间字段必须UTC或带明确时区；无时区字符串要显式 `--assume-utc`，否则拒绝猜测时区。
- 最新快照可能不覆盖所有CSV历史K，此类未匹配K只报告，不能将其视为算法相等/不相等。
- 没有足够交集或缺少正确列时验收失败；缺少导出CSV时验证**未开展**，不能宣称成功。

## 5. 逐K真正等价的下一关

只有拿到上述三个TradingView导出样本后，才能依次：
1. 实现以Pine逐K状态机为准的结构、D3、背离、回踩计算，对齐图表时间和数据源；
2. 对每个有效指标列计算数值误差、状态触发时点差、事件漏报/误报；
3. 独立审查历史回看、来源确认延迟和barstate时序；
4. **达到事先规定的匹配率/最大误差门槛后**，在 `RESEARCH_STATUS.md` 中升级各模块状态；
5. 用已对齐的真实规则重新跑多年度消融与样本外研究。

不能因为CSV的OHLC一致就把 `v3.3`、`Eric` 或 `V1.1` 直接标为 `VERIFIED`。

官方参考：
- https://www.tradingview.com/support/solutions/43000537255-how-to-export-chart-data/
- https://www.tradingview.com/pine-script-docs/faq/indicators/
