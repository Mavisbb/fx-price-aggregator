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

## **TAB 2 — Dashboard **
显示：
* Pair
* 最新实时价格`Last Price` (from intraday.csv)
* 昨天的Fixing`Prev Fixing`
* Pips Change`Δ in pips` (intraday - fixing)
  * Metals: ×10
  * JPY pairs: ×100
  * Non-JPY: ×10000
* 涨跌幅`%Δ`
* Bid / Ask（如果其他API提供Bid/Ask价格可以加入该column）

按`Refresh Dashboard` 会刷新数据表格，计算并更新所有货币对的最新行情

---

## **TAB 3 — FX Dashboard（交易视图）**


---

## **TAB 4 — Realized Volatility Heatmap**


---

# 🧠 Core Logic (from `main.py`)

## 1. `def _get_pairs_and_symbols(cfg)`

**Purpose:**
从 `config.yaml` 生成：

* 所有货币对名称列表
* API 所需的 symbol 列表

**规则：**

```python
invert=False  → 使用 quote  (如 USDHKD → HKD)
invert=True   → 使用 base   (如 AUDUSD → AUD)
```

**Example:**

```python
cfg = {
  "pairs": [
      {"name": "USDHKD", "base": "USD", "quote": "HKD", "invert": False},
      {"name": "AUDUSD", "base": "AUD", "quote": "USD", "invert": True},
  ]
}

pairs, symbols = _get_pairs_and_symbols(cfg)
# pairs   → ["USDHKD", "AUDUSD"]
# symbols → ["HKD", "AUD"]
```

👉 **意义**：
API 只能根据单一 symbol 请求，例如 “HKD/USD”，而 FX 市场有的是 quote-based，有的是 base-based，因此必须在这里统一映射。

---

## 2. `def _map_symbols_to_pairs_frame(df_sym, cfg, logger=None)`

API 返回：

```
{
  "rates": {
      "HKD": 7.81,
      "JPY": 151.20,
      "AUD": 1.52,
      ...
  }
}
```

但 GUI 和 Dashboard 需要的是 **pair-level prices**，例如：

* `USDHKD = 7.81`
* `AUDUSD = 1 / 1.52 = 0.6579`

此函数：

1. 根据 `invert` 决定是否对价格取倒数
2. 按货币对名称构建统一的 DataFrame
3. 作为 intraday.csv or dashboard 数据源

**Effectively:**
👉 把 “API symbol → 真正的 pair price” 做标准化。

---

## ### 3. Technical Indicators

来自 `main.py`：

### **Bollinger Bands**

```python
ma = px.rolling(window).mean()
std = px.rolling(window).std()
upper = ma + num_std * std
lower = ma - num_std * std
```

### **MACD**

* 快速 EMA（12）
* 慢速 EMA（26）
* signal（9）

### **Wilder's RSI (14-day)**

* Gain = positive diff
* Loss = negative diff
* 计算 RS → RSI

👉 三个指标用于 **dashboard 分析 FX momentum & volatility**。

---

# 🖥 GUI Overview (`gui.py`)

GUI 分为四个主要 Tab，每个对应交易员日常需要的一个操作面板。

---

## **TAB 1 — Data：Intraday Snapshot（实时数据抓取）**

用途：

* 从 API 抓取最新价格
* 写入 `intraday.csv`
* 自动清洗并格式化为统一结构

好处：
✔ 跟 Bloomberg 类似的实时性
✔ 每 120 秒自动刷新
✔ 可以用于 Dashboard 的最新价格更新

---

## **TAB 2 — Daily Loader（历史数据清洗）**

逻辑：

* 读取 `daily.csv`
* 格式化日期，并按时间排序
* 自动删除 Unnamed 列
* **只保留 config.yaml 中的 pairs**（避免历史文件污染）

用途：

✔ 用于绘制指标图
✔ 用于 realized volatility heatmap
✔ 保持历史数据干净规范

---

## **TAB 3 — FX Dashboard（交易视图）**

显示：
* Pair
* Last price refreshed (from intraday.csv)
* Previous' fixing
* Pips Change (fixing - intraday)
  * Metals: ×10
  * JPY pairs: ×100
  * Non-JPY: ×10000
* % Change
* Bid / Ask（如果其他API可以有Bid/Ask价格可以加入该column）

---

## **TAB 4 — Realized Volatility Heatmap**

支持周期： RV 30/60/90/180/250

用途：
✔ 比较不同时间窗口的波动率
✔ 识别高波动 / 低波动 regime
✔ 与 implied vol 做交叉检验
用 30/60/90 来画历史图,Vol Surface 使用 30/60/90/180/250
---

# 🌐 Choosing the Best Data Source（API 选型解释）

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
# ▶️ Running the App
```bash
python main.py
```
---

# 🧭 Example Workflow

1. **Load Daily 数据**
2. **Run Intraday Snapshot** 获取实时数据
3. 查看 **Dashboard** 判断市场变化
4. 查看 **Heatmap** 判断波动率 regime
5. 根据需要做 hedge / delta 调整 / 入场

---

# 📌 Future Plans

* Websocket real-time feeds
* Forward Points Aggregator
* Multi-bank quote comparison
* SQLite tick database
* Implied Vol surface building

---

