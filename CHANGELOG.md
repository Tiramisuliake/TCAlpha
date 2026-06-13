# Changelog

## [0.8.8] — 2026-06-12

> 策略库扩充：12 → 15 类，补齐三个空白范式 —— 顺势指标（CCI）、量价加权（VWAP 偏离）、仓位管理（金字塔加仓）。前端零改动（参数表单按 params_schema 动态渲染）。

### Added — 策略库扩充（CCI / VWAP / 金字塔加仓）
- `strategies/examples/cci.py`：**CCI 顺势指标**（只做多）—— 从超卖区（< -100）上穿 -100 抄底开多、从超买区（> +100）下穿 +100 高位平多；与 RSI/KDJ 同属超买超卖范式，但 CCI 无界、对趋势加速更敏感
- `strategies/examples/vwap_bias.py`：**VWAP 偏离回归**（只做多）—— 滚动 N 日成交量加权均价（典型价 × 量），收盘低于 VWAP×(1-bias) 超跌买入、回到 VWAP 上方卖出；策略库唯一的「成交量加权价格」范式，放量日权重更高，贴近真实持仓成本
- `strategies/examples/pyramid_turtle.py`：**金字塔加仓海龟**（只做多）—— 突破前 N 日高开首仓，每涨 add_step×ATR 加一仓至 max_units 上限（每层间距按波动率自适应），跌破前 M 日低一次性全平；策略库唯一的「分批建仓 / 仓位管理」范式，其余策略均一次性满仓
- `core/backtest_engine.py`：3 类注册进 `STRATEGY_CLASSES`（共 15 类），回测 / 扫参 / 对比 / 策略管理全链路即刻可用
- 测试：注册检查扩到 15 类 + CCI 穿越开平 / VWAP 超跌买入回归卖出 / 金字塔加仓封顶 max_units 且跌破全平归零（+9 用例，共 168 passed）

## [0.8.7] — 2026-06-12

> 三块：**回测周期参数**（日线 → 1m~60m 分钟级，年化口径随周期）；**Walk-Forward 防过拟合**（扫参训练/验证切分 + 样本外衰减率）；**回测报告导出**（零依赖自包含 HTML）。另：分钟线下载链路核查——provider / Celery / beat 早已就绪（v0.8.0 DataProvider 时期落地），本轮只补引擎侧。

### Added — 回测周期参数（分钟级回测）
- `core/backtest_engine.py`：`_load_bars(period)` 按周期选 ArcticDB `bar_{period}` 库（1d/60m/30m/15m/5m/1m，与数据下载任务命名一致）；新增 `_ANNUAL_BARS` 年化因子表——夏普 / Sortino / 波动率 / 滚动夏普按周期年化（5 分钟线 √(252×48)），日线口径不变
- `BacktestJob.period` / `ParamSweepJob.period` 列 + 迁移 `63655e556d5b`（server_default '1d' 兼容旧行）；schema / service / task 全链路透传
- 前端：单次回测与参数寻优表单新增 K 线周期下拉（日线默认）

### Added — Walk-Forward 防过拟合（扫参样本外验证）
- `run_sweep` 新增 `oos_split`（0.05~0.6 验证集占比）：按时间把 K 线切成训练段（寻优排序用）+ 验证段（样本外复测）；每行带 `oos_metrics` 与 `decay`（1 - 样本外/训练，越大越过拟合）；**排序始终按训练段**——用 OOS 排序等于把验证集当训练集用
- `ParamSweepJob.oos_split` 列（同迁移）；前端寻优表单「验证集 %」输入，结果表条件渲染样本外目标值 / 衰减列（>50% 标红），最优卡训练 vs 样本外对照 + 疑似过拟合提示
- 测试：年化因子映射 / 夏普 √48 缩放 / bar_5m 库加载与非法周期报错 / oos 切分行字段与训练段排序 / 不传 oos 向后兼容（+6 用例）

### Added — 回测报告导出（自包含 HTML）
- `services/report.py`：零外部依赖（无 Jinja2 / 无 CDN）——f-string 模板 + **内联 SVG** 资金曲线（含基准虚线）与回撤面积 + 月度收益上色表 + 成交明细（前 200 笔）+ 用户内容 HTML 转义防注入；离线可看、可存档分享
- `GET /api/backtest/{id}/report`（`backtest.read` + 属主校验，仅 done 可导，attachment 下载头）
- 前端：回测结果面板「导出报告」按钮（axios blob 带鉴权下载，绕开 window.open 丢 token 问题）
- 测试：核心区块齐全 / 可选区块缺省不渲染 / XSS 转义（+3 用例，共 159 passed）

## [0.8.6] — 2026-06-11

> 四块：**实盘 Gateway 抽象**（Phase 9 起步）；**配对交易回测**（价差 z-score 统计套利，模拟做空腿）；**模拟资金账户**（撮合扣款 / 余额拒单，模拟盘第一次"花真钱"）；**Phase 8 数据权限收尾**（scope 全链路对齐）。另：复权核查通过——日 K / 分钟 K 下载均为前复权（qfq），回测数据正确性无问题。

### Added — 模拟资金账户（SimGateway 资金约束）
- `db/models/account.py`：`sim_accounts` 表（user_id 唯一 / balance / init_capital）+ 迁移 `d4845eee9740`；账户懒创建，初始资金走新配置 `SIM_INIT_CAPITAL`（默认 100 万）
- `SimGateway`：开仓单**委托时按委托价预校验**余额（不足直接 rejected）；撮合成交时**按实际价复核**——委托后价格上行导致资金不够同样拒单；开仓扣 现金+手续费、平仓入 现金-手续费-印花税
- `services/sim.place_market_order`（手工市价单）同样接入：开仓验余额扣款、平仓入账，两条下单路径资金口径一致
- 新 API：`GET /api/sim/account`（现金 / 持仓成本 / 总资产·成本口径 / 持仓明细含加权均价）+ `POST /api/sim/account/reset`（现金回初始资金，流水保留审计）
- 前端 Trade 页：资金账户卡（可用现金 / 持仓成本 / 总资产红绿着色 / 重置按钮带确认）+ 持仓表新增成本均价 / 持仓成本列；订单成交与 WS 推送联动刷新账户；修正"无资金校验"过时提示
- 测试：账户懒创建 / 开仓扣款 / 平仓入账含印花税 / 委托即拒 / 撮合时价格上行拒单（+5 用例）

### Changed — Phase 8 数据权限收尾
- 盘点结论：`effective_scope` 已覆盖 backtest / sweep / sim orders / strategy 四处；本轮补齐 **ai_alerts**（管理员 / data_scope=all 可跨用户看告警）
- **设计决定**：watchlist 自选与 notify 规则刻意保持 self-only——个人配置非业务产出，且 notify 规则含 webhook 密钥，跨用户可见有泄密风险（已写入 docstring）
- 测试：API 层接线测试（super→all / 普通 self→self 透传到 service）+ 原 effective_scope 纯函数用例（共 +2 用例，全量 151 passed）

