# BTC Trading Playbook — AI分析代理执行规范

当用户要求“读取仓库，按现在行情给出交易思路”时：
1. **每次重新读取**仓库最新的 README、MASTER_STRATEGY、ANALYSIS_SOP、RISK_MANAGEMENT、RESEARCH_STATUS、config/strategy.yaml。注明准确commit SHA，不要仅凭聊天记忆执行。
2. 获取并引用可核实的行情数据（prefer Binance connector），统一时间戳UTC，明确现货/永续与是否收盘；不允许编造实时价格、OI、CVD或资金费率。
3. **不能声称已在聊天中运行TradingView Pine**。如果没有指标报警/截图或已验证一致性引擎，则Eric v1.9.10和强支撑压力v3.3值保持UNKNOWN。可以列标准K线计算代理指标，但要标“非原脚本值”。
4. 流程：日线/4H结构→强区/代理位置→Eric状态可用性→SH/BMS/RTO→**负资金费率专项（已结算、连续性、极端分位与时效）**→订单流支持/反证→双向条件计划→风险否决。负费率不能代替价格结构确认。
5. 输出时分别标事实、解释、条件性假设；每个方向都写触发和失效标准，并允许WAIT。OI不能单独认定新增空头，正费率不能直接认定顶。
6. 不自动执行交易、下单、改交易所账户、使用API密钥；只有用户明确授权且具备匹配工具时才讨论执行。
7. 报告以 REPORT_TEMPLATE.md 为纲，优先记录数据缺口，不以猜测补齐。需要把报告写回仓库时遵循用户指示及公共隐私规则。
8. 策略版本更改需要CHANGELOG记录、保留旧代码及回测；不得在没有新证据时承诺盈利。

本仓库所有信号目前均为研究用途。

9. 当解释Funding作为潜在底部因素时，必须阅读 [research/RESULTS_2022_2026.md](research/RESULTS_2022_2026.md)，同时区分“结算后固定持有事件研究”和“确认结构后交易”的不同统计母体；不能宣称负Funding已证实有稳定的多头利润优势。
10. 新增 `research/causal_structure_backtest.py` 是独立PROXY，不是用户的Strong MTF SR v3.3 / Eric / Pine V1.1联合策略。跨年度样本量为0或4时必须明确“证据不足”，严禁计算貌似可靠的胜率预测。

11. 每次分析可计算 `engine/eric_core.py` 中的D3数学核心，并在报告中标注 `CORE_FORMULA_PORT_UNVERIFIED`；禁止将D3数值直接解释为Eric v1.9.10“反转超卖”“严格底背离”或MTF共振已触发。
12. 三份Pine已建立[数据导出侧本](pine/validation)及[校验说明](docs/TRADINGVIEW_PARITY.md)。如果未实际取得TradingView图表CSV或未完成实机编译，必须保持原始指标逐K等价状态NOT_TESTED；CI单元测试不能替代平台验证。
13. 若取得CSV，先运行 `research/audit_tradingview_csv.py` 检查时间、OHLC和来源周期，再比较Eric基础D3，后续才考虑原始状态机与Python逐K匹配。
