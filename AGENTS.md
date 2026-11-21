# BTC Trading Playbook — AI分析代理执行规范

当用户要求“读取仓库，按现在行情给出交易思路”时：
1. **每次重新读取**仓库最新的 README、MASTER_STRATEGY、ANALYSIS_SOP、RISK_MANAGEMENT、RESEARCH_STATUS、config/strategy.yaml。注明准确commit SHA，不要仅凭聊天记忆执行。
2. 获取并引用可核实的行情数据（prefer Binance connector），统一时间戳UTC，明确现货/永续与是否收盘；不允许编造实时价格、OI、CVD或资金费率。
3. **不能声称已在聊天中运行TradingView Pine**。如果没有指标报警/截图或已验证一致性引擎，则Eric v1.9.10和强支撑压力v3.3值保持UNKNOWN。可以列标准K线计算代理指标，但要标“非原脚本值”。
4. **纯五步默认流程**：已收盘日线/4H结构→已知前高低/流动性→SH/BMS/RTO价格状态/时限→Volume/Delta/OI/已结算Funding反证→风险和WAIT。**不要将Eric放进默认交易流程**；负费率不能代替价格确认。
5. 输出时分别标事实、解释、条件性假设；每个方向都写触发和失效标准，并允许WAIT。OI不能单独认定新增空头，正费率不能直接认定顶。
6. 不自动执行交易、下单、改交易所账户、使用API密钥；只有用户明确授权且具备匹配工具时才讨论执行。
7. 报告以 REPORT_TEMPLATE.md 为纲，优先记录数据缺口，不以猜测补齐。需要把报告写回仓库时遵循用户指示及公共隐私规则。
8. 策略版本更改需要CHANGELOG记录、保留旧代码及回测；不得在没有新证据时承诺盈利。

本仓库所有信号目前均为研究用途。

9. 当解释Funding作为潜在底部因素时，必须阅读 [research/RESULTS_2022_2026.md](research/RESULTS_2022_2026.md)，同时区分“结算后固定持有事件研究”和“确认结构后交易”的不同统计母体；不能宣称负Funding已证实有稳定的多头利润优势。
10. 新增 `research/causal_structure_backtest.py` 是独立PROXY，不是用户的Strong MTF SR v3.3 / Eric / Pine V1.1联合策略。跨年度样本量为0或4时必须明确“证据不足”，严禁计算貌似可靠的胜率预测。

11. 默认分析**不计算、不展示Eric**。用户明确要求比较，或启用研究附录配置时，才计算`engine/eric_core.py` D3数学核心，标记`CORE_FORMULA_PORT_UNVERIFIED`并置于**独立研究附录**；不改变五步主决策，不能冒充原Eric反转/背离。
12. 三份Pine已建立[数据导出侧本](pine/validation)及[校验说明](docs/TRADINGVIEW_PARITY.md)。如果未实际取得TradingView图表CSV或未完成实机编译，必须保持原始指标逐K等价状态NOT_TESTED；CI单元测试不能替代平台验证。
13. 若取得CSV，先运行 `research/audit_tradingview_csv.py` 检查时间、OHLC和来源周期，再比较Eric基础D3，后续才考虑原始状态机与Python逐K匹配。

14. 用户要求“按五步方法直接回测历史”时优先检查 `research/five_step_observable_backtest.py` 和 `research/RESULTS_FIVE_STEP_2026-11-21.md`，说明已完成历史OHLCV/Funding可观测子集执行回测。不要误说无法回测，也**不要**把该Python模型冒充包含完整原v3.3、Eric、真实CVD与OI的等价回测。
15. 负Funding并非自动买入；2025—2026 B_RTO_FUND模型只实现+0.0910%模拟权益收益（9笔交易），早段仍亏损。带方向拆分的数据更重要：后段9笔仅2笔多头。任何结论必须标明成本、样本量、2022年EMA预热、历史后段非真正未知样本外。

16. **重要：五步历史回测V0.2替代旧版中“连续3期Funding”成绩**。原代码曾误用下一期未结算数据；目前仅允许`fi-2,fi-1,fi`。旧版`B_RTO_STREAK3`的2022—2024“4笔-0.6192%”不得复述为有效结果；现为5笔-0.8857%。
17. 优先引用[独立方向回测研究V0.2](research/RESULTS_LONG_FUNDING_FOCUS_V0_2.md)，并明确2026年A顺势LONG+RTO候选为0，历史盈利主要来自2024/2025，2023有亏损；B逆势LONG+负Funding仅2026两笔样本，连续3期硬过滤0笔。
18. `research/five_step_observable_backtest.py`冻结研究参数：BMS确认5根、成交量1.0×，不同于`config/strategy.yaml`日常分析4根、0.8×；不能混用或以实验业绩替代分析配置表现。独立多头账户与混合账户方向子集是两种不同统计母体。

19. **当前最高优先级（2026-11-21）**：默认响应为`PURE_FIVE_STEP`，不使用Eric入场/否决。只有显式研究需求才以独立附录显示Eric D3，不得影响方向、SH/BMS/RTO状态、风险或WAIT。
20. 新`engine/five_step.py`为1H价格行为**代理**状态机，含4根BMS、5根RTO及各阶段失效/超时；并非与Pine v1.1逐K一致、不能称`CONFIRMED_RTO`为已证实入场信号。
21. 日常配置4根/0.8倍量；五年冻结历史回测5根/1.0倍量，**两者不能共用旧绩效数字**。未经新配置完整回测，不得声称优化产生利润提升。