### Added — 实盘 Gateway 抽象（Phase 9 起步）
- `core/gateway.py` 重写：原占位 Protocol → **BaseGateway ABC** —— `send_order` / `cancel_order` / `get_position` 为抽象契约；`connect` / `disconnect` / `subscribe` / `match` 为默认 no-op 可选钩子（模拟盘无会话概念、撮合由 runtime 驱动；实盘网关覆写为券商会话与推送注册，撮合在券商侧）
- `create_gateway` 工厂：按 `settings.gateway_type`（新增配置，默认 `sim`）实例化，实盘网关（QMT / xtquant 等）接入时注册新类型即可，**业务层零改动**
- `SimGateway` 继承 BaseGateway（签名本就吻合，零行为变化）；`runtime.py` 改走工厂，不再直接实例化 SimGateway
- 测试：继承关系 / 工厂默认与显式覆盖 / 未知类型报错 / match 默认 no-op（+5 用例）

### Added — 配对交易回测（统计套利，模拟做空腿）
- `core/backtest_engine.py`：新增 `run_pair(symbol_a, symbol_b, window, entry_z, exit_z)` —— 价差 = ln(A) - ln(B)，滚动 z-score；z > entry_z 空 A 多 B、z < -entry_z 多 A 空 B（多弱空强各半仓名义），|z| < exit_z 价差回归双腿平仓；收盘信号次日开盘 ± 滑点撮合。**做空为模拟语义**（融券简化：卖空收现金、负债按现价 mark-to-market、全额名义无杠杆），实盘券源 / 保证金 / 费率不建模
- `_round_trips` 泛化：按 **(symbol, direction) 分腿独立配对** —— 单标的退化为原行为，轮动多 symbol、配对多空交织均配对正确；空头腿 MAE/MFE 语义取反；回合记录新增 symbol / direction 字段
- `run()` 按 `class_name=PairTradingBacktest` 分支，A/B 标的与 z 参数存 params JSON（零迁移）；结果带 `pair_zscore` / `pair_symbols` / 窗口与阈值
- 前端：回测页新增「配对交易」Segmented —— `components/PairBacktest.tsx`（A/B 标的 + z 窗口/开平阈值 → 指标卡 + 资金曲线 + **z-score 曲线带开平仓标线** + 双腿成交明细：买入/卖空/卖出/买回四态标签）
- 测试：价差发散回归盈利（双腿四笔成交）/ 无发散零交易 / 缺标的报错 / 分腿回合独立配对（空头收益率）/ run() e2e 落库两标的两方向（+6 用例，共 144 passed）

## [0.8.5] — 2026-06-11

> 三块：策略库 10 → 12 类（趋势回踩 + 布林收口突破）；回测引擎首次支持**多标的**——动量轮动回测（零迁移，复用 BacktestJob）；扫参寻优接入绩效深化指标 + 参数地图选轴切片。

### Added — 多标的动量轮动回测
- `core/backtest_engine.py`：新增 `run_rotation(symbols, lookback, rebalance_days, ...)` —— 多标的日 K 对齐到交易日并集（收盘 ffill、开盘用收盘兜底），每 rebalance_days 个交易日按过去 lookback 日收益率排名**全仓持有最强标的**，动量全负则空仓（绝对动量过滤，熊市离场）；信号收盘算、次日开盘 ± 滑点撮合（无未来函数），买入一手取整、卖出含印花税
- `run()` 按 `class_name=RotationBacktest` 分支走轮动（不进策略注册表，不影响实时 runtime）；标的列表与轮动参数存 `params` JSON，**零迁移**；`Trade` 加 `symbol` 字段，成交落库带各自标的
- 结果追加 `rotation_symbols` / `rotation_holdings`（调仓时间线）/ `rotation_lookback` / `rotation_rebalance_days`，并继续复用基准对比、绩效深化、交易行为分析全套指标
- 前端：回测页新增「轮动回测」Segmented —— `components/RotationBacktest.tsx`（标的多选 + 动量窗口/调仓间隔/基准 → 指标卡 + 资金曲线 + 调仓时间线 + 成交明细带标的列 + 绩效/交易分析）；`EquityChart` 从回测页抽为公共组件供单标的/轮动共用
- 测试：升/跌/平三标的恒持最强 / 全负空仓 / 动量反转换仓 / 标的缺失报错 / run() e2e 落库带 symbol（+5 用例）

### Added — 扫参寻优升级（参数地图）
- `_SWEEP_METRIC_KEYS` 接入 `calmar` / `expectancy`（v0.8.3 绩效深化指标可作寻优目标）
- 前端 ParamSweep：目标下拉新增 Calmar / 单笔期望 / 最大回撤(最浅)；**>2 参数时支持选 X/Y 轴绘参数地图**，其余维度自动固定在最优组合取值上切片；结果表新增 Calmar 列
- 测试：calmar 目标排序 + 结果行带深化指标（+1 用例，共 134 passed）

### Added — 策略库扩充（趋势回踩 / 布林收口突破）
- `strategies/examples/pullback.py`：**趋势回踩**（只做多）—— 收盘站上长均线（趋势过滤）且当日最低触及短均线、收盘收回其上（回踩企稳）→ 开多；收盘跌破长均线 → 平多。与追突破相反的「趋势中低吸」范式
- `strategies/examples/boll_squeeze.py`：**布林收口突破**（只做多）—— **前一根** bar 带宽 (上轨-下轨)/中轨 ≤ squeeze_th 判定挤压（突破当根带宽已被拉开，须看突破前），挤压中收盘突破上轨 → 开多；跌破中轨 → 平多。与 BollStrategy（均值回归）互为同指标的相反范式
- `core/backtest_engine.py`：2 类注册进 `STRATEGY_CLASSES`（共 12 类）
- 测试：回踩「上行带回调→暴跌破线」开平 / 下跌趋势闸门不开仓 + 收口突破确定性路径（开平各一次）/ 大噪声不挤压闸门反例（+8 用例，共 128 passed）

## [0.8.4] — 2026-06-10

> 策略库扩充：5 → 10 类，新增 KDJ（超买超卖）、网格交易（震荡市）、DMI/ADX（趋势强度过滤）、ATR 吊灯止损（跟踪止损范式）、双均线+量能过滤（放量确认），补齐震荡 / 网格 / 止损三个空白范式。前端零改动（参数表单按 params_schema 动态渲染）。

### Added — 策略库扩充（KDJ / 网格 / DMI / ATR 止损 / 量能均线）
- `strategies/examples/kdj.py`：**KDJ 随机指标**（只做多）—— A 股口径手工递推（RSV + 1/3 平滑，talib STOCH 口径不同故自算），K/D 存 State 持久化重启续算不漂移；低位金叉开多、高位死叉平多
- `strategies/examples/grid.py`：**网格交易**（震荡市）—— 首根 bar 锚定基准价，每跌 grid_pct 一格买 100 股、涨回一格卖 100 股，max_grids 限仓；当前格数由 `pos // 100` 推导，涨跌停 / 停牌未成交时不与真实仓位漂移
- `strategies/examples/dmi.py`：**DMI/ADX 趋势过滤**（只做多）—— +DI > -DI 且 ADX ≥ 阈值开多、-DI 反超平多；条件取「状态」而非「交叉沿」（交叉瞬间 ADX 往往尚未达标），ADX 闸门过滤震荡市假信号
- `strategies/examples/atr_stop.py`：**ATR 吊灯止损**（只做多）—— 突破前 N 日高入场；持仓期止损线 = 持仓最高价 - atr_mult×ATR **单调上移**锁浮盈，收盘跌破即离场；引入「跟踪止损」出场范式（现有策略均为信号出场）
- `strategies/examples/ma_vol.py`：**双均线 + 量能过滤**（只做多）—— 金叉且当根量 ≥ vol_ratio×前 N 日均量（均量不含当根，放量不抬自家基准）才开多，无量金叉提示"疑似假突破"观望；死叉平多不设量能门槛
- `core/backtest_engine.py`：5 类注册进 `STRATEGY_CLASSES`，回测 / 扫参 / 对比 / 策略管理全链路即刻可用
- 测试：注册检查扩到 10 类 + KDJ 金叉死叉触发 / K-D 值域 + 网格确定性买卖路径 / max_grids 限仓 + DMI 趋势开平 + ATR 止损触发 / 止损线单调性 + 量能过滤正反用例（+19 用例，共 120 passed）

