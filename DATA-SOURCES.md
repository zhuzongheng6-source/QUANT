# QUANT 数据源调研：免费、可信、可整合的数据栈

> 调研日期：2026-11-26（香港）
> 适用项目：`QUANT`（SPY/BIL 日频、趋势/固定仓位/买入持有）
> 结论口径：个人研究用途、0 元预算优先、允许注册免费 key、不购买付费数据
> 本次工作：只做调研与实测，未修改任何现有代码或数据文件

---

## 0. 摘要（TL;DR）

1. **免费且可信的方案不是“找一个万能 API”，而是分层数据栈**：
   **Tiingo（复权主源）+ SSGA 官方分红文件（公司行动真值）+ Nasdaq/FRED（免 key 独立校验）+ IBKR（执行对账）**。
2. **上一轮路线图中的 Stooq 已不能作为备源**：实测返回 JS 验证页，无法直接取 CSV；有开发者记录称 2026-04 起批量 CSV 需在网页过 captcha 获取 per-user key。第二数据源应改为 **Nasdaq**（约 10 年原始 OHLCV，免 key），交易日历校验用 **FRED**。
3. **不要直接相信供应商的 adjclose**。用“原始收盘价 + 官方分红”自算复权，本次实测与 Yahoo 历史复权因子吻合到 **0.00023 bp**；这样新分红不会回溯改写历史，且完全可复现。
4. **当前项目的事件文件不完整**：`data/events-20261124-SPY.json` 只有 2026 年三次分红，缺 2025 年四次；快照中 1.16% 的差额正是 2025 年分红。要做 point-in-time 复算，事件必须覆盖全部历史。
5. 对现有 2026 样本外结果的影响预计在 **1 bp 量级**；真正的收益是**可复现性、异常发现能力和数据溯源**，不是收益率本身。

---

## 1. 背景与目标

项目路线图把“数据接入与质量检查”列为 P0：

- 第二数据源交叉校验（原建议 Stooq / IBKR / FRED）；
- 自动检测缺口、跳变、拆股、分红异常，并写入 snapshot `summary.json`；
- 自动刷新 + 失败告警；
- 公司行动 point-in-time 化。

本次调研要回答三个问题：

1. 哪些源**免费**、**长期可用**、**数据质量足够**？
2. 如何用不同平台/不同方式**整合**出比单一供应商更真实的数据？
3. 对现有 QUANT 平台，最小改动路径是什么？

---

## 2. 方法与可复现性

- 时间：2026-11-26 凌晨，香港网络。
- 环境：macOS；Python `/path/to/quant-env/bin/python`（pandas 2.3.3、numpy 2.2.6、requests 2.32.5、openpyxl）。
- 方式：直接请求公开端点；用冻结的 2018–2025 SPY 数据做交叉核对；用官方分红文件重算复权因子。
- 限制：沙箱只读，未能保存中间文件；所有验证均为**现场实测**，命令可按下文端点复现。
- 标注规则：**“实测”**= 本次真实请求返回；**“文档”**= 官网/第三方资料，未注册实测。

---

## 3. 关键实测结果

### 3.1 总表

