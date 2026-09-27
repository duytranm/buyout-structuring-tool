import altair as alt
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Buyout Buddy",
    page_icon=":material/handshake:",
    layout="wide",
)

# Yahoo Finance ticker suffix per exchange (used when the typed symbol has no "." already).
EXCHANGES = {
    "US / primary listing — no suffix": "",
    "London Stock Exchange (UK)": ".L",
    "Euronext Paris (France)": ".PA",
    "Euronext Amsterdam (Netherlands)": ".AS",
    "Deutsche Börse Xetra (Germany)": ".DE",
    "SIX Swiss Exchange (Switzerland)": ".SW",
    "Borsa Italiana (Italy)": ".MI",
    "Bolsa de Madrid (Spain)": ".MC",
    "Toronto Stock Exchange (Canada)": ".TO",
    "Australian Securities Exchange": ".AX",
    "Tokyo Stock Exchange (Japan)": ".T",
    "Hong Kong Stock Exchange": ".HK",
    "Shanghai Stock Exchange (China)": ".SS",
    "Shenzhen Stock Exchange (China)": ".SZ",
    "National Stock Exchange (India)": ".NS",
    "Bombay Stock Exchange (India)": ".BO",
    "Korea Exchange (South Korea)": ".KS",
    "Singapore Exchange": ".SI",
    "B3 (Brazil)": ".SA",
    "Bolsa Mexicana de Valores (Mexico)": ".MX",
}

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "HKD": "HK$",
    "CAD": "C$", "AUD": "A$", "CHF": "CHF ", "INR": "₹", "KRW": "₩", "BRL": "R$",
    "MXN": "MX$", "SGD": "S$", "SEK": "kr ", "NOK": "kr ", "ZAR": "R",
}

# Some exchanges quote in minor units (pence/cents) even though the reported currency
# code implies the major unit — normalize those to the major unit here.
MINOR_UNIT_CURRENCIES = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100)}


def money_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def fmt_billions(value: float, code: str) -> str:
    return f"{money_symbol(code)}{value / 1e9:,.2f}B"


def fmt_price(value: float, code: str) -> str:
    return f"{money_symbol(code)}{value:,.2f}"


@st.cache_data(ttl="1h", show_spinner="Fetching market data...")
def get_snapshot(ticker: str) -> dict | None:
    """Fetch price, share count, net income, and currency for a ticker."""
    ticker = ticker.strip().upper()
    if not ticker:
        return None
    info = yf.Ticker(ticker).info
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    shares = info.get("sharesOutstanding")
    if not price or not shares:
        return None
    currency = info.get("currency") or "USD"
    if currency in MINOR_UNIT_CURRENCIES:
        major_currency, divisor = MINOR_UNIT_CURRENCIES[currency]
        price = price / divisor
        currency = major_currency
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": float(price),
        "shares": float(shares),
        "net_income": float(info.get("netIncomeToCommon") or 0.0),
        "currency": currency,
    }


@st.cache_data(ttl="1h", show_spinner=False)
def get_fx_rate(from_ccy: str, to_ccy: str) -> float | None:
    """Latest close for the from_ccy -> to_ccy exchange rate."""
    if from_ccy == to_ccy:
        return 1.0
    try:
        hist = yf.Ticker(f"{from_ccy}{to_ccy}=X").history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def company_inputs(label: str, default_ticker: str, key_prefix: str) -> dict:
    """Render exchange + ticker input and editable snapshot fields; return current assumptions."""
    with st.container(border=True):
        st.markdown(f"**{label}**")

        e1, e2 = st.columns([1, 1])
        exchange = e1.selectbox(
            "Exchange", list(EXCHANGES.keys()), key=f"{key_prefix}_exchange"
        )
        raw_ticker = e2.text_input(
            "Ticker symbol", value=default_ticker, key=f"{key_prefix}_ticker"
        ).strip().upper()

        suffix = EXCHANGES[exchange]
        query_ticker = raw_ticker if (not suffix or "." in raw_ticker) else f"{raw_ticker}{suffix}"

        snapshot = get_snapshot(query_ticker) if query_ticker else None
        if query_ticker and snapshot is None:
            st.error(f"Couldn't fetch data for \"{query_ticker}\". Enter figures manually below.")

        name = snapshot["name"] if snapshot else query_ticker or "—"
        st.caption(f"{name} · Yahoo Finance symbol: {query_ticker or '—'}")

        # Suffix widget keys with the resolved symbol so switching companies re-seeds these
        # fields from the new snapshot instead of keeping the previous ticker's edited values.
        field_key = f"{key_prefix}_{query_ticker or 'manual'}"

        c1, c2 = st.columns(2)
        currency = c1.text_input(
            "Currency",
            value=snapshot["currency"] if snapshot else "USD",
            max_chars=3,
            key=f"{field_key}_currency",
        ).strip().upper()
        price = c2.number_input(
            f"Share price ({currency})",
            min_value=0.01,
            value=round(snapshot["price"], 2) if snapshot else 50.00,
            step=0.5,
            key=f"{field_key}_price",
        )
        shares = st.number_input(
            "Shares outstanding",
            min_value=1.0,
            value=float(snapshot["shares"]) if snapshot else 1_000_000_000.0,
            step=1_000_000.0,
            format="%.0f",
            key=f"{field_key}_shares",
        )
        net_income = st.number_input(
            f"Trailing net income ({currency})",
            value=float(snapshot["net_income"]) if snapshot else 0.0,
            step=10_000_000.0,
            format="%.0f",
            key=f"{field_key}_net_income",
            help="Used only for the simplified accretion / dilution estimate below.",
        )

        market_cap = price * shares
        st.metric("Market cap", fmt_billions(market_cap, currency))

    return {
        "ticker": raw_ticker or key_prefix,
        "name": name,
        "price": price,
        "shares": shares,
        "net_income": net_income,
        "currency": currency or "USD",
    }