## [0.8.3] — 2026-06-10

> 交易明细深化：成交配对为「回合」（进场→出场），给出持仓周期 / 单笔收益率 / MAE/MFE / 单笔期望，前端新增盈亏分布直方图 + 持仓周期×收益散点。延续零迁移（结果存 JSON 列）。

### Added — 交易级分析（回合配对 + MAE/MFE + 期望）
- `core/backtest_engine.py`：新增 `_round_trips(trades, bars)` 把时序 open/close 成交配对为回合（分批平仓拆多回合），均价跟踪与 `_settle` 一致；每回合含 entry/exit 日期、持仓天数、单笔收益率、**MAE/MFE**（持仓期间相对入场均价的最大不利/有利偏移，需 bars 高低价）
- `_metrics` 加 `bars` 可选参数，追加 `round_trips` / `avg_holding_days` / `win_holding_days` / `lose_holding_days` / `avg_mae` / `avg_mfe` / `expectancy`（单笔期望 = 胜率×平均盈利 + 败率×平均亏损）；`_simulate` 透传 bars
- 前端 `components/TradeAnalysis.tsx`：单笔期望 / 平均持仓（盈亏分拆）/ MAE / MFE 指标卡 + **单笔收益率分布直方图**（红盈绿亏）+ **持仓周期×收益散点**（盈亏双系列）；接入回测结果面板
- `types`：新增 `RoundTrip` 接口，`BacktestResult` 追加交易级可选字段（向后兼容，旧回测不渲染）
- 测试：单回合配对 / 分批平仓拆回合 / MAE-MFE 计算 / 孤儿平仓跳过 / expectancy 公式 / 无交易向后兼容（+6 用例，共 35 passed）

## [0.8.2] — 2026-06-10

> 回测绩效深化：风险标量（Calmar / 年化波动率 / 最大回撤区间 / 连胜连亏）+ 月度收益热力图 + 滚动夏普/Beta + 相对强弱曲线。延续基准对比，零迁移（结果存 JSON 列）。

### Added — 回测绩效与基准分析深化
- `core/backtest_engine.py`：新增 `_drawdown_interval`（峰/谷/修复/持续天数）、`_streaks`（最长连胜/连亏）、`_monthly_returns`、`_rolling_sharpe`；`_metrics` 追加 Calmar / 年化波动率 / 平均盈亏 / 月度收益 / 滚动夏普
- `_benchmark_metrics`：追加滚动 Beta（60 日窗口）+ 相对强弱（策略归一 / 基准归一比值）
- 前端 `components/BacktestAnalysis.tsx`：风险指标卡 + 月度收益热力图（年×月，红涨绿跌）+ 滚动夏普/Beta 双轴 + 相对强弱曲线；接入回测结果面板
- `types`：`BacktestResult` 追加绩效深化可选字段（向后兼容）
- 测试：回撤区间 / 连胜连亏 / 月度 / 滚动夏普 / Calmar / 滚动 Beta / 相对强弱（+10 用例，共 29 passed）

## [0.8.1] — 2026-06-10

> 回测基准对比：策略收益自动 vs 指数基准，给出 Alpha / Beta / 超额收益 / 信息比率；基准可配置（沪深300 / 中证500 / 创业板指 / 上证50）。

### Added — 回测基准对比（Alpha / Beta / 超额收益 vs 指数基准）
- `data/provider.py`：新增 `fetch_index_daily()`（AKShare `index_zh_a_hist`）拉指数日 K，写进 `DataProvider` 契约
- `core/backtest_engine.py`：回测自动对比指数基准 —— 新增 **Alpha / Beta / 超额收益 / 信息比率 / 基准收益** 指标（`_benchmark_metrics`）；基准指数日 K 经 `_load_index_close` lazy 下载并缓存到 ArcticDB `index_1d` 库；按自然日跨时区对齐，任何失败都跳过基准、绝不拖垮主回测
- **基准可配置**：`_BENCHMARK_INDICES` 支持 沪深300 / 中证500 / 创业板指 / 上证50，基准名贯穿 `_metrics` / `_simulate` / `run`；`backtest_jobs` 新增 `benchmark` 列（默认 `000300`）+ 迁移 `b2cf008fad46`，`schemas` / `services` 透传选择
- 前端回测页：单次回测表单新增**对比基准下拉**（4 指数）；资金曲线叠加基准线（灰色虚线），指标区在有基准时追加 超额收益 / Alpha / Beta 三张卡片
- 测试：基准指标计算单测（跨时区对齐 / 平基准 beta=0 / 正相关 beta>0 / 向后兼容无基准字段）

## [0.8.0] — 2026-06-08

> 量化能力大扩充：策略库扩到 5 类，回测引擎进化（网格扫参 + 多策略对比 + A 股撮合约束 + AI 归因），新增**选股器**与**盯盘驾驶舱**两大业务模块，统一数据获取层 **DataProvider**，并补齐 GitHub Actions CI。

### Added — 策略库扩充
- `strategies/examples/`：新增 **海龟唐奇安通道突破**（趋势跟踪）、**RSI**、**MACD**、**布林带** 四套策略，连同原有 MA 交叉共 5 类，覆盖均线 / 动量 / 趋势 / 波动率
- **策略参数表单动态化**：前端按后端 `params_schema` 自动渲染参数输入，新增策略无需改前端

### Added — 回测引擎进化
- **网格扫参（Param Sweep）**：新增 `ParamSweepJob` 表 + 迁移；回测引擎提取 `_simulate` 复用、新增 `run_sweep` 核心；后端 API（schema / service / task / 路由）+ 前端扫参 UI + 结果热力图
- **多策略对比回测**：同标的、同区间多策略 PK
- **A 股撮合约束**：回测撮合加入涨跌停 / 停牌限制，更贴近真实成交
- **AI 回测归因**：回测结果一键 LLM 流式解读（走 SSE）

### Added — 选股器（Screener）
- 后端：screener 服务 + 全市场快照刷新 task + `/api/screener/run` API
- **多因子打分**：动量 / 估值 / 换手率归一化加权打分排序
- 前端：筛选表单 + 结果表页面（`pages/Screener`）
- **选股闭环**：结果行一键「加自选 / 去回测 / 建策略」

### Added — 盯盘驾驶舱 + 自选股
- **盯盘驾驶舱**页（`pages/Monitor`）：自选股实时报价 + AI 告警聚合

### Added — 工程化（CI）
- **GitHub Actions CI**：ruff + pytest（带 PG / Redis service 容器）+ 前端 tsc 类型检查
- 前端 CI 工具链对齐本地：Node 20→22、pnpm 9→11、`pnpm-workspace.yaml` 修正、install 加 `--ignore-scripts`

