import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import uuid

# --- 1. 페이지 설정 및 모바일 최적화 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    /* 이동 탭의 스크롤바 설정 */
    .village-scroll {
        max-height: 400px;
        overflow-y: auto;
        padding-right: 10px;
    }
    .stButton button { width: 100%; margin: 2px 0; padding: 12px; font-size: 16px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 로드 (에러 방지용 캐싱) ---
@st.cache_resource
def connect_gsheet():
    try:
        # secrets에서 정보를 안전하게 가져옴
        creds = Credentials.from_service_account_info(
            st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 실패: {e}")
        return None

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    try:
        # 각 시트 데이터 로드
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 마을 데이터 로드 (마을 개수 상관없이 자동화)
        vil_ws = doc.worksheet("Village_Data")
        vals = vil_ws.get_all_values()
        headers = vals[0]
        villages = {}
        item_max_stocks = {name: 0 for name in items_info.keys()}
        
        for row in vals[1:]:
            if not row[0]: continue
            v_name = row[0]
            villages[v_name] = {'x': int(row[1]), 'y': int(row[2]), 'items': {}}
            for i in range(3, len(headers)):
                item_name = headers[i]
                if item_name in items_info and i < len(row) and row[i]:
                    stock = int(row[i])
                    villages[v_name]['items'][item_name] = stock
                    # 시세 기준점: 해당 아이템의 전 세계 최대 재고량
                    if stock > item_max_stocks[item_name]:
                        item_max_stocks[item_name] = stock
                        
        player_recs = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, villages, item_max_stocks, player_recs
    except Exception as e:
        st.error(f"❌ 데이터 파싱 에러: {e}")
        return None

# --- 3. 시세 업데이트 (평양/부산 차이 로직) ---
def update_market_prices(settings, items_info, market_data, item_max_stocks):
    vol = settings.get('volatility', 5000) / 1000
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_s = i_info['stock']
                max_s = item_max_stocks.get(i_name, 100)
                
                if curr_s <= 0:
                    i_info['price'] = base * 10
                else:
                    # 재고 격차에 따른 시세 차이 (평양 200 vs 부산 5000 -> 25배 차이 반영)
                    ratio = max_s / curr_s
                    factor = math.pow(ratio, (vol / 4))
                    i_info['price'] = int(base * max(0.4, min(25.0, factor)))

# --- 4. 게임 엔진 실행 ---
data = load_game_data()
if data:
    doc, settings, items_info, mercs_data, villages, item_max_stocks, player_records = data

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("불러올 슬롯", [1, 2, 3])
        if st.button("게임 시작", key="start"):
            p_rec = player_records[slot-1]
            st.session_state.player = {
                'money': int(p_rec['money']) if p_rec['money'] else 10000,
                'pos': p_rec['pos'] if p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec['inventory'] else {},
                'start_time': time.time()
            }
            st.session_state.stats = {'slot': slot}
            # 초기 시장가 설정
            market = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in info['items'].items()} for v, info in villages.items()}
            st.session_state.market_prices = market
            update_market_prices(settings, items_info, market, item_max_stocks)
            st.session_state.game_started = True
            st.rerun()

    else:
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        st.header(f"📍 현재 위치: {curr_pos}")
        st.subheader(f"💰 소지금: {player['money']:,}냥")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                st.write("용병을 고용하여 짐 무게를 늘리세요.")
                for m_name, m_info in mercs_data.items():
                    if st.button(f"{m_name} 고용 ({m_info['price']:,}냥)", key=f"merc_{m_name}"):
                        if player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']
                            player['mercs'].append(m_name)
                            st.success(f"{m_name} 고용 완료!"); st.rerun()
            else:
                for i_name, i_data in market[curr_pos].items():
                    c1, c2, c3 = st.columns([2,1,1])
                    c1.write(f"**{i_name}** ({i_data['stock']}개)")
                    c2.write(f"{i_data['price']:,}냥")
                    if c3.button("선택", key=f"sel_{i_name}"): st.session_state.trade_target = i_name
                
                if 'trade_target' in st.session_state:
                    t = st.session_state.trade_target
                    amt = st.number_input(f"{t} 수량", 1, 10000, 1)
                    cc1, cc2 = st.columns(2)
                    if cc1.button("매수", key="buy"):
                        price = market[curr_pos][t]['price'] * amt
                        if player['money'] >= price and market[curr_pos][t]['stock'] >= amt:
                            player['money'] -= price
                            player['inventory'][t] = player['inventory'].get(t, 0) + amt
                            market[curr_pos][t]['stock'] -= amt
                            update_market_prices(settings, items_info, market, item_max_stocks)
                            st.rerun()
                    if cc2.button("매도", key="sell"):
                        if player['inventory'].get(t, 0) >= amt:
                            player['money'] += market[curr_pos][t]['price'] * amt
                            player['inventory'][t] -= amt
                            market[curr_pos][t]['stock'] += amt
                            update_market_prices(settings, items_info, market, item_max_stocks)
                            st.rerun()

        with tab2:
            st.subheader("🚩 이동할 마을 선택")
            # 💡 마을이 많아져도 스크롤 가능한 컨테이너
            with st.container(height=400):
                dests = [n for n in villages.keys() if n != curr_pos]
                for dest in dests:
                    d_info = villages[dest]
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings.get('travel_cost', 15))
                    # 각 버튼에 고유 키 부여 (중복 ID 에러 방지)
                    if st.button(f"🏯 {dest} 이동 ({cost}냥 / {int(dist)}리)", key=f"move_{dest}"):
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            st.rerun()
                        else:
                            st.error("돈이 부족합니다!")

        with tab3:
            st.write(f"🎒 소지 용병: {', '.join(player['mercs']) if player['mercs'] else '없음'}")
            st.write(f"📦 인벤토리: {player['inventory']}")
            if st.button("💾 데이터 저장", key="save"):
                ws = doc.worksheet("Player_Data")
                data = [st.session_state.stats['slot'], player['money'], player['pos'], 
                        json.dumps(player['mercs'], ensure_ascii=False), 
                        json.dumps(player['inventory'], ensure_ascii=False), 
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.stats['slot']+1}:F{st.session_state.stats['slot']+1}", [data])
                st.success("저장 완료!")
