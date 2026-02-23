import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import hashlib
import uuid
import random

# 페이지 설정
st.set_page_config(
    page_title="조선거상 미니",
    page_icon="🏯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# CSS (기존 유지 + 약간 정리)
st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 12px; font-size: 16px; }
    .stTextInput input, .stNumberInput input { font-size: 16px; padding: 10px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .price-same { color: #666; }
    .trade-log {
        background: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
        font-family: monospace;
        font-size: 13px;
        max-height: 180px;
        overflow-y: auto;
    }
    .trade-complete {
        color: #006d40;
        font-weight: bold;
        background: #e6f4ea;
        padding: 10px;
        border-radius: 6px;
        margin: 8px 0;
    }
    .slot-card {
        background: white;
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #e0e4e8;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
</style>
""", unsafe_allow_html=True)

# 구글 시트 연결
@st.cache_resource
def get_gsheet():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gspread"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"시트 연결 실패: {e}")
        return None

# 데이터 로드 (기존과 거의 동일)
@st.cache_data(ttl=12)
def load_data():
    doc = get_gsheet()
    if not doc:
        return None, None, None, None, None, None

    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records()}
        items = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])}
                 for r in doc.worksheet("Item_Data").get_all_records() if r.get('item_name')}
        mercs = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))}
                 for r in doc.worksheet("Balance_Data").get_all_records() if r.get('name')}

        vil_ws = doc.worksheet("Korea_Village_Data")
        headers = [h.strip() for h in vil_ws.row_values(1)]
        villages = {}
        initial_stocks = {}

        for row in vil_ws.get_all_values()[1:]:
            if not row or not row[0].strip(): continue
            name = row[0].strip()
            if name in villages: continue

            x = int(row[1]) if len(row)>1 and row[1].strip().isdigit() else 0
            y = int(row[2]) if len(row)>2 and row[2].strip().isdigit() else 0

            villages[name] = {'x':x, 'y':y, 'items':{}}
            initial_stocks[name] = {}

            if name != "용병 고용소":
                for i in range(3, len(headers)):
                    item = headers[i]
                    if item in items and len(row)>i and row[i].strip().isdigit():
                        stock = int(row[i])
                        villages[name]['items'][item] = stock
                        initial_stocks[name][item] = stock

        players = []
        for r in doc.worksheet("Player_Data").get_all_records():
            if not r.get('slot'): continue
            players.append({
                'slot': int(r['slot']),
                'money': int(r.get('money', 10000)),
                'pos': r.get('pos', '한양'),
                'inv': json.loads(r.get('inventory', '{}')),
                'mercs': json.loads(r.get('mercs', '[]')),
                'week': int(r.get('week', 1)),
                'month': int(r.get('month', 1)),
                'year': int(r.get('year', 1592)),
                'last_save': r.get('last_save', '없음')
            })

        return settings, items, mercs, villages, initial_stocks, players

    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return None, None, None, None, None, None

# 세션 초기화
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None
if 'market' not in st.session_state:
    st.session_state.market = None
if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = {}

settings, items_info, merc_data, villages, initial_stocks, slots = load_data()

if not settings:
    st.stop()

# 시장 데이터 초기화
if st.session_state.market is None:
    market = {}
    for v, data in villages.items():
        if v == "용병 고용소": continue
        market[v] = {}
        for item, stock in data['items'].items():
            market[v][item] = {'stock': stock, 'price': items_info[item]['base']}
    st.session_state.market = market

# 가격 업데이트 (재고 기반만)
def update_prices():
    min_rate = settings.get('min_price_rate', 0.4)
    max_rate = settings.get('max_price_rate', 3.0)

    for village, items in st.session_state.market.items():
        for name, data in items.items():
            base = items_info[name]['base']
            stock = data['stock']
            init = initial_stocks.get(village, {}).get(name, 100) or 100

            ratio = stock / init if init > 0 else 0

            if stock <= 0:
                factor = max_rate
            elif ratio < 0.5:
                factor = 2.5
            elif ratio < 1.0:
                factor = 1.8
            else:
                factor = 1.0

            price = int(base * factor)
            price = max(int(base * min_rate), min(price, int(base * max_rate)))
            data['price'] = price

# 무게 계산
def calc_weight():
    current = sum(q * items_info.get(i, {'w':0})['w'] for i,q in st.session_state.player['inv'].items())
    total = 200 + sum(merc_data[m]['w_bonus'] for m in st.session_state.player['mercs'])
    return current, total

# 구매/판매 처리 (간소화 버전)
def trade_item(action, item_name, qty):
    pos = st.session_state.player['pos']
    market_item = st.session_state.market[pos][item_name]
    player = st.session_state.player

    log_key = f"{action}_{pos}_{item_name}_{int(time.time()*1000)}"
    if log_key not in st.session_state.trade_logs:
        st.session_state.trade_logs[log_key] = []

    total_qty = 0
    total_money = 0

    for _ in range(qty):
        if action == "buy":
            if player['money'] < market_item['price'] or market_item['stock'] <= 0:
                break
            if calc_weight()[0] + items_info[item_name]['w'] > calc_weight()[1]:
                break
            player['money'] -= market_item['price']
            player['inv'][item_name] = player['inv'].get(item_name, 0) + 1
            market_item['stock'] -= 1
            total_qty += 1
            total_money += market_item['price']

        elif action == "sell":
            if player['inv'].get(item_name, 0) <= 0:
                break
            player['money'] += market_item['price']
            player['inv'][item_name] -= 1
            market_item['stock'] += 1
            total_qty += 1
            total_money += market_item['price']

        update_prices()  # 매 거래마다 가격 갱신

        st.session_state.trade_logs[log_key].append(
            f"{'매수' if action=='buy' else '매도'} {total_qty}/{qty} | 가격 {market_item['price']:,} | 잔액 {player['money']:,}"
        )

        if total_qty >= qty:
            break

    return total_qty, total_money, log_key

# ────────────────────────────────────────────────
# 메인 화면
# ────────────────────────────────────────────────

if not st.session_state.game_started:
    st.title("🏯 조선거상 미니")
    for p in sorted(slots, key=lambda x: x['slot']):
        with st.container():
            st.markdown(f"""
            <div class="slot-card">
                <b>슬롯 {p['slot']}</b><br>
                위치: {p['pos']}　|　소지금: {p['money']:,}냥<br>
                마지막 저장: {p['last_save']}
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"접속", key=f"enter_slot_{p['slot']}"):
                st.session_state.player = p
                st.session_state.game_started = True
                st.rerun()

else:
    player = st.session_state.player
    pos = player['pos']

    update_prices()

    st.header(f"📍 {pos}")
    col1, col2 = st.columns([3,2])
    col1.metric("💰 소지금", f"{player['money']:,}냥")
    cw, tw = calc_weight()
    col2.metric("⚖️ 무게", f"{cw}/{tw}근")

    tab_trade, tab_inv, tab_merc, tab_menu = st.tabs(["🛒 거래", "🎒 인벤", "⚔️ 용병", "⚙️ 메뉴"])

    with tab_trade:
        if pos == "용병 고용소":
            st.subheader("용병 고용소")
            for name, data in merc_data.items():
                if st.button(f"{name} 고용 ({data['price']:,}냥 | +{data['w_bonus']}근)",
                             key=f"hire_{name}"):
                    if len(player['mercs']) >= settings.get('max_mercenaries', 5):
                        st.error("최대 인원 초과")
                    elif player['money'] >= data['price']:
                        player['money'] -= data['price']
                        player['mercs'].append(name)
                        st.success(f"{name} 고용 완료!")
                        st.rerun()
                    else:
                        st.error("잔액 부족")
        else:
            st.subheader(f"{pos} 장터")
            for item in st.session_state.market.get(pos, {}):
                data = st.session_state.market[pos][item]
                base = items_info[item]['base']

                cls = "price-up" if data['price'] > base * 1.15 else \
                      "price-down" if data['price'] < base * 0.85 else "price-same"

                with st.container(border=True):
                    st.markdown(f"**{item}**   <span class='{cls}'>{data['price']:,}냥</span>", unsafe_allow_html=True)
                    col_a, col_b, col_c = st.columns([4,2,2])
                    col_a.write(f"재고 : {data['stock']:,}개")
                    col_b.write(f"최대 구매 가능 : {min(player['money']//data['price'] if data['price']>0 else 0, (tw-cw)//items_info[item]['w'] if items_info[item]['w']>0 else 999)}")

                    qty = col_c.number_input("수량", min_value=1, value=1, step=1,
                                             key=f"qty_{pos}_{item}")

                    c_buy, c_sell = st.columns(2)
                    if c_buy.button("매수", key=f"buy_{pos}_{item}"):
                        qty_done, spent, logid = trade_item("buy", item, qty)
                        if qty_done > 0:
                            st.success(f"{qty_done}개 매수 완료 (-{spent:,}냥)")
                            if logid in st.session_state.trade_logs:
                                with st.container():
                                    st.markdown("<div class='trade-log'>", unsafe_allow_html=True)
                                    for line in st.session_state.trade_logs[logid][-8:]:
                                        st.write(line)
                                    st.markdown("</div>", unsafe_allow_html=True)
                        st.rerun()

                    if c_sell.button("매도", key=f"sell_{pos}_{item}"):
                        qty_done, earned, logid = trade_item("sell", item, qty)
                        if qty_done > 0:
                            st.success(f"{qty_done}개 매도 완료 (+{earned:,}냥)")
                            if logid in st.session_state.trade_logs:
                                with st.container():
                                    st.markdown("<div class='trade-log'>", unsafe_allow_html=True)
                                    for line in st.session_state.trade_logs[logid][-8:]:
                                        st.write(line)
                                    st.markdown("</div>", unsafe_allow_html=True)
                        st.rerun()

    with tab_inv:
        st.subheader("인벤토리")
        if player['inv']:
            for it, q in sorted(player['inv'].items()):
                if q > 0:
                    st.write(f"• {it} × {q:,}")
        else:
            st.info("인벤토리가 비어 있습니다.")

    with tab_merc:
        st.subheader("용병")
        if player['mercs']:
            from collections import Counter
            for m, cnt in Counter(player['mercs']).items():
                st.write(f"• {m} × {cnt}명  (무게 +{merc_data[m]['w_bonus'] * cnt:,}근)")
        else:
            st.info("고용한 용병이 없습니다.")

    with tab_menu:
        st.subheader("메뉴")
        dest = st.selectbox("이동할 마을", [v for v in villages if v != pos])
        if st.button("이동하기"):
            player['pos'] = dest
            st.rerun()

        if st.button("저장"):
            # 저장 로직 (필요 시 구현)
            st.success("저장되었습니다 (아직 DB 연동 미완료)")

        if st.button("나가기"):
            st.session_state.game_started = False
            st.rerun()