### Changed — 数据层收口
- 统一数据获取层 **DataProvider**：收口所有 AKShare 调用，单点限流 / 缓存 / 重试
- **数据同步健壮性**：新增 `SyncLog` 水位表 + 增量下载 + 同步失败飞书告警
- 清理 DataProvider 收口后残留的死常量

### Changed — 权限（Phase 8 起步）
- `data_scope` 数据权限**真正生效**：`all` scope 可跨用户可见 —— Phase 8 数据权限落地第一步

### Changed — 前端体验
- 前端健壮性兜底：`ErrorBoundary` + 404 页 + 路由级权限守卫
- 前端设计落地与体验优化；策略监控台细节打磨（信号占位 / 参数格式化 / 持仓卡片 / 运行脉冲）；模拟交易禁用卖空

### Fixed
- `screener` 股票代码前导 0 丢失
- `app/data` 被 `.gitignore` 误伤导致 DataProvider 文件漏提交

### Tests
- 补充网格扫参 / 涨跌停 / 策略 / 选股器单测

## [0.7.6] — 2026-06-02

### Added — Phase 7 v0.7.6：前端按钮权限收紧 + 热门股 seed

把 RBAC 闭环延伸到 UI 按钮层：viewer 视角下能看到自己点不动的按钮，但 disabled + Tooltip 提示缺什么权限，体验比"点了再被 403"更友好。

前端
- `components/PermButton.tsx`：包装 AntD `Button`，按 `useAuthStore.has(perm)` 决定 disabled + Tooltip；`hideOnDenied` 用于纯破坏性操作（删除）；`perm` 支持单字符串或字符串数组（全部都需要）；super 用户自动绕过
- `pages/Strategy`：新建/编辑 → `strategy.write`；删除 → `strategy.delete`（hideOnDenied）；启动/停止 → `strategy.run`
- `pages/Backtest`：开始回测 → `backtest.run`
- `pages/Notify`：新建/编辑/测试发送/保存 → `notify.rule.write`；删除 → `notify.rule.write`（hideOnDenied）
- `pages/Trade`：市价单提交 → `sim.order.place`；撤单 → `sim.order.cancel`
- `pages/Data`：下载 K 线 / 刷新股票列表 → `data.download`
- `pages/Chart`：下载 K 线 / 立即下载 → `data.download`；AI 解读 / 重新分析 → `ai.chat`

工具
- `backend/scripts/seed_symbols.py`：离线 seed 50 只热门 A 股到 PG `symbols` 表（沪深主板 / 创业板 / 科创板代表，覆盖银行 / 白酒 / 新能源 / 半导体 / 医药等），idempotent；不依赖 AKShare / Celery，dev 早期一键让 K 线 / 策略 / 回测 / 模拟交易页面立刻能搜到候选

### Notes — UX 设计

- **可发现性优先**：缺权限的按钮**默认 disabled + Tooltip 提示**，而不是隐藏。让 viewer 知道"这个功能存在但需要 xxx 权限"，鼓励申请权限
- **破坏性操作隐藏**：删除按钮用 `hideOnDenied`，避免误导
- **后端闸门是真正的安全边界**：前端 disabled 只是 UX；即使前端 bypass，后端 `require_permission` 仍会 403。前端只负责"别让 viewer 浪费一次往返"

## [0.7.5] — 2026-06-02

### Fixed — 时区统一（Asia/Shanghai）
- 全栈日期 / 时段计算与时间戳改用 `now_cn()`：notify `quiet_hours` 静音判断、AKShare 下载日期窗口（`data_tasks` / `market`）、策略运行时循环窗口、事件总线与实时报价时间戳 —— 修复 UTC/naive 导致的跨日偏差与飞书卡片显示晚 8h

### Changed — 重构
- `notify_dispatcher._load_active_rules` 改用 `RuleView` dataclass 快照，不再重建 `NotifyRule` ORM 实体（消除带主键游离实体被误写的隐患）

## [0.7.4] — 2026-06-01

### Fixed — 代码审查修复（安全 / 正确性 / 性能 / 健壮性）

回测与策略引擎
- `strategies/base.py`：实例化时为每个实例深拷贝 params/state/vars，修复类属性单例导致的跨回测 / 多策略状态污染
- `core/backtest_engine.py`：`run()` 在 session 内提取 job 字段为局部变量，修复 commit 后跨 session 访问 detached ORM 对象（`DetachedInstanceError`）
- `db/postgres.py`：`SyncSessionLocal` 加 `expire_on_commit=False`，与异步 session 行为一致
- `core/runtime.py`：策略主循环窗口滚动到当天 + 从最后一根 bar 增量读取，修复跨交易日拉不到新 K + 每轮重读整年

鉴权 / 安全
- `deps.py`：`get_current_user_id` 缺失 / 失效 token 一律 401，移除 fallback 到 `default_user_id` 的死代码（fail-closed）
- `services/auth.py`：登录失败分支也跑一次 bcrypt 校验，抹平响应时延差异，防用户名枚举
- `api/ws.py`：WebSocket 转发改三协程竞争（转发 / 断开探测 / 心跳），修复客户端静默断开导致的 Redis 订阅与 task 泄漏

性能
- `services/market.py`：`get_symbols` 用 `COUNT(*)` 子查询替代全量拉 id 计数
- `core/sim_gateway.py`：`get_position` 改 DB 端 `group_by` 聚合，避免拉全部成交订单到内存

测试
- `tests/test_backtest_engine.py`：新增 `run()` 端到端 + 策略状态隔离集成测试
- `tests/test_rbac.py`：`as_user` fixture 同步 override `get_current_user_id`

### Changed — 工程化（前端工具链 + 全栈整理）
- 前端接入 ESLint 扁平配置（`frontend/eslint.config.js` + `typescript-eslint` / `eslint-plugin-react-hooks` / `eslint-plugin-react-refresh` / `globals`）
- 新增 `frontend/src/api/streamClient.ts`：带鉴权刷新的 fetch / SSE 客户端
- 后端多模块整理：`timezone.utc` → `UTC`、import 规整、类型标注完善等
- `docs/project-bugfix-plan.md`：本轮问题修复计划记录

## [0.7.3] — 2026-05-30

### Fixed — DX 启动稳定性 + 登录跳转

启动器（动态端口）
- `backend/run.py`：扫 8001..8050 找真正可 `socket.bind()` 的端口（绕开 Windows tcpip.sys 幽灵 LISTENING），写入 `frontend/.dev-port`
- `frontend/vite.config.ts`：启动读 `.dev-port` 决定代理目标，前后端永远自动对齐；`BACKEND_PORT` 环境变量可强锁
- `scripts/start_backend.ps1` / `start-backend.bat` / `Makefile`：全部改走 `python run.py`，移除原先靠 taskkill 杀 socket 的不可靠路径
- `.run/Backend.run.xml`：PyCharm Run 配置走 PowerShell + `uv --directory backend run python run.py` + 注入 `NO_PROXY`
- `frontend/.gitignore`：忽略动态端口文件 `.dev-port`
- `backend/README.md`：刷新启动 4 种方式 + PyCharm 一次性配置说明

