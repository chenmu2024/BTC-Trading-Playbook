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
