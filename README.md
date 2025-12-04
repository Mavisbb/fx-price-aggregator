# 📈 FX Price Aggregator

这个系统提供实时usd base的外汇和金属现货数据，计算指标，可视化波动热图，和交互式图形用户界面。
---
##  Overview
**为了避免BBG不稳定或无法访问的情况，这个aggregator可以从稳定的公共 API 获取实时外汇现货价格清理和管理历史数据，计算技术指标（RSI/MACD/Bollinger Bands），用 GUI 显示所有信息，方便用户日常交易监控。**
---
# 🗂 Project Structure
```
fx-aggregator/
│── main.py             # Core logic for data loading, indicators
│── gui.py              # Tkinter GUI 包含四个tab
│── config.yaml         # Currency pairs, API settings
│── requirements.txt    # Python dependency list
│── data/
│    ├── daily.csv      # 历史价，用来画 MA / Bollinger / MACD / RSI / RV / rolling corr / heatmap 图
│    ├── intraday.csv   # Dashboard 显示最新价
     ├── volatility.csv # 用来画Vol Surface 和 RV 图
```
---
# 🛠️ 创建虚拟环境

```bash
cd ~/Downloads/fx_aggregator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
---
# 🖥️ 启动 GUI面板

```bash
python gui.py
```
---
# 🔧 Configuration (`config.yaml`)主要逻辑:

* **invert = false** → API returns quote currency directly
  * Example: `USDHKD` → request `HKD`
  
* **invert = true** → API returns base currency and invert it
  * Example: `AUDUSD` → request `AUD`

确保所有 prices normalized to “1 USD = x quote units” logic.

---
# 📊 GUI 功能详解 (`gui.py`)
GUI 分为四个主要 Tab，每个对应交易员日常需要的一个操作面板。
---

## **TAB 1 — 抓取Data**
* 第一次运行`Fetch 5Y History`时，系统会调用 API 一次性抓取过去 5 年的每日 FX 历史价格，并写入 daily.csv。
如果 daily.csv 已经存在，则跳过，不会重复抓取，也不会覆盖历史数据。
* 点击`Daily Fixing Update`程序会读取 daily.csv 中最后一个日期 last_date，只抓取 last_date + 1 到今天缺失的fixing，只补增量，不会重复抓历史数据也不会覆盖旧数据，通过自动合并和去重最终形成一个数据连续且不断增加的5年+的历史数据库。
* `Intraday Snapshot`用于抓取当前最新的FX spot price（类似 BBG 的 BGN Last Price），每按一次按钮 = 写一次当下价格记录在 intraday.csv 中（不覆盖历史），以便在 GUI Dashboard 中显示最新价格与昨天fixing作对比。
* `Recompute Vol`是根据 daily.csv 的历史价格计算30/60/90/180/250日的历史波动率。计算完成后会写入 volatility.csv，用于后面 “History & Vol” 与 “Vol Surface” 图表使用。

好处：
✔ 跟 Bloomberg 类似的实时性
✔ 每 120 秒自动刷新
✔ 可以用于 Dashboard 的最新价格更新

---

## **TAB 2 — FX Dashboard**
Dashboard用于展示最新货币对市场价格与昨天的fixing作对比。通过intraday.csv获取最新tick，daily.csv获取昨天的 fixing，计算 pips 变化与涨跌幅，实时更新界面。
按`Refresh Dashboard` 会刷新数据表格，计算并更新所有货币对的最新价格
内容包含：
* Pair
* 最新实时价格`Last Price` (from intraday.csv)
* 昨天的Fixing`Prev Fixing`
* Pips Change`Δ in pips` (intraday - fixing)
  * Metals: ×10
  * JPY pairs: ×100
  * Non-JPY: ×10000
* 涨跌幅`%Δ`
* Bid / Ask（如果其他API提供Bid/Ask价格可以加入该column）

---

## **TAB 3 — History & Vol**
本页面主要展示某一货币对的历史价格走势、技术指标（TA），以及实现波动率（Realized Vol）。 用户可以从下拉菜单选择货币对，并通过两个按钮生成图表：
* Plot Price + Vol + TA
* Vol Surface (Realized)

1.`Plot Price + Vol + TA`生成四个图：
* 现货价格 + MA20/MA60 + Bollinger Bands
* 短端实现波动率（RV_30/60/90）从 volatility.csv 读取
* MACD（12, 26, 9）
  * MACD = EMA(12) – EMA(26)
  * Signal = EMA(9)
  * Histogram = MACD – Signal
* RSI（Wilder’s RSI 14）
  * avg_gain = EMA(gain, α = 1/14)
  * avg_loss = EMA(loss, α = 1/14)
  * RSI = 100 - (100 / (1 + RS))
2. `Vol Surface (Realized)`用于展示和对比不同tenor的实现波动率的变化

---
## **TAB 4 — Correlation**
该页面用于计算不同外汇货币对之间的相关性，包括：两两货币对之间30/60/90天的Rolling Correlation和所有货币对的Correlation Heatmap。
数据来自daily.csv，如果没有点击`Fetch 5Y History` / `Daily Fixing Update`，则所有图表均无法显示。

---

## 🔍 Considered Data Sources

| Provider                             | 优点                                | 缺点               |
| ------------------------------------ | --------------------------------- | ---------------- |
| **Oanda**                            | 有 FX 汇率                           | 收费    |
| **Yahoo Finance**                    | 免费                                | FX 数据不够精确，偏差大    |
| **AlphaVantage**                     | 免费                                | 频率低（每分钟限制）       |
| **TwelveData**                           | 免费                               | FX 更新频率低          |
| **银行直连 API**（Citi, JPM, BOCHK）       | 真实报价                           | **交易数据不对个人开放，仅retail price，除非花钱买license** |
| **Apilayer Exchange Rates Data API** | ✔ 真实汇率与 Bloomberg 对标差距较小✔ 免费层可用 ✔ 支持172种货币 & 贵金属 ✔ 免费额度高（100条/天），更新频率相对较快（15min/次） | 贵金属没有XPTUSD报价，货币对都要USD Base，花钱才能高频    |

---

# 🧭 Workflow
1. **Load Daily 数据**
2. **Run Intraday Snapshot** 获取实时数据
3. 查看 **Dashboard** 判断市场变化
4. 查看 **Heatmap** 判断波动率 regime
5. 根据需要做 hedge或delta 调整 