测试体系（B 阶段稳定性补强）
- `backend/app/utils/rate_limit.py`：Redis 固定窗口共享限流（跨 worker）
- `backend/tests/conftest.py`：新增 `fake_arctic` / `sample_bars_df` / `sample_bars_arctic` / `sync_db` / `make_bar` fixtures
- `backend/tests/test_rate_limit.py` / `test_backtest_engine.py` / `test_sim_gateway.py`：核心 core 模块单测
- `backend/scripts/check_pubsub.py`：多 worker Redis pub/sub 广播验证脚本

前端登录流程
- `store/useAuthStore.ts::bootstrap`：已持有 accessToken 时跳过 refresh，避免登录后被 `RequireAuth` 弹回 `/login`（v0.7.2 残留的回流 bug）

## [0.7.2] — 2026-05-30

### Added — Phase 7 v0.7.2：用户 / 角色管理 UI

让超管不再需要 SQL，直接在 UI 上增删用户、配角色、分权限。

后端
- `schemas/system.py`：UserListItem / UserCreate / UserUpdate / UserRolesAssign / PasswordReset / RoleOut / RoleDetailOut / RoleCreate / RoleUpdate / RolePermissionAssign / PermissionOut
- `services/system.py`：用户 CRUD（list/get/create/update/delete/set_roles/reset_password）+ 角色 CRUD（list/get/create/update/delete/set_permissions）+ 权限只读列表
  - 防自残：admin 不能删自己 / 停用自己 / 把自己从 admin 角色摘掉
  - 内置：admin 角色不允许删除
- `api/system.py`：8 个端点，全部挂 `system.user.read/write` 或 `system.role.read/write` 闸门
- `main.py`：挂载到 `/api/system`
- `tests/test_system_api.py`：12 用例覆盖 401 / viewer 403 / admin 200 / 防自残 400

前端
- `types/index.ts`：补 RoleOut / RoleDetailOut / UserListItem / UserCreate / UserUpdate / PermissionOut
- `api/system.ts`：11 个函数封装
- `pages/System/Users/index.tsx`：用户表 + 新建/编辑/角色多选/重置密码/删除（不能删自己）；React Query useQuery + useMutation；删除 / 停用自己按钮禁用
- `pages/System/Roles/index.tsx`：角色表 + 新建/编辑/删除（admin 禁删）+ **按 category 折叠分组的权限多选**（含全选/清空/三态 Checkbox）
- `App.tsx`：侧栏菜单按 `useAuthStore.has(perm)` 过滤；新增「用户管理」「角色管理」入口；super 全可见
- `store/useWorkspaceStore.ts`：加 `system-users` / `system-roles` 路由项
- `components/WorkspaceTabs`：补图标映射

### Added — DX 启动体验改善（hotfix from v0.7.1 cycle）

后端启动脚本
- `scripts/start_backend.ps1`：清残留 + 启 uvicorn + 后台 health 探活打 ✅ banner
  - UTF-8 with BOM + chcp 65001：PS 5.1 中文不乱码
  - `taskkill /F /T` 多轮清理：根治 uvicorn --reload 父子进程僵尸
  - 注入 `NO_PROXY=localhost,127.0.0.1`：避开 Clash/V2Ray 劫持本地请求
  - watcher 子进程显式 `DefaultWebProxy=$null`，绕代理探活
  - 默认端口 8001（避开 8000 在 Windows 上常见的 TCP socket 泄漏；`-Port 8000` 可覆盖）
- 根目录 `start-backend.bat` / `start-frontend.bat`：纯 ASCII 注释（cmd GBK 解码不乱码），双击即启
- `.run/Backend.run.xml` / `Frontend.run.xml` / `Celery Worker.run.xml` / `Celery Beat.run.xml`：PyCharm Run 配置，顶栏 ▶ 直接跑
- `Makefile`：加 `back-safe` target；默认端口同步 8001

前端登录反馈修复
- `utils/feedback.ts`：全局 feedback holder（message + notification）
- `components/FeedbackBridge.tsx`：`App.useApp()` 注入 holder
- `main.tsx`：`<AntApp>` 包裹，根治 AntD v5 静态 `message.error()` 在 React 19 严格模式下被静默吞掉
- `api/client.ts`：用 `feedback` 替代 static `message`
- `pages/Login/index.tsx`：按 401 / 422 / 5xx / `ERR_NETWORK` / `ECONNABORTED` 给不同的错误反馈
- `vite.config.ts`：代理目标 `localhost:8000` → `127.0.0.1:8001`，避免 DNS / 代理双重干扰

文档
- `backend/README.md` 重写：一键启动 4 种方式 + 首次准备 + JWT 说明 + 常见坑速查（端口僵尸 / 代理劫持 / lifespan 卡）

## [0.7.1] — 2026-05-27

### Added — Phase 7 RBAC 闸门生效

把 v0.7.0 种下的 18 个权限点真正挂到业务路由上，让 trader / viewer 在 API 层就受限。

后端路由
- `api/strategy.py`：list/classes → `strategy.read`；POST/PUT → `strategy.write`；DELETE → `strategy.delete`；start/stop → `strategy.run`
- `api/backtest.py`：list/get/trades → `backtest.read`；submit → `backtest.run`
- `api/sim.py`：orders / position → `sim.order.read`
- `api/data.py`：download → `data.download`
- `api/market.py`：symbols / kline → `data.read`；refresh / download → `data.download`
- `api/notify.py`：rules/logs/event-types → `notify.rule.read`；POST/PUT/DELETE/test → `notify.rule.write`
- `api/watchlist.py` + `api/ai_alerts.py`：全部 `ai.watch`
- `api/ai.py::chat` + `api/ai_chart.py::analyze`：`ai.chat`
- `/api/auth/*` / `/health` / `/` 不挂闸门（登录入口 + 健康检查）

权限语义沿用 v0.7.0 种子：
- admin：18/18（super=true 直接绕过，不需要 perm 列表）
- trader：14/18 操作类（strategy / sim / backtest / data / ai / notify 各自读+写+运行）
- viewer：6/18 只读（strategy.read / sim.order.read / backtest.read / data.read / ai.chat / notify.rule.read）

测试
- 新增 `tests/test_rbac.py`：12 个用例覆盖
  - 无 token → 401（require_permission 直接拒）
  - admin / super → 任意端点 200
  - viewer 调写端点（notify/strategy delete/backtest submit/data download）→ 403，detail 含缺失的权限码
  - trader 调写端点 → 闸门通过（!= 403）
- 用 `app.dependency_overrides[get_current_user] = ...` 注入 AuthUser，避免依赖真 JWT 签发；用 `init_engine()` autouse fixture 让 TestClient 也能拿到 async session

### Notes — v0.7.1 行为变化

- **无 JWT 访问业务接口直接 401**（v0.7.0b 已硬切，v0.7.1 进一步坐实）；`deps.get_current_user_id` 的 fallback 仍保留兼容期，但 `require_permission` 不再走 fallback
- `/api/auth/login` 仍不需要 token；`/health` / `/` 仍开放
- `BasicAuthMiddleware` 默认未挂载（v0.6.0 起 `AUTH_ENABLED=false`）；如启用，会与 JWT 闸门叠加（两层都过才行），建议生产关 Basic Auth 单走 JWT

## [0.7.0] — 2026-05-27

### Added — Phase 7 RBAC 后端基础（v0.7.0a，后端独立交付）

参考 fastapi-vue-admin，落地"角色 / 权限 / 数据权限 + JWT"四件套的后端部分；
前端 JWT 接入与 Basic Auth 平滑下线放到 v0.7.0b 单独验证。