| 源 | 实测方式 | 结果 | 结论 |
|---|---|---|---|
| Yahoo chart | query1/query2 的 v8 chart、v7 download、v8 spark | 首次 200；随后持续 **HTTP 429**，正文仅 `Too Many Requests`（19 字节），约 40 分钟未恢复 | 不能作唯一主源 |
| Stooq | `stooq.com/q/d/l/?s=spy.us&i=d` | 返回 JS 验证页（“This site requires JavaScript…”），无 CSV | 不能再当免密钥备源 |
| Nasdaq | `api.nasdaq.com/api/quote/{SYM}/historical` | 免 key；SPY/BIL/AAPL 均 **2513 行**，2016-11-25..2026-11-24 | 可作 10 年内原始价校验 |
| Nasdaq vs Yahoo | SPY 2018-01-02..2025-12-31 | 两边均 **2011 个交易日**，互相缺失 **0** 天；收盘最大差 **$0.06999877929689546**（2019-07-16，约 **2.33 bp**） | 独立校验有效 |
| FRED SP500 | `fredgraph.csv?id=SP500` | 2018–2025 非空日期 **2011 个**，与 Yahoo 完全一致，双向缺失 0 | 可作交易日历/指数校验 |
| SSGA 官方分红 | `spdr-etf-historical-distributions.xlsx` | **13,464 行**；SPY **136 条**（1993-03-19 起），BIL **233 条**（2007-07-02 起）；6 位小数，含短期/长期资本利得 | **公司行动真值** |
| 自算复权 | 官方 7 次分红 + 原始 close | 2025-01-02 累计因子 **0.980732878940**；Yahoo **0.980732856152**；差 **0.00023 bp** | 复权可完全接管 |
| Eastmoney | 600519 前复权 | `dktotal=6050`，日线正常 | A 股可用 |
| Tencent | 00700 前复权 | `qfqday` 正常返回 | 港股可用 |
| HKEX 每日文件 | `d261125e.htm` | **25,580,087 字节**；仅最近一日，更早日期 404 | 免费仅当日，历史付费 |
| EODHD demo | AAPL.US | curl 200；同一 URL 用 urllib 返回 403 | 必须用目标客户端实测 |
| Twelve Data demo | AAPL / SPY | curl 200；urllib 401；SPY 401（demo key 不含 SPY） | demo key 不代表免费额度 |
| Alpha Vantage | 官方文档 | `TIME_SERIES_DAILY_ADJUSTED` 明确标注 **Premium** | 免费 key 只有非复权日线 |

### 3.2 三个关键发现

**发现一：Yahoo 的复权价可以被精确复现。**

Yahoo 的调整因子等价于：

```text
factor_t = Π_{ex_date > t} (1 - (dividend + capital_gain) / close_{ex_date-1})
```

以 2025-01-02 为观测点：

- 2025 年四次分红：2025-03-21 `1.695528`、06-20 `1.761117`、09-19 `1.831114`、12-19 `1.993368`；
- 2026 年三次分红：2026-03-20 `1.796999`、06-18 `1.903516`、09-18 `1.888834`；
- 2025 年因子连乘 `0.988393075009`（贡献 1.16%）；
- 2026 年因子连乘 `0.992249848504`（贡献 0.78%）；
- 合计 `0.980732878940`；
- Yahoo 同日 `adjclose/close = 0.980732856152`；
- 差异 `0.00023 bp`。

结论：供应商的 adjclose 不是黑盒真值，而是“原始价 + 事件”的派生量。我们应当自己算，并把供应商结果作为对账对象。

**发现二：当前事件文件缺 2025 年，导致历史不可复算。**

`data/events-20261124-SPY.json` 只有 2026 年三次分红；2025 年四次完全缺失。快照中 2025-01-02 的 `adjclose/close = 0.9807329605495169`，若只用 2026 年事件只能得到 `0.992249848504`，差 1.16%——这 1.16% 就是 2025 年分红。要满足 point-in-time，事件必须覆盖全部历史（SPY 1993+、BIL 2007+），而不是只覆盖刷新窗口。

**发现三：BIL 的分红不能忽略。**

BIL 是 T-bill ETF，价格长期在 100 美元附近，收益几乎全部来自月度分红。2026 年至 11 月 2 日共 10 次分红，合计 **2.711819 美元/份（约 2.7%）**。若回测只用原始收盘价，BIL 的年化收益会被系统性低估约 2.7%；在 70% BIL 仓位下，组合收益偏差约 **1.9%/年**。当前平台使用 Yahoo adjclose 没有这个问题，但切换到“原始价 + 自算复权”后必须把 BIL 事件纳入。

### 3.3 与上一轮路线图的差异

| 上一轮建议 | 本次结论 | 原因 |
|---|---|---|
| Stooq 作第二数据源 | **改为 Nasdaq** | Stooq 已加 JS 验证/captcha，CSV 不可直接取 |
| FRED 校验 ETF 价格 | **只校验日历/指数水平** | FRED `SP500` 是指数，不是 SPY 复权价 |
| IBKR 历史数据 | **保留，作执行/对账** | 有账户时仍是最强执行真值；无账户则不可用 |
| Yahoo 作主源 | **降为备源** | 429 无 SLA；复权会回溯改写 |
| 事件文件随刷新窗口生成 | **必须全历史** | 否则无法复算历史复权 |

