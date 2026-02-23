import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import uuid

# --- 1. 페이지 설정 및 스타일 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

st.markdown("""
<style>
    .stButton button { width: 100%; margin: 5px 0; padding: 15px; font-size: 18px; }
    .price-up { color: #ff4b4b; font-weight: bold; }
    .price-down { color: #4b7bff; font-weight: bold; }
    .trade-progress { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# --- 2. 데이터 로드 (스프레드시트 연동) ---
@st.cache_resource
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 시트 연결 실패: {e}"); return None

def load_game_data():
    doc = connect_gsheet()
    if not doc: return None
    
    # 1) 세팅 (volatility 5000)
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    # 2) 아이템 (생선 85냥 등)
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    # 3) 용병
    mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
    
    # 4) 마을 (재고 로드 및 시세 기준값 계산)
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
                if stock > item_max_stocks[item_name]:
                    item_max_stocks[item_name] = stock
                
    player_recs = doc.worksheet("Player_Data").get_all_records()
    return doc, settings, items_info, mercs_data, villages, item_max_stocks, player_recs

# --- 3. 핵심: 시세 로직 (재고비례 폭등/폭락) ---
def update_market_prices(settings, items_info, market_data, item_max_stocks):
    vol = settings.get('volatility', 5000) / 1000 
    for v_name, items in market_data.items():
        if v_name == "용병 고용소": continue
        for i_name, i_info in items.items():
            if i_name in items_info:
                base = items_info[i_name]['base']
                curr_s = i_info['stock']
                max_s = item_max_stocks.get(i_name, 100)
                if curr_s <= 0: i_info['price'] = base * 10
                else:
                    ratio = max_s / curr_s # 부산 5000/5000=1, 평양 5000/200=25
                    factor = math.pow(ratio, (vol / 4)) # 재고 적은 평양은 기하급수적으로 비싸짐
                    i_info['price'] = int(base * max(0.5, min(30.0, factor)))

# --- 4. 엔진 및 UI ---
res = load_game_data()
if res:
    doc, settings, items_info, mercs_data, villages, item_max_stocks, player_records = res

    if 'game_started' not in st.session_state:
        st.session_state.game_started = False

    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slot = st.selectbox("슬롯 선택", [1, 2, 3])
        if st.button("게임 시작", use_container_width=True):
            p_rec = player_records[slot-1]
            st.session_state.player = {
                'money': int(p_rec['money']) if p_rec['money'] else 10000,
                'pos': p_rec['pos'] if p_rec['pos'] else "한양",
                'mercs': json.loads(p_rec['mercs']) if p_rec['mercs'] else [],
                'inventory': json.loads(p_rec['inventory']) if p_rec['inventory'] else {},
                'start_time': time.time()
            }
            st.session_state.stats = {'slot': slot}
            # 초기 마켓 생성 및 시세 적용
            market = {v: {i: {'stock': s, 'price': items_info[i]['base']} for i, s in info['items'].items()} for v, info in villages.items()}
            st.session_state.market_prices = market
            update_market_prices(settings, items_info, market, item_max_stocks)
            st.session_state.game_started = True
            st.rerun()

    else:
        player = st.session_state.player
        market = st.session_state.market_prices
        curr_pos = player['pos']
        
        # 상단바
        max_w = 200 + sum(mercs_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs'])
        curr_w = sum(player['inventory'].get(n, 0) * items_info.get(n, {}).get('w', 0) for n in player['inventory'])
        
        st.header(f"📍 {curr_pos}")
        c1, c2 = st.columns(2)
        c1.metric("💰 소지금", f"{player['money']:,}냥")
        c2.metric("📦 무게", f"{curr_w}/{max_w}근")

        tab1, tab2, tab3 = st.tabs(["🛒 장터", "🚩 이동", "👤 내 정보"])

        with tab1:
            if curr_pos == "용병 고용소":
                for m_name, m_info in mercs_data.items():
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**{m_name}** (+{m_info['weight_bonus']}근)")
                    if col2.button(f"{m_info['price']:,}냥", key=f"buy_{m_name}"):
                        if player['money'] >= m_info['price']:
                            player['money'] -= m_info['price']; player['mercs'].append(m_name); st.rerun()
            else:
                for i_name, i_data in market[curr_pos].items():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    col1.write(f"**{i_name}** ({i_data['stock']}개)")
                    col2.write(f"{i_data['price']:,}냥")
                    if col3.button("선택", key=f"sel_{i_name}"): st.session_state.trade_item = i_name

                if 'trade_item' in st.session_state:
                    t_item = st.session_state.trade_item
                    st.divider()
                    amt = st.number_input(f"{t_item} 수량", 1, 10000, 1)
                    cc1, cc2 = st.columns(2)
                    if cc1.button("매수", key="btn_buy"):
                        cost = market[curr_pos][t_item]['price'] * amt
                        if player['money'] >= cost and market[curr_pos][t_item]['stock'] >= amt and (curr_w + items_info[t_item]['w']*amt) <= max_w:
                            player['money'] -= cost
                            player['inventory'][t_item] = player['inventory'].get(t_item, 0) + amt
                            market[curr_pos][t_item]['stock'] -= amt
                            update_market_prices(settings, items_info, market, item_max_stocks)
                            st.rerun()
                    if cc2.button("매도", key="btn_sell"):
                        if player['inventory'].get(t_item, 0) >= amt:
                            player['money'] += market[curr_pos][t_item]['price'] * amt
                            player['inventory'][t_item] -= amt
                            market[curr_pos][t_item]['stock'] += amt
                            update_market_prices(settings, items_info, market, item_max_stocks)
                            st.rerun()

        with tab2:
            st.subheader("마을 이동")
            # 💡 마을 자동 생성 루프 (StreamlitDuplicateElementId 방지 위해 key 부여)
            dests = [n for n in villages.keys() if n != curr_pos]
            cols = st.columns(2)
            for idx, dest in enumerate(dests):
                with cols[idx % 2]:
                    d_info = villages[dest]
                    dist = math.sqrt((villages[curr_pos]['x']-d_info['x'])**2 + (villages[curr_pos]['y']-d_info['y'])**2)
                    cost = int(dist * settings.get('travel_cost', 15))
                    if st.button(f"🏯 {dest}\n({cost}냥)", key=f"btn_move_{dest}"):
                        if player['money'] >= cost:
                            player['money'] -= cost; player['pos'] = dest; st.rerun()

        with tab3:
            st.write(f"👥 용병: {player['mercs']}")
            st.write("🎒 인벤토리:")
            for k, v in player['inventory'].items():
                if v > 0: st.write(f"- {k}: {v}개")
            # 💡 저장 버튼에도 고유 키 부여
            if st.button("💾 데이터 저장", key="btn_final_save", use_container_width=True):
                ws = doc.worksheet("Player_Data")
                data = [st.session_state.stats['slot'], player['money'], player['pos'], json.dumps(player['mercs'], ensure_ascii=False), json.dumps(player['inventory'], ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{st.session_state.stats['slot']+1}:F{st.session_state.stats['slot']+1}", [data])
                st.success("저장 완료!")
            if st.button("🚪 메인으로", key="btn_go_main", use_container_width=True):
                st.session_state.game_started = False; st.rerun()