数据库：
- 迁移 `7aaf2f5c947e_add_rbac_roles_permissions_and_user_fields`
  - 4 张新表：`roles` / `permissions` / `role_permissions` / `user_roles`，全部加唯一约束 + 索引 + `ON DELETE CASCADE`
  - `users` 新增 `display_name` / `is_super` / `last_login_at` 三列（`server_default` 兼容 v0.6.0 已有 admin 行）
  - 种子：3 个角色（admin / trader / viewer）+ 18 个权限点（system / strategy / sim / backtest / data / ai / notify 六大类）+ 角色-权限映射
  - 现有 `id=1` admin 用户：`is_super=true` + 绑 admin 角色（保留 Phase 6 历史数据）
- ORM：`db/models/permission.py` + `db/models/role.py`（Role / UserRole / RolePermission），在 `db/models/__init__.py` 集中导出供 alembic autogenerate

JWT 核心（`backend/app/core/`）：
- `security.py`
  - `hash_password` / `verify_password`：bcrypt 直调，72 字节截断（沿用 Phase 6 与 passlib 5.x 的兼容补丁）
  - `create_access_token(user_id)`：HS256，15min，payload 含 `sub` / `jti` / `type=access`
  - `create_refresh_token(user_id)`：HS256，30 天，jti 用于黑名单
  - `decode_token(token, expected_type=...)`：严格校验 access / refresh 类型，防止互用
  - `blacklist_jti` / `is_jti_blacklisted`：Redis `auth:bl:<jti>`，TTL = token 剩余有效期
- `auth_deps.py`
  - `AuthUser` 数据类：扁平的 `role_codes` / `permission_codes` / `data_scope`（取所有角色最宽 self < dept < all）
  - `get_current_user(request, db)`：Bearer access → 黑名单校验 → 一次查 users + roles + permissions（拒绝 N+1）
  - `require_permission(*codes)` / `require_any_permission(*codes)`：路由级权限闸门，super 用户绕过
  - `CurrentUser = Annotated[AuthUser, Depends(get_current_user)]`：路由签名直接用

业务层 / 路由（`backend/app/services/auth.py` + `backend/app/api/auth.py` + `backend/app/schemas/auth.py`）：
- `POST /api/auth/login`：用户名 + 密码 → 200 返回 `access_token` (JSON) + 写 refresh httponly cookie；更新 `last_login_at`；统一错误消息防用户名枚举
- `POST /api/auth/refresh`：从 cookie 读 refresh → 旋转新 refresh + 发新 access；旧 jti 拉黑（防重放）
- `POST /api/auth/logout`：拉黑 refresh + 拉黑 access（如果带了）+ 清 cookie，幂等
- `GET /api/auth/me`：返回 `id / username / display_name / is_super / roles[] / permissions[] / data_scope / last_login_at`
- Refresh cookie：`HttpOnly` + `SameSite=Strict` + `Path=/api/auth`（业务接口不带 refresh，进一步降 CSRF 面）+ 生产 `Secure` 开关

deps 软升级（`backend/app/deps.py`）：
- `get_current_user_id`：优先解析 `Authorization: Bearer <access>` 的 `sub`；缺失 / 失效则 fallback `settings.default_user_id`（向后兼容 v0.6.0 Basic Auth 时期的前端，老接口零改动）
- v0.7.0b 前端切完 JWT 后再硬切：拿不到 token 直接 401

配置（`backend/app/config.py`）：
- 新增 `jwt_access_expire_minutes` (15) / `jwt_refresh_expire_days` (30) / `refresh_cookie_name` / `refresh_cookie_path` / `refresh_cookie_secure` / `refresh_cookie_samesite`
- 保留 `jwt_expire_minutes` 兼容旧字段

工具：
- `backend/scripts/create_admin.py`：交互式创建 / 重置超级管理员（更新密码 + `is_super=true` + 绑 admin 角色），幂等

### Notes — v0.7.0a 边界

- 仍兼容 v0.6.0 Basic Auth：`AUTH_ENABLED=true` 时 ASGI 中间件继续生效，新 `/api/auth/*` 端点已挂载但需用户手动加白名单（或 v0.7.0b 一并切换）
- 前端 v0.7.0a 不做改动，仍走 Basic Auth；JWT 端到端验证用 curl / `/docs` / TestClient
- 权限闸门 `require_permission` 已就位但未挂任何路由（业务路由的 RBAC 改造留给后续小版本，按"先 read，再 write，再 delete"渐进）

### Added — Phase 7 RBAC 前端接入（v0.7.0b）

把 Phase 6 的 Basic Auth 平滑切换到 JWT，access 在内存、refresh 在 HttpOnly cookie。

前端：
- `types/index.ts`：新增 `TokenResponse` / `MeResponse` / `DataScope`
- `api/auth.ts`：裸 axios（不走 client 拦截器）封装 `apiLogin` / `apiRefresh` / `apiLogout` / `apiMe`，全部 `withCredentials`，避免 401-on-401 死循环
- `store/useAuthStore.ts`：彻底重写
  - 状态：`accessToken`（内存） + `userId` + `me` + `bootstrapping`
  - actions：`login` / `logout` / `refresh` / `loadMe` / `bootstrap`
  - 权限查询助手：`has(perm)` / `hasAny(...)` / `scope()` —— super 用户自动绕过
  - 非 hook 工具：`getAccessToken()` / `authHeader()` / `wsUrl(path)` —— `wsUrl` 把 access token 拼到 query 兼容 WS 端点
- `api/client.ts`：响应拦截器重写
  - 401 自动 `sharedRefresh()`（in-flight Promise 复用，并发请求只触发一次刷新）
  - 刷新成功 → 用新 token 重试原请求（仅一次，防死循环）
  - 刷新失败 → 跳 `/login?from=<path>`
  - 自带 `_retry` 标志位，`/auth/refresh` / `/auth/login` 自身 401 不再递归
- `pages/Login/index.tsx`：移除 btoa 拼 Basic Auth，直接调 `store.login(username, password)` → 走 `/api/auth/login`
- `App.tsx`：
  - `RequireAuth` 启动调 `bootstrap()` 用 cookie 静默刷新恢复登录态；刷新期间显示 Spin，避免闪回 Login
  - 顶栏新增 `UserMenu` 显示 `display_name` + 角色/超管标识 + 退出登录下拉
- Basic Auth 平滑下线：`AUTH_ENABLED` 默认 false，旧 `BasicAuthMiddleware` 代码保留但不再挂载

## [0.6.0] — 2026-05-27

### Added — Phase 6 Step 1：Basic Auth 鉴权

公网部署的前置必备：让 TCAlpha 不再 "0 鉴权裸奔"。

后端：
- `config.py` 新增 `auth_enabled` / `auth_username` / `auth_password_hash` / `auth_public_paths` / `auth_protect_docs`
- `middleware/basic_auth.py`：ASGI 中间件，同时覆盖 HTTP + WebSocket
  - HTTP 路径走标准 `Authorization: Basic <base64>` header
  - WebSocket 不能传 header，回退到 `?token=base64(user:pass)` 查询参数
  - 公共白名单走 `auth_public_paths`（默认 `/health` `/`），`/docs` 等元数据由 `auth_protect_docs` 控制
  - bcrypt 5.x 直接对接（绕过 passlib 4.x 自检兼容 bug，安全截断到 72 字节）
