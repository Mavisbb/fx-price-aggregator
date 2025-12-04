import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

import main as backend

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


class FXApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FX Aggregator Dashboard")
        self.geometry("1100x750")

        # 读取 config，一次性
        self.cfg = backend.load_config()
        self.pair_names, _ = backend._get_pairs_and_symbols(self.cfg)

        # Ask API key
        self.api_key = simpledialog.askstring(
            "API Key",
            "Enter your ExchangeRatesData API key:",
            show="*"
        )
        if not self.api_key:
            messagebox.showerror("Error", "API key is required.")
            self.destroy()
            return

        self._build_ui()

    def log(self, msg: str):
        if hasattr(self, "log_text"):
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
        print(msg)

    # ==========================================
    #         集中数据入口：daily / vol / returns
    # ==========================================
    def _load_daily_df(self):
        path = DATA_DIR / "daily.csv"
        if not path.exists():
            messagebox.showwarning("Warning", "daily.csv not found. Run data tab first.")
            return None

        df = pd.read_csv(path)
        if "date" not in df.columns:
            messagebox.showerror("Error", "daily.csv missing 'date' column.")
            return None

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").set_index("date")

        # 去掉 unnamed
        bad = [c for c in df.columns if c.lower().startswith("unnamed")]
        if bad:
            df = df.drop(columns=bad)

        # 只保留 config 里的 pairs（防止 XPTUSD 等残留）
        keep_cols = [c for c in df.columns if c in self.pair_names]
        df = df[keep_cols]

        return df

    def _load_vol_df(self):
        path = DATA_DIR / "volatility.csv"
        if not path.exists():
            return None

        df = pd.read_csv(path, parse_dates=["date"])
        if "pair" not in df.columns:
            return None

        df = df[df["pair"].isin(self.pair_names)]
        df = df.sort_values(["date", "pair"])
        return df

    def _load_returns(self):
        df = self._load_daily_df()
        if df is None:
            return None
        rets = np.log(df / df.shift(1))
        return rets.dropna(how="all")

    # ==========================================
    #                  UI 总框架
    # ==========================================
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_data = ttk.Frame(notebook)
        self.tab_dashboard = ttk.Frame(notebook)
        self.tab_history = ttk.Frame(notebook)
        self.tab_corr = ttk.Frame(notebook)

        notebook.add(self.tab_data, text="Data")
        notebook.add(self.tab_dashboard, text="Dashboard")
        notebook.add(self.tab_history, text="History & Vol")
        notebook.add(self.tab_corr, text="Correlation")

        self._build_tab_data()
        self._build_tab_dashboard()
        self._build_tab_history()
        self._build_tab_corr()

    # ==========================================
    #              TAB 1: DATA
    # ==========================================
    def _build_tab_data(self):
        frame = ttk.Frame(self.tab_data)
        frame.pack(side=tk.TOP, fill=tk.X, pady=10)

        ttk.Button(frame, text="1. Fetch 5Y History",
                   command=self.on_fetch_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="2. Daily Fixing Update",
                   command=self.on_daily_fix).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="3. Intraday Snapshot",
                   command=self.on_intraday).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame, text="4. Recompute Vol",
                   command=self.on_recompute_vol).pack(side=tk.LEFT, padx=5)

        self.log_text = tk.Text(self.tab_data, height=25)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def on_fetch_history(self):
        try:
            backend.fetch_full_history(self.api_key, logger=self.log)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_daily_fix(self):
        try:
            backend.update_daily_fixing(self.api_key, logger=self.log)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_intraday(self):
        try:
            backend.update_intraday_snapshot(self.api_key, logger=self.log)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_recompute_vol(self):
        try:
            backend.compute_volatility(logger=self.log)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ==========================================
    #              TAB 2: DASHBOARD
    # ==========================================
    def _build_tab_dashboard(self):
        frame = ttk.Frame(self.tab_dashboard)
        frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        ttk.Button(frame, text="Refresh Dashboard",
                   command=self.refresh_dashboard).pack(side=tk.LEFT, padx=5)

        self.table = ttk.Treeview(
            self.tab_dashboard,
            columns=("pair", "last", "prev", "chg", "chg_pct"),
            show="headings",
            height=25,
        )
        for col, txt, width in [
            ("pair", "Pair", 80),
            ("last", "Last price", 100),
            ("prev", "Prev fixing", 100),
            ("chg", "Δ in pips", 80),
            ("chg_pct", "%Δ", 80),
        ]:
            self.table.heading(col, text=txt)
            self.table.column(col, width=width, anchor=tk.CENTER)

        self.table.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _load_latest_intraday(self):
        path = DATA_DIR / "intraday.csv"

        if not path.exists():
            messagebox.showwarning("Warning", "intraday.csv not found. Run Intraday Snapshot first.")
            return None

        df = pd.read_csv(path)

        # Required columns
        if not {"ts", "pair", "price"}.issubset(df.columns):
            messagebox.showerror("Error", "intraday.csv missing required columns.")
            return None

        # Convert timestamp 
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.dropna(subset=["ts"])

        # Keep the latest tick per pair
        df = df.sort_values("ts").groupby("pair").tail(1)
        df = df.set_index("pair")

        return df
    
    def _compute_pips(self, pair, change):
        pair = pair.upper()

        # Metals
        if pair.startswith("XAU") or pair.startswith("XAG"):
            return change * 10   
        # JPY pairs 
        if pair.endswith("JPY"):
            return change * 100
        # All others
        return change * 10000


    def refresh_dashboard(self):
        df_daily = self._load_daily_df()
        df_intr = self._load_latest_intraday()

        if df_daily is None or df_daily.empty:
            messagebox.showerror("Error", "daily.csv missing or empty.")
            return

        if df_intr is None or df_intr.empty:
            messagebox.showerror("Error", "intraday.csv missing or empty.")
            return

        # 清空表格
        for row in self.table.get_children():
            self.table.delete(row)

        # 跟昨天fixing来对比
        if len(df_daily) >= 2:
            prev_fix = df_daily.iloc[-2]
        else:
            prev_fix = df_daily.iloc[-1]

        for pair in df_daily.columns:
            if pair not in df_intr.index:
                continue

            last_price = df_intr.loc[pair, "price"]
            fix_price = prev_fix[pair]

            if pd.isna(fix_price):
                continue

            change = last_price - fix_price
            pip_change = self._compute_pips(pair, change)
            pct_change = (change / fix_price) * 100 if fix_price != 0 else 0

            self.table.insert(
                "",
                tk.END,
                values=(
                    pair,
                    f"{last_price:.6f}",
                    f"{fix_price:.6f}",
                    f"{pip_change:.1f}",
                    f"{pct_change:.2f}%"
                ),
            )

    # ==========================================
    #           TAB 3: HISTORY & VOL
    # ==========================================
    def _build_tab_history(self):
        frame = ttk.Frame(self.tab_history)
        frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        ttk.Label(frame, text="Pair:").pack(side=tk.LEFT, padx=5)

        self.hist_pair = tk.StringVar()
        self.hist_combo = ttk.Combobox(
            frame, textvariable=self.hist_pair, state="readonly", width=14
        )
        self.hist_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            frame,
            text="Plot Price + Vol + TA",
            command=self.plot_history_and_indicators
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(
            frame,
            text="Vol Surface (Realized)",
            command=self.plot_vol_surface
        ).pack(side=tk.LEFT, padx=10)

        self.hist_combo["values"] = self.pair_names
        if self.pair_names:
            self.hist_combo.current(0)

        ttk.Label(
            self.tab_history,
            text="Top: Price + MA20/60 + Bollinger\nThen: Realized Vol (RV_30/60/90), MACD, RSI",
            foreground="gray",
            justify="left",
        ).pack(anchor="w", padx=5)

    # --------- Technical Indicators -----------
    @staticmethod # Bollinger Bands
    def _compute_bollinger(px, window=20, num_std=2):
        ma = px.rolling(window).mean()
        std = px.rolling(window).std()
        lower = ma - num_std * std
        upper = ma + num_std * std
        return ma, upper, lower

    @staticmethod # MACD
    def _compute_macd(px, fast=12, slow=26, signal=9):
        ema_fast = px.ewm(span=fast, adjust=False).mean()
        ema_slow = px.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - signal_line
        return macd, signal_line, hist

    @staticmethod # Wilder's RSI
    def _compute_rsi(px, window=14):
        delta = px.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def plot_history_and_indicators(self):
        pair = self.hist_pair.get()
        df = self._load_daily_df()
        if not pair or df is None or pair not in df.columns:
            messagebox.showerror("Error", "Pair not found or no data.")
            return

        px = df[pair].dropna()
        if px.empty:
            messagebox.showwarning("Warning", "No price data for this pair.")
            return

        # === Technical indicators ===
        ma20, bb_up, bb_low = self._compute_bollinger(px, window=20, num_std=2)
        ma60 = px.rolling(60).mean()
        macd, macd_sig, macd_hist = self._compute_macd(px)
        rsi = self._compute_rsi(px)

        # === Realized Vol ===
        vol_df = self._load_vol_df()
        rv_sub = None
        if vol_df is not None:
            v = vol_df[vol_df["pair"] == pair].copy()
            if not v.empty:
                v = v.set_index("date").sort_index()
                cols = [c for c in ["rv_30", "rv_60", "rv_90"] if c in v.columns]
                if cols:
                    rv_sub = v[cols].reindex(px.index)

        # ==== Plot: 4x1 subplots ====
        fig, axes = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
        ax_price, ax_rv, ax_macd, ax_rsi = axes

        # 1) Price + MA + Bollinger
        ax_price.plot(px.index, px.values, label=f"{pair} Price", linewidth=1.2)
        ax_price.plot(ma20.index, ma20.values, "--", label="MA20")
        ax_price.plot(ma60.index, ma60.values, ":", label="MA60")

        ax_price.fill_between(px.index, bb_low, bb_up, color="lightgray", alpha=0.4, label="Bollinger(20,2)")
        ax_price.set_ylabel("Price")
        ax_price.set_title(f"{pair} – Price, MA & Bollinger")
        ax_price.grid(True)
        ax_price.legend(loc="upper left")

        # 2) Realized Vol
        if rv_sub is not None:
            for c in rv_sub.columns:
                ax_rv.plot(rv_sub.index, rv_sub[c], label=c)
            ax_rv.set_ylabel("Realized Vol")
            ax_rv.set_title("Realized Volatility (RV_30 / RV_60 / RV_90)")
            ax_rv.legend(loc="upper left")
        else:
            ax_rv.text(0.5, 0.5, "No RV data", ha="center", va="center", transform=ax_rv.transAxes)
            ax_rv.set_title("Realized Volatility")
        ax_rv.grid(True)

        # 3) MACD
        ax_macd.plot(macd.index, macd.values, label="MACD", linewidth=1.0)
        ax_macd.plot(macd_sig.index, macd_sig.values, label="Signal", linewidth=1.0)
        ax_macd.bar(macd_hist.index, macd_hist.values, label="Hist", alpha=0.4)
        ax_macd.axhline(0, color="black", linewidth=0.8)
        ax_macd.set_ylabel("MACD")
        ax_macd.set_title("MACD (12,26,9)")
        ax_macd.legend(loc="upper left")
        ax_macd.grid(True)

        # 4) RSI
        ax_rsi.plot(rsi.index, rsi.values, label="RSI(14)", linewidth=1.0)
        ax_rsi.axhline(70, color="red", linestyle="--", linewidth=0.8)
        ax_rsi.axhline(30, color="green", linestyle="--", linewidth=0.8)
        ax_rsi.set_ylabel("RSI")
        ax_rsi.set_title("RSI (14)")
        ax_rsi.set_ylim(0, 100)
        ax_rsi.grid(True)
        ax_rsi.legend(loc="upper left")

        plt.tight_layout()
        plt.show()

    def plot_vol_surface(self):
        pair = self.hist_pair.get()
        if not pair:
            return

        vol_df = self._load_vol_df()
        if vol_df is None:
            messagebox.showerror("Error", "volatility.csv not found.")
            return

        df = vol_df[vol_df["pair"] == pair].copy()
        if df.empty:
            messagebox.showwarning("Warning", f"No volatility data for {pair}.")
            return

        df = df.sort_values("date")
        mats = [c for c in ["rv_30", "rv_60", "rv_90", "rv_180", "rv_250"] if c in df.columns]
        if not mats:
            messagebox.showwarning("Warning", "No RV columns found.")
            return
        
        df_surf = df.set_index("date")[mats]
        df_surf.index = df_surf.index.strftime("%Y%m%d")
        
        if df_surf.dropna(how="all").empty:
            messagebox.showerror("Error", "Realized vol surface is empty.")
            return

        plt.figure(figsize=(10, 6))
        sns.heatmap(df_surf.T, cmap="coolwarm")
        plt.title(f"{pair} – Realized Volatility Surface")
        plt.xlabel("Date")
        plt.xticks(rotation = 45, ha = "right")
        plt.ylabel("Window")
        plt.tight_layout()
        plt.show()

    # ==========================================
    #              TAB 4: CORRELATION
    # ==========================================
    def _build_tab_corr(self):
        frame = ttk.Frame(self.tab_corr)
        frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        ttk.Label(frame, text="Pair A:").pack(side=tk.LEFT, padx=5)
        self.corr_a = tk.StringVar()
        self.corr_a_combo = ttk.Combobox(frame, textvariable=self.corr_a, width=12)
        self.corr_a_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(frame, text="Pair B:").pack(side=tk.LEFT, padx=5)
        self.corr_b = tk.StringVar()
        self.corr_b_combo = ttk.Combobox(frame, textvariable=self.corr_b, width=12)
        self.corr_b_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(frame, text="Window:").pack(side=tk.LEFT, padx=5)
        self.corr_win = tk.StringVar(value="60")
        ttk.Combobox(
            frame, textvariable=self.corr_win, state="readonly",
            width=5, values=["30", "60", "90"]
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="Rolling Corr", command=self.plot_corr).pack(side=tk.LEFT, padx=10)
        ttk.Button(frame, text="Heatmap", command=self.plot_corr_heatmap).pack(side=tk.LEFT, padx=10)

        # 初始值
        self.corr_a_combo["values"] = self.pair_names
        self.corr_b_combo["values"] = self.pair_names
        if self.pair_names:
            self.corr_a_combo.current(0)
            if len(self.pair_names) > 1:
                self.corr_b_combo.current(1)

    def plot_corr(self):
        a = self.corr_a.get()
        b = self.corr_b.get()
        if not a or not b or a == b:
            messagebox.showwarning("Warning", "Select two different pairs.")
            return

        rets = self._load_returns()
        if rets is None or a not in rets.columns or b not in rets.columns:
            messagebox.showerror("Error", "No return data.")
            return

        win = int(self.corr_win.get())
        series = rets[a].rolling(win).corr(rets[b]).dropna()

        if series.empty:
            messagebox.showwarning("Warning", "Not enough data for rolling correlation.")
            return

        plt.figure(figsize=(10, 4))
        plt.plot(series.index, series.values)
        plt.title(f"{win}D Rolling Corr: {a} vs {b}")
        plt.grid(True)
        plt.tight_layout()
        plt.show()

    def plot_corr_heatmap(self):
        rets = self._load_returns()
        if rets is None:
            return

        corr = rets.corr()
        plt.figure(figsize=(11, 9))
        sns.heatmap(corr, cmap="coolwarm", square=True, annot=True,
                    linewidths=0.4)
        plt.title("Correlation Heatmap (Daily Log Returns)")
        plt.tight_layout()
        plt.show()


def main():
    app = FXApp()
    if app.winfo_exists():
        app.mainloop()


if __name__ == "__main__":
    main()