st.title(":material/handshake: Buyout Buddy")
st.caption(
    "Model the cash / stock mix of an acquisition and see the resulting deal value, "
    "exchange ratio, pro forma ownership, and a simplified accretion / dilution estimate. "
    "Pick a listing exchange for each company to pull tickers from international markets."
)

col1, col2 = st.columns(2)
with col1:
    acquirer = company_inputs("Acquirer", "MSFT", "acq")
with col2:
    target = company_inputs("Target", "ADBE", "tgt")

deal_currency = acquirer["currency"]

if target["currency"] != deal_currency:
    with st.container(border=True):
        st.markdown(
            f"**Currency conversion** — the deal is modeled in {deal_currency} "
            f"(the acquirer's currency); {target['ticker']} trades in {target['currency']}."
        )
        fetched_rate = get_fx_rate(target["currency"], deal_currency)
        fx1, fx2 = st.columns(2)
        fx_rate = fx1.number_input(
            f"Exchange rate: 1 {target['currency']} = ? {deal_currency}",
            min_value=0.0001,
            value=float(fetched_rate) if fetched_rate else 1.0,
            step=0.0001,
            format="%.4f",
        )
        if fetched_rate is None:
            fx1.caption("Couldn't fetch a live rate — enter it manually.")
        fx2.metric(
            f"{target['ticker']} price in {deal_currency}",
            fmt_price(target["price"] * fx_rate, deal_currency),
        )
    target_price = target["price"] * fx_rate
    target_net_income = target["net_income"] * fx_rate
else:
    target_price = target["price"]
    target_net_income = target["net_income"]

st.divider()
st.subheader("Deal terms")

with st.container(border=True):
    t1, t2 = st.columns(2)
    offer_price = t1.number_input(
        f"Offer price per target share ({deal_currency})",
        min_value=0.01,
        value=round(target_price * 1.30, 2),
        step=0.5,
    )
    implied_premium = offer_price / target_price - 1
    t2.metric("Implied premium over current price", f"{implied_premium:+.1%}")

    stake_pct = st.slider(
        "Stake to acquire (% of target shares)",
        min_value=1,
        max_value=100,
        value=100,
        format="%d%%",
        help="Less than 100% models a partial / controlling-stake purchase instead of a full buyout.",
    )
    acquired_shares = target["shares"] * stake_pct / 100
    if stake_pct < 100:
        st.caption(f"Acquiring {stake_pct}% of shares · {acquired_shares:,.0f} of {target['shares']:,.0f} shares")

    cash_pct = st.slider(
        "Consideration mix — cash vs. acquirer stock",
        min_value=0,
        max_value=100,
        value=50,
        format="%d%% cash",
    )
    stock_pct = 100 - cash_pct
    st.caption(f"{cash_pct}% cash · {stock_pct}% stock")

cash_per_share = offer_price * cash_pct / 100
stock_value_per_share = offer_price * stock_pct / 100
exchange_ratio = stock_value_per_share / acquirer["price"] if acquirer["price"] else 0.0

total_deal_value = offer_price * acquired_shares
total_cash = cash_per_share * acquired_shares
total_stock_value = stock_value_per_share * acquired_shares
new_shares_issued = total_stock_value / acquirer["price"] if acquirer["price"] else 0.0
pro_forma_shares = acquirer["shares"] + new_shares_issued
target_ownership_pct = (new_shares_issued / pro_forma_shares * 100) if pro_forma_shares else 0.0
acquirer_ownership_pct = 100 - target_ownership_pct