- `main.py`：按 `settings.auth_enabled` 开关挂载 `BasicAuthMiddleware`
- `scripts/gen_password_hash.py`：bcrypt 密码哈希生成工具

前端：
- `store/useAuthStore.ts`：Zustand store + sessionStorage 凭证（关 tab 即失效），导出 `authHeader()` / `wsUrl()` 工具
- `api/client.ts`：axios 请求拦截器自动注入 `Authorization`；响应拦截器收到 401 时清状态并跳 `/login`
- `api/ai.ts::streamChat`：SSE-over-fetch 同样带 Auth header
- `pages/Strategy/index.tsx`：WS 改走 `wsUrl()`，移除硬编码 `ws://localhost:8000`
- `pages/Login/index.tsx`：新增登录页（用户名 + 密码，自带探活校验）
- `App.tsx`：`RequireAuth` 路由守卫，未登录访问任意页面跳 `/login?from=<path>`

### Added — Phase 5 Step 4：图表 AI 分析

- `services/ai_chart.py` + `api/ai_chart.py`：`GET /api/ai/chart/analyze?symbol=&period=` SSE 流式
- `frontend/src/api/ai_chart.ts::streamChartAnalysis`：GET fetch + SSE 解析，复用 `authHeader()`
- `pages/Chart/index.tsx`：右上"AI 分析"按钮 → 抽屉打开 → 喂当前 symbol/period 给 AI 流式解读

### 工具 / 文档

- `.env.prod.example`：生产环境完整 `.env` 模板
- `docs/deploy.md`：从 0 到 v0.6.0 的部署 runbook + 安全自检

## [0.5.2] — 2026-05-27

### Added — Phase 5 Step 3 AI 盯盘

后端：
- `db/models/watchlist.py` + `ai_alert.py`：用户关注列表（user_id+symbol 唯一约束）+ AI 盯盘告警结果（含指标快照）
- 迁移 `3b597a00cb62_add_watchlists_and_ai_alerts`，server_default 兼容空表
- `services/ai_watcher.py`：核心盯盘函数
  - `build_snapshot(symbol)`：读 ArcticDB `bar_1d` 最近 60 根，算 MA5/10/20 / RSI14 / MACD（DIF/DEA/HIST 自实现 EMA）/ 5d & 20d 涨跌幅 / 量能比
  - `watch_symbol(user_id, symbol)`：拼 prompt → DeepSeek `response_format={"type":"json_object"}` 单次调用 → Pydantic `WatchResult` 严格校验 → 落 `ai_alerts` → `publish_event("ai.alert.{level}")`
  - 系统 prompt 严格要求 level/signal/reason 三字段 JSON，禁止"建议买入"等投资建议措辞
- `tasks/ai_tasks.py`：
  - `ai_watch_all`（beat 触发，遍历所有 watchlist，可 `force=True` 跳过交易时段判断）
  - `ai_watch_one`（手动单标的）
  - `celery_app.py` beat 加 `crontab(minute='*/15', hour='9-14')`
- `api/watchlist.py` + `api/ai_alerts.py`：watchlist CRUD + alert 列表（level/symbol/only_unacked 过滤）+ ack + 手动触发 `POST /api/ai-alerts/watch/{symbol}`
- 集成：盯盘结果走 `ai.alert.warn` / `ai.alert.danger` 事件，用户在「通知中心」勾 `ai.alert.*` 即可推送到飞书

前端：
- `api/watchlist.ts` + `api/ai_alerts.ts`：API 封装
- `pages/AI/index.tsx` 改造为 Tabs：
  - **助手聊天**：保留原 chat（拆为 `Chat.tsx`）
  - **AI 盯盘**：告警卡片列表（level 段选 / 未读切换 / ack 按钮 / 折叠指标快照）
  - **关注列表**：股票增删 + 行内"盯一次"手动触发 + "查告警"跳转

工具：
- 无新外部依赖

## [0.5.1] — 2026-05-27

### Added — Phase 5 Step 2 通知中心 + 飞书推送

后端：
- `db/models/notify.py`：`NotifyRule` / `NotifyLog` 表（用户级飞书 webhook + 签名密钥 + 静音时段）
- `alembic/versions/a332786c9ac0_add_notify_rules_and_logs.py`：迁移（含 server_default 兼容空表）
- `core/event_bus.py`：统一事件总线 `publish_event(type, payload, level, user_id)`，底层 Redis pub/sub `events:*` 通道，命名 `category.action.subaction`
- `services/feishu.py`：`send_card` / `send_text`，HMAC-SHA256 签名 + Redis 令牌桶限流（100/min/webhook）+ httpx async
- `services/notify.py` / `schemas/notify.py` / `api/notify.py`：规则 CRUD + 历史查询 + 测试推送 + 事件类型 / 渠道元数据接口
- `workers/notify_dispatcher.py`：独立进程，`asyncio` psubscribe `events:*`，按 NotifyRule 通配匹配 + quiet_hours 过滤 + 30s SETNX 去重，分发到飞书并落 NotifyLog
- 业务接入：`runtime.py` 发出 `strategy.started/stopped/crashed`、`backtest_tasks` 发 `backtest.started/done/failed`、`main.py` 全局 exception handler 发 `api.exception`

前端：
- `api/notify.ts`：规则 / 历史 / 元数据 / 测试推送 API 封装
- `pages/Notify/index.tsx`：规则 + 历史 双 tab UI，规则 Drawer（事件类型多选 + 通配符 + 渠道 + webhook + 签名 + 静音时段 + 启用开关），逐行"测试"按钮 + 顶部"临时测试"弹窗
- `App.tsx` / `useWorkspaceStore.ts` / `WorkspaceTabs`：加路由 `/notify` + 侧栏菜单项 + tab 图标

工具：
- `Makefile`：`make notify` = `uv run python -m app.workers.notify_dispatcher`
- `.env.example`：飞书全局兜底占位（实际 webhook 走 PG，每用户独立）

## [0.5.0] — 2026-05-27

### Added — Phase 5 AI 助手（Step 1 / chat MVP）
- `backend/app/schemas/ai.py`：`ChatMessage` / `ChatRequest` DTO（多轮历史 + 可选 system + temperature）。
- `backend/app/services/ai.py`：OpenAI 兼容 `AsyncOpenAI` 单例 + `stream_chat()` 异步生成器，默认 DeepSeek（`AI_API_BASE` / `AI_API_KEY` / `AI_MODEL` 走 `.env`）。
- `backend/app/api/ai.py`：`POST /api/ai/chat` 改为真实 SSE 流式（替换 Phase 0 的 echo 占位），协议 `data: <chunk-json>` / `[DONE]` / `[ERROR]<msg>`。
- `frontend/src/api/ai.ts`：浏览器 SSE-over-fetch 客户端（EventSource 不支持 POST，故用 `ReadableStream` 自己拆 `data:` 帧），支持 `AbortController` 取消。
- `frontend/src/pages/AI/index.tsx`：气泡式聊天 UI — 流式打字效果、停止按钮、清空对话、Enter 发送 / Shift+Enter 换行、自动滚到底部。

