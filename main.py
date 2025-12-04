import os
from pathlib import Path
from datetime import datetime, timedelta

import requests
import pandas as pd
import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DAILY_PATH = DATA_DIR / "daily.csv"
INTRADAY_PATH = DATA_DIR / "intraday.csv"
VOL_PATH = DATA_DIR / "volatility.csv"


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_config():
    cfg_path = BASE_DIR / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _log(msg: str, logger=None):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    if logger is not None:
        logger(line)


def _request_json(url: str, headers: dict, params: dict, logger=None):
    resp = requests.get(url, headers=headers, params=params, timeout=120)
    try:
        data = resp.json()
    except Exception:
        _log(f"HTTP {resp.status_code} – failed JSON: {resp.text[:300]}", logger)
        resp.raise_for_status()

    if not resp.ok or data.get("success") is False or "error" in data:
        _log(f"API error: {data}", logger)
        raise RuntimeError(f"API error: {data}")
    return data


# =========================================
#   Pairs & Symbols (统一入口)
# =========================================
def _get_pairs_and_symbols(cfg):
    pairs_cfg = cfg["pairs"]

    pair_names = [p["name"] for p in pairs_cfg]

    symbols = set()
    for p in pairs_cfg:
        base = p["base"]
        quote = p["quote"]
        invert_flag = p.get("invert", False)

        sym = base if invert_flag else quote
        symbols.add(sym)

    return pair_names, sorted(symbols)


def _map_symbols_to_pairs_frame(df_sym: pd.DataFrame, cfg, logger=None) -> pd.DataFrame:
    pairs_cfg = cfg["pairs"]
    pair_df = pd.DataFrame(index=df_sym.index)

    for p in pairs_cfg:
        pair_name = p["name"]
        base = p["base"]
        quote = p["quote"]
        invert_flag = p.get("invert", False)

        sym = base if invert_flag else quote

        if sym not in df_sym.columns:
            _log(f"Warning: symbol {sym} not in API data for pair {pair_name}", logger)
            pair_df[pair_name] = np.nan
            continue

        rates = df_sym[sym].astype(float)

        if invert_flag:
            pair_df[pair_name] = 1.0 / rates
        else:
            pair_df[pair_name] = rates

    return pair_df


# =========================================
#   1) FULL 5Y HISTORY
# =========================================
def fetch_full_history(api_key: str, logger=None):
    ensure_data_dir()
    if DAILY_PATH.exists():
        _log("daily.csv exists — skip full history.", logger)
        return

    cfg = load_config()
    base_url = cfg["api"]["base_url"]
    base_ccy = cfg["api"]["base_currency"]
    _, symbols = _get_pairs_and_symbols(cfg)
    years_back = int(cfg["history"].get("years_back", 5))

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=years_back * 365)

    _log(f"Fetch history {start_date} → {end_date}", logger)

    headers = {"apikey": api_key}
    url = f"{base_url}/timeseries"

    all_rates = {}

    cur = start_date
    while cur <= end_date:
        cur_end = min(cur + timedelta(days=364), end_date)

        params = {
            "start_date": cur.isoformat(),
            "end_date": cur_end.isoformat(),
            "base": base_ccy,
            "symbols": ",".join(symbols),
        }

        _log(f"Chunk {cur} → {cur_end}", logger)
        data = _request_json(url, headers, params, logger)

        rates_block = data.get("rates", {})
        for date_str, sym_map in rates_block.items():
            all_rates.setdefault(date_str, {}).update(sym_map)

        cur = cur_end + timedelta(days=1)

    if not all_rates:
        raise RuntimeError("No data returned from API.")

    df_sym = pd.DataFrame(all_rates).T.sort_index()
    df_sym.index = pd.to_datetime(df_sym.index)
    df_sym.index.name = "date"

    pair_df = _map_symbols_to_pairs_frame(df_sym, cfg, logger)
    pair_df.to_csv(DAILY_PATH)
    _log(f"Saved daily.csv shape {pair_df.shape}", logger)