---

## 4. 数据源清单

### 4.1 美股行情

| 源 | 免费额度 | 复权/事件 | 定位 | 备注 |
|---|---|---|---|---|
| [Tiingo](https://www.tiingo.com/pricing) | 1,000 次/日、50/时、500 个代码/月 | `adjClose` + `divCash` + `splitFactor` | **主源** | 需注册 key；免费档仅内部使用；美股/ETF |
| Yahoo chart | 无 key、无 SLA | adjClose + 3 位小数事件 | 备源 | 必须缓存 + 退避；429 风险 |
| Nasdaq | 无 key，约 10 年 | 仅原始 OHLCV | **独立校验** | 非官方接口；不能替代复权源 |
| EODHD | 20 次/日、1 年历史 | EOD + splits + dividends | 备源 | demo key 仅少数代码 |
| Polygon | 5 次/分、约 2 年 | 聚合 + 参考数据 | 备源 | 免费档是否含 splits/dividends 以账户为准 |
| Twelve Data | 800 credits/日、8/分 | 需确认调整口径 | 备源 | Basic 免费档 |
| Alpha Vantage | 25 次/日 | 复权端点 **Premium** | 不推荐 | 免费仅非复权日线 |
| Alpaca | 免费 IEX、2016+ | bars + corporate actions | 备源/执行 | 需 key；IEX 单一交易所 |
| IBKR | 有账户即可 | `ADJUSTED_LAST` + 公司行动 | **执行/对账** | 有 pacing 限制；需 TWS/Gateway |
| FMP | 250 次/日（文档） | 历史端点是否仍免费需实测 | 备选 | 免费政策变动较多 |
| marketstack | 100 次/月、12 个月 | EOD | 不推荐 | 额度太小 |
| Finnhub | 免费档无美股历史 OHLCV | — | 不适用 | candles 属付费 |
| Stooq | 已失效 | — | 不用 | JS 验证/captcha |
| IEX Cloud | 2024-08-31 已关停 | — | 不用 | — |

### 4.2 官方/公司行动/基本面

| 源 | 额度 | 内容 | 用途 |
|---|---|---|---|
| [SSGA 分红 xlsx](https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions) | 免费 | 全部 SPDR ETF 分红，含资本利得，6 位小数，SPY 1993+ | **公司行动真值** |
| [SEC EDGAR](https://www.sec.gov/os/accessing-edgar-data) | 10 req/s，需描述性 UA | filings、XBRL companyfacts/frames、13F、Form 4 | 基本面、事件、持仓 |
| [FRED/ALFRED](https://fred.stlouisfed.org/docs/api/fred/) | 120 req/min（key） | 宏观、利率、日历；ALFRED vintage | 宏观、point-in-time |
| [CBOE VIX CSV](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) | 免费 | VIX 等，1990+ | 波动率 |
| [NY Fed SOFR](https://markets.newyorkfed.org/api/rates/secured/sofr/last/3.json) | 免费 | SOFR | 利率 |
| [Treasury Fiscal Data](https://fiscaldata.treasury.gov/api-documentation/) | 免费、无 key | 国债、财政 | 宏观 |
| [CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | 免费 | 持仓 | 情绪/仓位 |
| [FINRA 空头持仓](https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data) | 免费 | 空头持仓，滚动 1 年 + 归档 | 情绪 |
| [OpenFIGI](https://www.openfigi.com/api) | 免费 | FIGI/ISIN/CUSIP 映射 | 标识对齐 |

### 4.3 A 股/港股

| 源 | 免费额度 | 特点 | 定位 |
|---|---|---|---|
| BaoStock | 免费、无注册 | A 股，复权可选，历史长，稳定 | 研究主源 |
| AkShare | 免费、无 key | A/H/期货/宏观，接口多但易失效、IP 限流 | 快速原型 |
| Tushare | 120 积分免费 | 仅非复权日线；复权因子需更高积分 | 备源 |
| Eastmoney | 免费 | A 股前/后复权；实测 600519 返回 6050 根 | 校验/补充 |
| Tencent | 免费 | 港股前复权；实测 00700 正常 | 校验/补充 |
| QMT/xtquant | 券商账户 | A 股实时/历史，实盘首选；订阅约 100 只上限 | 实盘 |
| HKEX 每日文件 | 免费仅最近一日 | 全市场当日行情（约 25 MB HTML） | 自建归档 |
| HKEX 历史全盘 | 付费（据调研约 HK$5,000/月） | 二进制全 tick | 机构 |

### 4.4 其他（按需）

- **加密**：Binance/OKX/Coinbase 公开 klines；CoinGecko 约 30 次/分。
- **FX**：ECB reference rates、Frankfurter、HKMA。
- **宏观聚合**：DBnomics（免 key，聚合 FRED/ECB/IMF/World Bank）。
- **指数成分历史**：Wikipedia + GitHub `fja05680/sp500`（免费，需注意准确性）；严谨研究用 CRSP/Compustat。
- **学术**：先查 CUHK 是否订阅 WRDS；CRSP/Compustat/IBES 是最可信的 point-in-time 来源。

---

## 5. 给 QUANT 的推荐组合

### 5.1 角色分工

| 角色 | 首选 | 校验/备选 | 频率 |
|---|---|---|---|
| SPY/BIL 复权日线 | Tiingo | Yahoo（缓存） | 每日 |
| 原始收盘 | Nasdaq | — | 每日 |
| 交易日历 | FRED SP500 | 交易所假日表 | 每日 |
| 分红/资本利得 | SSGA 官方 xlsx | 发行人/SEC | 每周 |
| 执行/成交 | IBKR | 券商对账单 | 每日 |
| 宏观/利率 | FRED + ALFRED | NY Fed/Treasury | 每日/每月 |

### 5.2 端点速查

```text
# 主源：Tiingo（1 次/代码，全历史；之后增量）
GET https://api.tiingo.com/tiingo/daily/SPY/prices?startDate=2018-01-01&token=$TIINGO_TOKEN

# 校验：Nasdaq（免 key，约 10 年，仅原始 OHLCV）
GET https://api.nasdaq.com/api/quote/SPY/historical?assetclass=etf&fromdate=2016-11-25&todate=2026-11-24&limit=9999

# 日历：FRED（免 key，CSV 含空值行）
GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500

# 公司行动真值：SSGA（免 key，全部 SPDR）
GET https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx

# 港股校验：Tencent（免 key，前复权）
GET https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=hk00700,day,2025-01-01,2026-12-31,320,qfq

# A 股校验：Eastmoney（免 key，fqt=1 前复权，fqt=2 后复权）
GET https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600519&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=1&beg=20240101&end=20261231
```

### 5.3 请求量估算

- 每日：Tiingo 2–3 次（SPY/BIL，增量）+ Nasdaq 2 次 + FRED 1 次 ≈ **6 次/日**。
- 每周：SSGA xlsx 1 次 + 全量对账。
- 远低于 Tiingo 1,000/日、FRED 120/分、SEC 10/秒的限制。

---

## 6. 整合架构

### 6.1 数据模型：原始价是唯一真值，复权价是派生量

```text
bars(symbol, date, open, high, low, close, volume, source, as_of, raw_sha256)
events(symbol, ex_date, dividend, st_cg, lt_cg, split_factor, source, as_of)
adj(symbol, date, factor, method, events_sha256)
```

- 主键：`(symbol, date, source, as_of)`。
- 回测只读本地 `adj`，不直接读供应商 adjclose。
- `events` 与 `bars` 分开存，避免每个价格行重复存事件。

### 6.2 源优先级与合并规则

| 字段 | 优先级 |
|---|---|
| 价格 | Tiingo > Yahoo > Nasdaq（Nasdaq 只校验，不进主序列） |
| 分红 | SSGA 发行人文件 > SEC/公司公告 > Tiingo > Yahoo |
| 拆股 | Tiingo `splitFactor` > Nasdaq splits > SEC 8-K |
| 日历 | FRED > 交易所假日表 |

冲突处理：

- 以 **ex-date** 对齐；金额容差 **0.5 美分**；拆股按精确比例。
- 无法解释的差异写入 `checks`，并触发告警；不静默覆盖。
- 同一 `as_of` 重跑必须得到同一内容哈希（幂等）。

### 6.3 复权算法与验证

```text
factor_t = Π_{ex_date > t} (1 - (dividend + capital_gain) / close_{ex_date-1})
           × Π (1 / split_ratio)
```

验证结果（本次实测）：

| 项目 | 值 |
|---|---|
| 2025 年因子 | 0.988393075009 |
| 2026 年因子 | 0.992249848504 |
| 合计 | 0.980732878940 |
| Yahoo | 0.980732856152 |
| 差异 | 0.00023 bp |

注意事项：

- Yahoo 事件金额只保留 3 位小数（BIL 0.274 vs 官方 0.273931），单次误差可达 0.1 bp；官方 6 位小数可避免。
- 资本利得（ST/LT CG）也要计入，否则总收益会被低估。
- 分红用 **ex-date**，不用 payable date。
- 该算法假设分红按除息前收盘价再投资；与精确总收益的差异在单次事件 <1 bp，长期可忽略。

### 6.4 Point-in-time

- 每次抓取写 `as_of`；快照 **write-once**，不覆盖旧版本。
- 分红用 ex-date；基本面用 SEC `filed` 日期；宏观用 ALFRED vintage。
- 指数成分用历史成分表，避免幸存者偏差；股票池扩大时必须处理退市收益（CRSP 最完整）。
- 供应商修订（revision）单独存版本，不覆盖历史。

### 6.5 刷新与告警

- 美股收盘后 **06:30 HKT** 运行；港股 17:00 HKT。
- 增量：`startDate=最后日期`；每周一次全量。
- 429/5xx 指数退避；连续失败熔断并邮件告警（现有 163 邮箱 MCP 可直接用）。
- 429 时保留旧快照，不写半成品；告警里带 URL、状态码、重试次数。

### 6.6 存储

```text
data/raw/<source>/<symbol>/<as_of>.json.gz     # 原始响应
data/bars/<symbol>/<year>.parquet              # 规范化价格
data/events/<symbol>.parquet                   # 公司行动
data/snapshots/<date>-<hash>/manifest.json     # 溯源与校验
```

`manifest.json` 至少包含：

```json
{
  "as_of": "2026-11-26T06:30:00+08:00",
  "symbol": "SPY",
  "source": "tiingo",
  "url": "https://api.tiingo.com/...",
  "http_status": 200,
  "etag": "...",
  "raw_sha256": "...",
  "rows": 2011,
  "first": "2018-01-02",
  "last": "2025-12-31",
  "events_sha256": "...",
  "adjustment_method": "ratio_prev_close",
  "checks": {"calendar": "pass", "ohlc": "pass", "cross_source_max_diff_bp": 2.33}
}
```

---

## 7. 质量检查清单

| 检查 | 阈值/动作 |
|---|---|
| 交易日历 vs FRED | 任何缺失告警；缺失率 >0.5% 阻断 |
| OHLC 逻辑 | `low ≤ min(open,close)`、`high ≥ max(open,close)`，违反即阻断 |
| 重复/零/负/NaN | 阻断 |
| 跨源收盘差 | >5 bp 告警，>25 bp 阻断（实测最大 2.33 bp） |
| 分红金额 | >$0.0005 告警，>$0.005 阻断 |
| 自算 vs 供应商复权 | >1 bp 告警，>10 bp 阻断 |
| 单日跳变 | 绝对日收益 > 8σ 或 >10% 时人工复核，先查拆股/分红 |
| 成交量 | 交易日为 0 告警（ETF 极少） |
| 新鲜度 | 最后日期 < 最近收盘日 阻断 |
| 溯源 | URL、抓取时间、HTTP 状态、sha256、parser 版本、as_of 缺一不可 |

建议把检查结果写入 `summary.json` 的 `checks` 字段，并在每日报告里给出一行摘要。

---

## 8. 成本与合规

| 方案 | 成本 | 覆盖 | 适合 |
|---|---|---|---|
| 全免费 | 0 | 美股 EOD 复权、官方分红、宏观、日历 | 当前平台 |
| 轻付费 | 约 $20–30/月 | 更长历史、更多市场、更多调用（Polygon/EODHD） | 扩展期 |
| 学术 | 0（校内） | CRSP/Compustat/IBES，真正 point-in-time | 论文级 |
| 港股历史 | 约 HK$5,000/月 | 全盘 tick | 机构 |

合规提醒：

- **Yahoo/Nasdaq/Stooq** 都是非官方接口，ToS 可能限制自动化；个人研究可用，不要公开再分发。
- **Tiingo 免费档**仅限内部使用；再分发需付费计划。
- **FRED 的 SP500 序列**版权属 S&P；引用可以，再分发需注意。
- **HKEX** 实时/历史数据再分发需授权。
- **SEC** 要求描述性 UA，限 10 req/s；遵守 fair access。

---

## 9. 落地步骤（不改现有代码的前提下）

1. 注册 Tiingo，token 放环境变量/钥匙串，**不入库**。
2. 用 SSGA xlsx 回填 SPY/BIL **全部历史分红**（SPY 1993+、BIL 2007+），替换当前只有 2026 的事件文件。
3. 用“原始 close + 事件”自算 adj，与 Yahoo/Tiingo 对账，目标 <1 bp。
4. 加 Nasdaq 10 年原始 close 校验 + FRED 日历校验。
5. `manifest.json` 增加 `as_of`、`source`、`checks`、`events_sha256`。
6. 每日 06:30 刷新 + 失败邮件；每周对账报告。
7. 再扩展 A/H（BaoStock/AkShare 研究 → QMT 实盘）。

预期效果：

- 请求量约 6 次/日；
- 复权误差 <1 bp；
- 跨源差异 <5 bp；
- 缺口、跳变、分红异常当天发现；
- 任意历史快照可由 raw + events 重算。

---

## 10. 未验证项与风险

- **未实测**：Tiingo、Polygon、Alpaca、Twelve Data、FMP、Tushare、BaoStock、QMT、WRDS（无 key/账户/包）。其限额来自官网或第三方资料，可能调整。
- **Yahoo 429** 可能是临时 IP 限流，但仍无 SLA，不能作唯一主源。
- **Nasdaq** 是非官方接口，约 10 年上限；更长历史需 Tiingo/EODHD/CRSP。
- **SSGA xlsx** 结构可能变，解析应按表头名，不要按列号。
- **SPY/BIL 在 2018–2026 窗口内无拆股**，拆股路径未实测。
- **HKEX** 免费文件只有最近一日；要历史只能每日自建归档或付费。
- **指数成分/退市收益**：免费源不完整，严谨回测需 CRSP 或类似数据库。

---

## 附录 A：参考链接

- Tiingo 定价：<https://www.tiingo.com/pricing>
- Alpha Vantage 文档（复权端点标注 Premium）：<https://www.alphavantage.co/documentation/>
- EODHD 计划：<https://eodhd.com/help/plans>
- Alpaca 市场数据：<https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api>
- SEC EDGAR 访问：<https://www.sec.gov/os/accessing-edgar-data>
- FRED API：<https://fred.stlouisfed.org/docs/api/fred/>
- SSGA 分红文件入口：<https://www.ssga.com/us/en/intermediary/resources/documents/etf-dividend-distributions>
- CFTC COT：<https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm>
- FINRA 空头持仓：<https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data>
- Treasury Fiscal Data：<https://fiscaldata.treasury.gov/api-documentation/>

## 附录 B：本次实测数据摘要

```text
Yahoo 429 响应体长度：19 字节
Nasdaq 历史深度：2016-11-25 .. 2026-11-24，2513 行
Nasdaq vs Yahoo：2011/2011 交易日，0 缺失，最大差 $0.06999877929689546（2019-07-16）
FRED SP500：2011 个非空日，与 Yahoo 完全一致
SSGA：13,464 行；SPY 136 条；BIL 233 条
SPY 2025 分红：1.695528 / 1.761117 / 1.831114 / 1.993368
SPY 2026 分红：1.796999 / 1.903516 / 1.888834
BIL 2026 分红合计：2.711819（10 次）
复权因子：2025=0.988393075009，2026=0.992249848504，合计=0.980732878940
Yahoo 同日因子：0.980732856152；差 0.00023 bp
HKEX 每日文件：25,580,087 字节，仅最近一日
Eastmoney 600519：dktotal=6050
```
