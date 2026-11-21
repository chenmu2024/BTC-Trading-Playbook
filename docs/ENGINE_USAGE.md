# 公开行情分析引擎 v0.2（研究 / 非实盘）

## 能做什么
- 只读 Binance USDⓈ-M 永续 BTCUSDT 的 1W/1D/4H/1H/30m OHLCV。
- 剔除未收盘K线，计算EMA50/200趋势代理；计算此前20根已收盘K高低点代理（**非** v3.3强区）。
- 标注近期1H简单扫盘候选和粗略结构突破代理（**非** 原版Liquidity Sweep V1.1 / SH+BMS+RTO信号）。
- 利用 Binance K线中的 taker-buy base volume 构造每K主动成交量差及24小时窗口净差（**非** ExoCharts逐笔CVD）。
- 读取最近可用OI统计及已结算资金费率；写出来源时间与缺失原因。
- JSON与Markdown双份报告。未经完整逐K一致性验收，最终状态为WAIT或DATA_INSUFFICIENT。

## 运行
需要 Python 3.11+。依赖仅 PyYAML（开源免费）。
```bash
python -m pip install -r requirements.txt
python -m engine.cli --config config/strategy.yaml --output-dir output
python -m unittest discover -s tests -v
```
保存的 `output/` 报告不会自动上传GitHub，也不会运行后台任务。网络失败或地区访问限制会写入报告的数据错误；缺少必需周期时程序返回状态DATA_INSUFFICIENT及退出码2。

离线验证：先准备与 `fetch_snapshot` 返回结构相同的JSON，然后
```bash
python -m engine.cli --snapshot-file path/to/snapshot.json --output-dir output
```
用于离线复核的是保存的 **原始历史快照**，而不是重写交易逻辑后的事后行情。

## 数据限制（务必阅读）
- Binance公开数据可能存在服务不可用、地区限制、数据修订、频率限制。连接失败不能用前一天价格假装实时行情。
- OI使用USDⓈ-M openInterestHist报告字段 `sumOpenInterest`，其合约/资产计量须以交易所合约规格为准。OI增加不代表新空头。
- Funding是已结算值，不是下一期预测费率；两者不能互换。
- K线 taker delta 仅是同交易所、同K线、同基础资产单位的成交统计，计算窗严格写明；与不同源、逐笔或足迹图CVD不同。
- 日线与周线EMA使用从最早加载K线进行SMA播种的有限窗口计算；与TradingView完整历史图表EMA可能略有差异。
- v3.3 / Eric / Sweep V1.1的内部确认状态机 **尚未进行逐K一致性移植**，因此现在不能得出其“实时已确认信号”。
- 程序没有交易所认证、钱包API密钥、下单调用或高杠杆功能。
- 无盈利优势证明；历史 V1.0 回测曾亏损。不要据此自动交易。

## 下一阶段（尚未做）
1. 验证GitHub Actions离线测试通过。
2. 从TradingView逐K导出Eric/强区指标信号，建立对照fixture，确认高周期/低周期时序及Pivot延迟。
3. 外部引擎逐K复刻并跑一致性测试，才能升级UNKNOWN为VERIFIED。
4. 保持参数冻结，按时点记录真实分析输出，随后进行样本外统计，不利用未来数据挑结果。

## 采集完整性检查（2026-11-21）
- 对 Binance 各时间框架检查K线开盘时间是否严格相邻；发现缺K线会拒绝对应时间框架。
- 最新已收盘K线过旧（超过两个来源周期）时标记该周期数据错误；日线/4H/1H不能满足要求则决策为DATA_INSUFFICIENT。
- 离线历史快照用于事后复核，不代表实时行情；离线模式不采用当前时间去否定历史日期。

## 负资金费率模块 0.3
引擎读取最多1000条已结算Binance USDⓈ-M Funding历史并判断观察状态。跨频率采用与上一结算间隔有关的**线性8小时等效折算**，仅供跨期比较，不代表复利或真实费用收益。
`NEGATIVE_WATCH`=首次或不足3期负值；`PERSISTENT_NEGATIVE_WATCH`=至少3期连续负值；`DEEP_NEGATIVE_WATCH`=同时处于可用历史最低10%分位（需至少60个有效样本）。
此模块无自动买入指令；当历史数据不足/过期时输出UNKNOWN/STALE。结算间隔若频繁缩短，1000条数据可能覆盖不到90天，报告必须列起始日期与样本数量。

## Eric D3基础数学核心（独立移植，尚未逐K验证）
`engine/eric_core.py` 按用户Eric v1.9.10原始公式使用 `(low+close)/2 → Wilder RSI(20) → Stoch RSI(26) → SMA(4) → SMA(3)`，并按连续有效Stoch值数量至少6根判定D3输出就绪；仅作为标准已收盘K线数学参考数值。
自动BTC报告的 `eric_core_math` 会显示 `CORE_FORMULA_PORT_UNVERIFIED` 状态和D3读数，但不输出原Eric反转、背离、Episode、MTF状态。因只取260根历史K线，RMA种子可能与TradingView完整历史图表不同。完整验证见 [TRADINGVIEW_PARITY.md](TRADINGVIEW_PARITY.md)。

## 2026-11-21 默认 Pure Five-Step v0.4
- 分析引擎按 **Step1收盘趋势→Step2历史前高低→Step3 SH/BMS/RTO→Step4 Volume/Delta/OI/Funding→Step5风险/WAIT** 输出，详见 [纯五步规范](PURE_FIVE_STEP.md)。
- `engine/five_step.py` 只用已收盘1H K线，锁定SH、BMS参考位、确认截止、失效优先与RTO回踩状态。属于价格行为代理，不等价于Pine V1.1，也没有自动下单功能。
- 默认配置 `swing.research_overlay_enabled=false`：不计算、不展示Eric。改为true时，只增加未验证的D3数学核心**独立研究附录**；`swing.entry_gate_enabled=true`时CLI拒绝运行，不允许Eric决定交易。
- 原五年历史回测参数BMS=5根、最低量比1.0；新日常分析BMS=4根、量比0.8，**不能共用历史业绩**。即使出现历史`CONFIRMED_RTO`也不能等于当前可直接交易。默认仍为WAIT。