# =========================================
#   2) DAILY FIXING
# =========================================
def update_daily_fixing(api_key: str, logger=None):
    ensure_data_dir()
    cfg = load_config()

    base_url = cfg["api"]["base_url"]
    base_ccy = cfg["api"]["base_currency"]
    _, symbols = _get_pairs_and_symbols(cfg)

    headers = {"apikey": api_key}
    url = f"{base_url}/timeseries"

    if not DAILY_PATH.exists():
        _log("Run full_history first.", logger)
        return

    df_old = pd.read_csv(DAILY_PATH, parse_dates=["date"]).set_index("date").sort_index()
    last_date = df_old.index.max().date()

    today = datetime.utcnow().date()
    start_date = last_date + timedelta(days=1)

    if start_date > today:
        _log("No new days to update.", logger)
        return

    params = {
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "base": base_ccy,
        "symbols": ",".join(symbols),
    }

    data = _request_json(url, headers, params, logger)
    rates_block = data.get("rates", {})

    if not rates_block:
        _log("No rates returned for daily fixing.", logger)
        return

    df_sym = pd.DataFrame(rates_block).T
    df_sym.index = pd.to_datetime(df_sym.index)
    df_sym.index.name = "date"
    df_sym = df_sym.sort_index()

    df_new = _map_symbols_to_pairs_frame(df_sym, cfg, logger)

    df_all = pd.concat([df_old, df_new])
    df_all = df_all[~df_all.index.duplicated(keep="last")].sort_index()
    df_all.to_csv(DAILY_PATH)

    _log(f"daily.csv updated: now {df_all.shape}", logger)


# =========================================
#   3) INTRADAY SNAPSHOT
# =========================================
def update_intraday_snapshot(api_key: str, logger=None):
    ensure_data_dir()
    cfg = load_config()

    base_url = cfg["api"]["base_url"]
    base_ccy = cfg["api"]["base_currency"]
    pairs_cfg = cfg["pairs"]
    _, symbols = _get_pairs_and_symbols(cfg)

    headers = {"apikey": api_key}
    url = f"{base_url}/latest"

    params = {"base": base_ccy, "symbols": ",".join(symbols)}
    data = _request_json(url, headers, params, logger)
    rates = data.get("rates", {})

    if not rates:
        _log(" No intraday rates returned.", logger)
        return

    ts = datetime.utcnow().isoformat(timespec="seconds")
    rows = []

    for p in pairs_cfg:
        pair_name = p["name"]
        base = p["base"]
        quote = p["quote"]
        invert_flag = p.get("invert", False)

        sym = base if invert_flag else quote
        rate = rates.get(sym)
        if rate is None:
            continue

        price = float(rate)
        if invert_flag:
            price = 1.0 / price

        rows.append({"ts": ts, "pair": pair_name, "price": price})

    df_new = pd.DataFrame(rows)

    if INTRADAY_PATH.exists():
        df_new.to_csv(INTRADAY_PATH, mode="a", index=False, header=False)
    else:
        df_new.to_csv(INTRADAY_PATH, index=False)

    _log(f"Intraday +{len(df_new)} rows written to {INTRADAY_PATH}", logger)


# =========================================
#   4) REALIZED VOL
# =========================================
def compute_volatility(logger=None):
    ensure_data_dir()
    if not DAILY_PATH.exists():
        _log("Need daily.csv first.", logger)
        return

    df = pd.read_csv(DAILY_PATH, parse_dates=["date"]).set_index("date").sort_index()

    df = df.apply(pd.to_numeric, errors="coerce")
    pairs = list(df.columns)

    rets = np.log(df / df.shift(1))

    windows = [30, 60, 90, 180, 250]
    vol_dict = {}
    for w in windows:
        vol_dict[w] = rets.rolling(w).std() * np.sqrt(252)

    rows = []

    for d in df.index:
        d_str = d.date().isoformat()
        for pair in pairs:
            rec = {"date": d_str, "pair": pair}
            for w in windows:
                rv = vol_dict[w].loc[d, pair]
                rec[f"rv_{w}"] = float(rv) if pd.notna(rv) else None
            rows.append(rec)

    out = pd.DataFrame(rows).sort_values(["date", "pair"])
    out.to_csv(VOL_PATH, index=False)
    _log(f"Saved volatility.csv {out.shape}", logger)


# =========================================
#   CLI ENTRY
# =========================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="FX Aggregator – data pipeline")
    parser.add_argument("--api-key", required=True, help="ExchangeRatesData (apilayer) API key")
    parser.add_argument(
        "--action",
        choices=["full_history", "daily_fix", "intraday", "vol"],
        required=True,
        help="Which step to run",
    )
    args = parser.parse_args()

    if args.action == "full_history":
        fetch_full_history(args.api_key)
    elif args.action == "daily_fix":
        update_daily_fixing(args.api_key)
    elif args.action == "intraday":
        update_intraday_snapshot(args.api_key)
    elif args.action == "vol":
        compute_volatility()


if __name__ == "__main__":
    main()
