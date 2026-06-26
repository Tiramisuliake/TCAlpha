import type { FactorWeights } from "@/types";

/** 因子元信息：多因子选股权重输入 / 结果列 / 因子检验下拉共用。
 *
 * 抽到独立模块（而非 FactorScreen.tsx 导出），避免组件文件混导出常量触发
 * react-refresh/only-export-components 警告。
 */
export const FACTORS = [
  { key: "mom_20", label: "20日动量", unit: "pct", desc: "20 日区间收益率，越高越强" },
  { key: "mom_60", label: "60日动量", unit: "pct", desc: "60 日区间收益率，越高越强" },
  { key: "volatility", label: "波动率", unit: "pct", desc: "年化波动率，越低越优（低波动溢价）" },
  { key: "trend_slope", label: "趋势斜率", unit: "num", desc: "对数收盘价线性回归斜率年化，越高越强" },
  { key: "vol_surge", label: "量能放大", unit: "x", desc: "近 5 日均量 / 近 20 日均量，越高越活跃" },
  { key: "rev_5", label: "5日反转", unit: "pct", desc: "近 5 日收益，越低（跌多）越优——短期反转，与动量对冲" },
  { key: "rsi_14", label: "RSI", unit: "rsi", desc: "RSI(14) Wilder，越低越超卖——反转风格" },
  { key: "boll_pctb", label: "布林%B", unit: "pctb", desc: "布林带位置，越低越接近下轨——超卖" },
  { key: "corr_pv", label: "量价相关", unit: "num", desc: "近 20 日收盘价 vs 成交量相关性，越高量价齐升（资金确认）" },
  { key: "amihud", label: "非流动性", unit: "lo", desc: "Amihud 非流动性 mean(|日收益|/成交额)，越低流动性越好" },
  { key: "obv_slope", label: "OBV斜率", unit: "num", desc: "能量潮近 20 日回归斜率 / 日均量，越高资金净流入" },
] as const;

/** 多因子缺省权重：动量/趋势/量能类 1，反转/量价类 0（按需开启）。与后端 _DEFAULT_WEIGHTS 一致。 */
export const DEFAULT_FACTOR_WEIGHTS: FactorWeights = {
  mom_20: 1,
  mom_60: 1,
  volatility: 1,
  trend_slope: 1,
  vol_surge: 1,
  rev_5: 0,
  rsi_14: 0,
  boll_pctb: 0,
  corr_pv: 0,
  amihud: 0,
  obv_slope: 0,
};