### Added — 前端工作台升级
- `frontend/src/components/WorkspaceTabs`：多标签切换组件（基于 `@dnd-kit` 支持拖拽排序）。
- `frontend/src/components/PageScaffold.tsx`：统一的 flex 页面骨架组件，所有 page 复用。
- `frontend/src/store/useWorkspaceStore.ts`：Zustand 全局 workspace 状态（activeKey + 标签集合）。
- `frontend/src/main.tsx`：AntD 5 自定义主题 token（Layout / Menu / Card / Table / Button），统一圆角 8、控件高 36、表格 hover bg。
- 各 page（Dashboard / Chart / Strategy / Backtest / Data / AI）改造为 `PageScaffold` 子节点，统一外边距与高度。

### Changed
- `frontend/tsconfig.json`：移除 `references → tsconfig.node.json`，改 `include: ["src", "vite.config.ts"]` + `types: ["node"]`，修复编译路径。删除冗余的 `tsconfig.node.json`。
- `frontend/package.json`：`build` / `typecheck` 改为 `tsc --noEmit`（不再 emit 产物，避免污染工作树）。

### Chore
- 入仓 `.agents/` / `.codex/` / `AGENTS.md`：Codex 协作工具的共享 skills / hooks 配置，与 `.claude/` 同等待遇。

## [0.4.2] — 2026-05-26

### Fixed
- **Bug B** — `core/runtime.py::StrategyRuntime.run`：策略 task 异常退出时未清理 `strategy:running:{id}` Redis key，下次启动卡在 "strategy already running"。改为 try/finally 包住主循环，finally 中 `delete(running_key) + delete(stop_key)` 并把 DB status 写成 `stopped`/`error`。
- **Bug C** — `users` / `symbols` 表 schema 与 ORM 漂移：早期 `User` 模型加了 `password_hash` / `is_active` 但缺迁移；`select(User)` 报 `UndefinedColumn`。新增迁移 `27f8f3ac68c7_sync_users_and_symbols_schema`，补齐两列（`server_default` 兼容已有行）并把 `users` / `symbols` 的唯一约束统一为唯一索引。
- **Bug D** — `/health` 与根路径 `/`、`FastAPI(version=...)` 都硬编码 `0.1.0`。改为在 `app/__init__.py` 用 `tomllib` 读 `pyproject.toml`，三处统一引用 `app.__version__`。

### Added (chore)
- `backend/app/main.py` 末尾加 `if __name__ == "__main__": uvicorn.run(...)` 入口，PyCharm 右键 Run 即可启动后端（无需自配 module 命令）。

## [0.4.1] — 2026-05-26

### Fixed
- `core/backtest_engine.py::_load_bars`：naive `pd.Timestamp` 与 tz-aware `DatetimeIndex` 比较抛 `TypeError`，导致实时策略 worker 启动后立刻 crash、回测引擎读 ArcticDB 也受同一 bug 影响。改为按 index 的 `tz` 自动构造对齐的 start/end Timestamp。

### Added
- `backend/scripts/inject_fake_kline.py`：联调专用，向 ArcticDB `bar_1d` 灌 200 根带金叉/死叉走势的合成日 K（金叉位于约 60-120 根处，死叉位于 180+），用于无网络环境下的策略 / 回测路径快速验证。
- `backend/scripts/ws_listener.py`：联调专用 WebSocket 客户端，同时订阅 `/ws/orders` + `/ws/signals` 把消息打 stdout，方便观察 `SimGateway` → Redis pub/sub → WS 推送链路。

## [0.4.0] — 2026-05-26

### Added
- Phase 4：实时策略 worker + 模拟撮合
  - Alembic 迁移 `3b8d5e2a7c19`：`sim_orders` 表
  - `core/pubsub.py`：Redis channel 命名约定 + 同步发布工具
  - `core/sim_gateway.py`：`SimGateway`（`send_order` / `match` / `cancel` / `position`），按下一根 bar 开盘价撮合，结果发 Redis pub/sub
  - `core/runtime.py`：`StrategyRuntime`（ArcticDB 历史热身 → 循环驱动 `on_bar` → 下单），Redis stop key 优雅退出
  - `tasks/strategy_tasks.py`：`run_strategy` Celery 长跑任务（24h `time_limit`）
  - `api/ws.py`：`/ws/orders`、`/ws/signals`、`/ws/quote`（Redis pub/sub → WebSocket 转发）
  - `api/strategy.py`：新增 `start` / `stop` / `running` 端点
  - `api/sim.py` + `services/sim.py`：订单列表、持仓聚合
- 前端
  - `hooks/useWebSocket.ts`：自动重连 WebSocket hook
  - `api/sim.ts`：模拟交易 API 封装
  - Strategy 页面重构：策略列表 + 选中面板（启停按钮 + 信号卡 + 实时订单），WebSocket 订阅 `/ws/orders` + `/ws/signals` 实时更新

## [0.3.0] — 2026-05-26

### Added
- Phase 3：策略管理 + 回测引擎（Celery 异步）
  - Alembic 迁移 `2a4f7c91e035`：`users` / `strategy_configs` / `backtest_jobs` / `backtest_trades` 表
  - `core/backtest_engine.py`：`BacktestEngine`（ArcticDB 读取 → `on_bar` 撮合 → 指标计算 → 落 PG）
  - `strategies/examples/ma_cross.py`：`MaCrossStrategy` 完整 `on_bar`（金叉开多 / 死叉平多）
  - `tasks/backtest_tasks.py`：`run_backtest` Celery 异步任务（1h `time_limit`）
  - `services/strategy.py`：策略 CRUD + 策略类注册表
  - `services/backtest.py`：提交 / 状态 / 成交明细查询
  - `api/strategy.py` & `api/backtest.py`：完整 REST 路由
- 前端
  - `api/strategy.ts` + `api/backtest.ts` 封装
  - Strategy 页面：策略列表 + 新建 / 编辑 Drawer + 参数配置
  - Backtest 页面：提交表单 + 状态轮询 + 资金曲线（ECharts）+ 指标卡 + 成交明细

### Fixed
- `@tailwindcss/postcss` 依赖缺失

## [0.2.0] — 2026-05-26

### Added
- Phase 2：前端布局 + K 线图
  - App Shell：侧边栏导航 + 路由（仪表盘 / K 线 / 策略 / 回测 / 数据 / AI）
  - Chart 页面：lightweight-charts K 线主图 + 成交量副图 + 周期切换 + 股票搜索
  - Data 页面：股票列表表格（搜索 / 交易所过滤 / 分页）+ 一键刷新 + 单股 K 线下载触发
  - Dashboard：后端状态卡 + 股票数量统计
  - `POST /api/market/symbols/refresh` 触发全市场股票列表刷新 Celery 任务

### Fixed
- `deps.py` 模块级绑定导致 `async_session_factory` 为 None 的启动 bug
- Vite 代理补全 `/health` 路径

## [0.1.0] — 2026-05-26

### Added
- Phase 0：项目骨架（FastAPI + Celery + SQLAlchemy + ArcticDB + React + Docker）
- Phase 1：数据层
  - `Symbol` ORM 模型（symbols 表）
  - AKShare 日 K 下载（限流令牌 + tenacity 重试 + ArcticDB 增量落库）
  - Celery 任务：`refresh_symbol_list` / `download_one_symbol` / `download_daily_kline_all`
  - market API：`GET /api/market/symbols` / `GET /api/market/kline/{symbol}` / `POST /api/market/kline/{symbol}/download`
  - CLAUDE.md 项目规范文档