st.subheader("Deal summary")

with st.container(horizontal=True):
    deal_value_label = "Total deal value" if stake_pct == 100 else f"Total deal value ({stake_pct}% stake)"
    st.metric(deal_value_label, fmt_billions(total_deal_value, deal_currency), border=True)
    st.metric("Cash consideration", fmt_billions(total_cash, deal_currency), border=True)
    st.metric("Stock consideration", fmt_billions(total_stock_value, deal_currency), border=True)
    st.metric(
        "Exchange ratio",
        f"{exchange_ratio:.4f}" if stock_pct else "n/a",
        help="Shares of acquirer stock issued per target share.",
        border=True,
    )
    st.metric("New acquirer shares issued", f"{new_shares_issued:,.0f}", border=True)

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    with st.container(border=True):
        st.markdown("**Consideration mix**")
        mix_df = pd.DataFrame(
            {
                "Type": ["Cash", "Stock"],
                "Value": [total_cash, total_stock_value],
            }
        )
        mix_df["Row"] = "Consideration"
        mix_chart = (
            alt.Chart(mix_df)
            .mark_bar(height=30)
            .encode(
                x=alt.X("Value:Q", title=f"Consideration ({deal_currency})", stack="normalize"),
                y=alt.Y("Row:N", title=None, axis=None, scale=alt.Scale(paddingOuter=0.7)),
                color=alt.Color("Type:N", legend=alt.Legend(title=None, orient="bottom")),
                tooltip=["Type", alt.Tooltip("Value:Q", format=",.0f")],
            )
            .properties(height=200)
        )
        st.altair_chart(mix_chart, width="stretch")

with chart_col2:
    with st.container(border=True):
        st.markdown("**Pro forma ownership**")
        own_df = pd.DataFrame(
            {
                "Holder": [f"{acquirer['ticker']} shareholders", f"{target['ticker']} shareholders"],
                "Pct": [acquirer_ownership_pct, target_ownership_pct],
            }
        )
        own_df["Row"] = "Ownership"
        own_chart = (
            alt.Chart(own_df)
            .mark_bar(height=30)
            .encode(
                x=alt.X("Pct:Q", title="Ownership of combined company (%)", stack="normalize"),
                y=alt.Y("Row:N", title=None, axis=None, scale=alt.Scale(paddingOuter=0.7)),
                color=alt.Color("Holder:N", legend=alt.Legend(title=None, orient="bottom")),
                tooltip=["Holder", alt.Tooltip("Pct:Q", format=".1f")],
            )
            .properties(height=200)
        )
        st.altair_chart(own_chart, width="stretch")

with st.expander(":material/query_stats: Accretion / dilution (simplified)"):
    st.caption(
        "Illustrative only — assumes no purchase-accounting adjustments and combines "
        "trailing net income as a rough proxy for pro forma earnings"
        + (f", including only the acquired {stake_pct}% share of target net income." if stake_pct < 100 else ".")
    )
    a1, a2, a3 = st.columns(3)
    funding = a1.segmented_control(
        "Cash funded via", ["New debt", "Existing cash"], default="New debt"
    )
    interest_rate = a2.number_input(
        "Interest rate on new debt (%)",
        min_value=0.0,
        value=5.0,
        step=0.25,
        disabled=funding != "New debt",
    )
    tax_rate = a3.number_input("Tax rate (%)", min_value=0.0, max_value=100.0, value=21.0, step=1.0)
    synergies = st.number_input(
        f"Annual after-tax synergies ({deal_currency})", value=0.0, step=10_000_000.0, format="%.0f"
    )

    after_tax_interest = (
        total_cash * (interest_rate / 100) * (1 - tax_rate / 100) if funding == "New debt" else 0.0
    )
    acquired_net_income = target_net_income * stake_pct / 100
    combined_net_income = (
        acquirer["net_income"] + acquired_net_income + synergies - after_tax_interest
    )
    standalone_eps = acquirer["net_income"] / acquirer["shares"] if acquirer["shares"] else 0.0
    pro_forma_eps = combined_net_income / pro_forma_shares if pro_forma_shares else 0.0
    accretion_dilution = (pro_forma_eps / standalone_eps - 1) if standalone_eps else 0.0

    r1, r2, r3 = st.columns(3)
    r1.metric("Standalone acquirer EPS", fmt_price(standalone_eps, deal_currency))
    r2.metric("Pro forma EPS", fmt_price(pro_forma_eps, deal_currency))
    r3.metric(
        "Accretion / (dilution)",
        f"{accretion_dilution:+.1%}",
        delta=f"{accretion_dilution:+.1%}",
    )
