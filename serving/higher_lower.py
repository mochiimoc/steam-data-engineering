import streamlit as st
import duckdb
import pandas as pd
import random
from pathlib import Path

OWNERS_LOW_MIN = 20_000
DB_PATH = Path(__file__).parent.parent / "data" / "gold" / "steam.duckdb"

QUERY = """
SELECT
    g.game_id AS appid,
    g.name,
    f.owners_low,
    f.owners_high
FROM dim_game g
JOIN fact_game_snapshot f ON g.game_id = f.game_id
WHERE f.owners_high > 0 AND f.owners_low >= {min_owners}
QUALIFY row_number() OVER (PARTITION BY g.game_id ORDER BY f.date_id DESC) = 1
""".format(min_owners=OWNERS_LOW_MIN)


@st.cache_data
def load_games() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(QUERY).df()
    con.close()
    return df.reset_index(drop=True)


def fmt_owners(low: int, high: int) -> str:
    mid = (low + high) / 2
    if mid >= 1_000_000:
        return f"{mid/1_000_000:.1f}M sahip"
    if mid >= 1_000:
        return f"{mid/1_000:.0f}K sahip"
    return f"{mid:.0f} sahip"


def pick_random(df: pd.DataFrame, exclude_appid: int | None = None) -> dict:
    pool = df if exclude_appid is None else df[df["appid"] != exclude_appid]
    row = pool.sample(1).iloc[0]
    return row.to_dict()


def compare(challenger: dict, anchor: dict) -> str:
    """Return the correct answer: 'Daha fazla', 'Daha az', or 'Eşit'."""
    if challenger["owners_low"] == anchor["owners_low"]:
        return "Eşit"
    return "Daha fazla" if challenger["owners_low"] > anchor["owners_low"] else "Daha az"


def game_card(game: dict, reveal: bool = False) -> None:
    appid = int(game["appid"])
    img_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
    try:
        st.image(img_url, use_container_width=True)
    except Exception:
        pass
    st.markdown(f"### {game['name']}")
    if reveal:
        st.markdown(f"**{fmt_owners(game['owners_low'], game['owners_high'])}**")
    else:
        st.markdown("**? sahip**")


# ── init state ─────────────────────────────────────────────────────────────
def init():
    df = load_games()
    anchor = pick_random(df)
    challenger = pick_random(df, exclude_appid=anchor["appid"])
    st.session_state.update(
        df=df,
        anchor=anchor,
        challenger=challenger,
        score=0,
        reveal=False,
        last_correct=None,
        game_over=False,
    )


if "anchor" not in st.session_state:
    init()

# ── layout ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Steam Higher/Lower", layout="wide")
st.title("Steam Higher / Lower")
st.markdown(f"**Seri: {st.session_state.score}**")

if st.session_state.game_over:
    st.error(f"Oyun bitti! Skorun: **{st.session_state.score}**")
    if st.button("Yeniden Başla"):
        init()
        st.rerun()
    st.stop()

col_anchor, col_vs, col_challenger = st.columns([5, 1, 5])

with col_anchor:
    st.subheader("Çapa")
    game_card(st.session_state.anchor, reveal=True)

with col_vs:
    st.markdown("<br><br><br><br><h2 style='text-align:center'>VS</h2>", unsafe_allow_html=True)

with col_challenger:
    st.subheader("Rakip")
    game_card(st.session_state.challenger, reveal=st.session_state.reveal)

# ── reveal phase ─────────────────────────────────────────────────────────────
if st.session_state.reveal:
    correct = compare(st.session_state.challenger, st.session_state.anchor)
    chosen = st.session_state.last_correct  # user's answer stored here temporarily
    if chosen == correct:
        st.success(f"Doğru! Cevap: **{correct}**  +1")
    else:
        st.error(f"Yanlış! Doğru cevap: **{correct}**")
        st.session_state.game_over = True

    if not st.session_state.game_over:
        if st.button("Devam →"):
            # challenger becomes new anchor
            new_anchor = st.session_state.challenger
            new_challenger = pick_random(st.session_state.df, exclude_appid=new_anchor["appid"])
            st.session_state.anchor = new_anchor
            st.session_state.challenger = new_challenger
            st.session_state.reveal = False
            st.session_state.last_correct = None
            st.rerun()
    else:
        if st.button("Yeniden Başla"):
            init()
            st.rerun()

else:
    st.markdown("---")
    st.markdown("**Rakip oyun çapaya göre ne kadar sattı?**")
    bcol1, bcol2, bcol3 = st.columns(3)
    with bcol1:
        if st.button("⬆ Daha fazla", use_container_width=True):
            st.session_state.last_correct = "Daha fazla"
            correct = compare(st.session_state.challenger, st.session_state.anchor)
            if "Daha fazla" == correct:
                st.session_state.score += 1
            st.session_state.reveal = True
            st.rerun()
    with bcol2:
        if st.button("⬇ Daha az", use_container_width=True):
            st.session_state.last_correct = "Daha az"
            correct = compare(st.session_state.challenger, st.session_state.anchor)
            if "Daha az" == correct:
                st.session_state.score += 1
            st.session_state.reveal = True
            st.rerun()
    with bcol3:
        if st.button("= Eşit", use_container_width=True):
            st.session_state.last_correct = "Eşit"
            correct = compare(st.session_state.challenger, st.session_state.anchor)
            if "Eşit" == correct:
                st.session_state.score += 1
            st.session_state.reveal = True
            st.rerun()
