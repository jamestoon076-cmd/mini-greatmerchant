import time
import json
import sys
import math
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 시트 연결 및 데이터 로드 ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}")
        st.stop()

@st.cache_data(ttl=60)
def get_initial_data():
    doc = connect_gsheet()
    try:
        set_ws = doc.worksheet("Setting_Data")
        settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records()}
        item_ws = doc.worksheet("Item_Data")
        items_info = {str(r['item_name']).strip(): {'base': int(r['base_price']), 'w': int(r['weight'])} 
                      for r in item_ws.get_all_records() if r.get('item_name')}
        bal_ws = doc.worksheet("Balance_Data")
        merc_data = {r['name'].strip(): {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} 
                     for r in bal_ws.get_all_records()}
        vil_ws = doc.worksheet("Village_Data")
        vil_vals = vil_ws.get_all_values()
        headers = [h.strip() for h in vil_vals[0]]
        villages = {}
        initial_stocks = {}
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name: continue
            villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if i < len(row) and headers[i] in items_info and row[i]:
                        stock = int(row[i])
                        villages[v_name]['items'][headers[i]] = stock
                        initial_stocks[v_name][headers[i]] = stock
        play_ws = doc.worksheet("Player_Data")
        slots = play_ws.get_all_records()
        return settings, items_info, merc_data, villages, initial_stocks, slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 오류: {e}")
        return None

# --- 2. 게임 로직 함수 ---
def get_weight(player, items_info, merc_data):
    cw = sum(player['inv'].get(i, 0) * items_info[i]['w'] for i in player['inv'] if i in items_info)
    tw = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return cw, tw

def get_price(item_name, stock, settings, items_info, month):
    vol = settings.get('volatility', 500)
    base = items_info[item_name]['base']
    price = int(base * (1 + (vol / (stock + 10)))) if stock > 0 else base * 10
    if month in [3,4,5] and item_name in ['인삼', '소가죽', '염색가죽']: price = int(price * 1.2)
    elif month in [6,7,8] and item_name == '비단': price = int(price * 1.3)
    elif month in [9,10,11] and item_name == '쌀': price = int(price * 1.3)
    elif month in [12,1,2] and item_name == '가죽갑옷': price = int(price * 1.5)
    return price

# --- 3. 메인 실행 및 화면 ---
st.set_page_config(page_title="조선거상 모바일", layout="centered")
data = get_initial_data()
if data:
    SETTINGS, ITEMS_INFO, MERC_DATA, VILLAGES, INITIAL_STOCKS, SLOTS = data

# 세이브 슬롯 선택 (모바일 최적화)
if 'player' not in st.session_state:
    st.title("🏯 조선거상 (슬롯 선택)")
    for s in SLOTS:
        st.write(f"**[{s['slot']}번 슬롯]** {s['pos']} | {int(s.get('money', 0)):,}냥")
    
    choice = st.number_input("슬롯 번호", min_value=1, max_value=len(SLOTS), step=1)
    if st.button("🎮 게임 시작 (ENTER 대신 클릭)", use_container_width=True):
        p_row = next(s for s in SLOTS if s['slot'] == choice)
        st.session_state.player = {
            'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
            'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
            'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
            'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1)),
            'last_tick': time.time()
        }
        st.rerun()

else:
    player = st.session_state.player
    cw, tw = get_weight(player, ITEMS_INFO, MERC_DATA)
    
    # 45초/3분 시간 로직
    now = time.time()
    if now - player['last_tick'] >= 45:
        player['last_tick'] = now
        player['week'] += 1
        st.toast("📅 1주가 경과했습니다!")
        if player['week'] > 4:
            player['week'] = 1
            player['month'] += 1
            st.success("📦 월초 재고 초기화 완료!")
            if player['month'] > 12: player['month'] = 1; player['year'] += 1
        st.rerun()

    # 상단 상태바
    st.subheader(f"📍 {player['pos']}")
    st.info(f"💰 {player['money']:,}냥 | ⚖️ {cw}/{tw}근\n\n📅 {player['year']}년 {player['month']}월 {player['week']}주")

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 시장", "🚚 이동", "📦 가방", "💾 시스템"])

    with tab1: # 시장
        if player['pos'] == "용병 고용소":
            for m_name, d in MERC_DATA.items():
                if st.button(f"⚔️ {m_name} 고용 ({d['price']:,}냥)", use_container_width=True):
                    if m_name not in player['mercs'] and player['money'] >= d['price']:
                        player['money'] -= d['price']
                        player['mercs'].append(m_name)
                        st.rerun()
        else:
            for i_name, stock in VILLAGES[player['pos']]['items'].items():
                price = get_price(i_name, stock, SETTINGS, ITEMS_INFO, player['month'])
                st.write(f"**{i_name}** | {price:,}냥 (재고:{stock})")
                if st.button(f"🛒 {i_name} 1개 구매", key=f"b_{i_name}", use_container_width=True):
                    if player['money'] >= price and (cw + ITEMS_INFO[i_name]['w']) <= tw:
                        player['money'] -= price
                        player['inv'][i_name] = player['inv'].get(i_name, 0) + 1
                        VILLAGES[player['pos']]['items'][i_name] -= 1
                        st.rerun()
                st.divider()

    with tab2: # 이동
        for t_name, t_data in VILLAGES.items():
            if t_name == player['pos']: continue
            dist = math.sqrt((VILLAGES[player['pos']]['x']-t_data['x'])**2 + (VILLAGES[player['pos']]['y']-t_data['y'])**2)
            cost = int(dist * SETTINGS.get('travel_cost', 15))
            if st.button(f"🚩 {t_name} 이동 ({cost:,}냥)", use_container_width=True):
                if player['money'] >= cost:
                    player['money'] -= cost
                    player['pos'] = t_name
                    st.rerun()

    with tab3: # 가방
        st.write("### 📦 보유 물품")
        for i, q in player['inv'].items():
            if q > 0:
                st.write(f"{i}: {q}개")
                if st.button(f"💰 {i} 1개 판매", key=f"s_{i}", use_container_width=True):
                    price = get_price(i, VILLAGES[player['pos']]['items'].get(i, 100), SETTINGS, ITEMS_INFO, player['month'])
                    player['money'] += price
                    player['inv'][i] -= 1
                    VILLAGES[player['pos']]['items'][i] = VILLAGES[player['pos']]['items'].get(i, 0) + 1
                    st.rerun()

    with tab4: # 시스템
        if st.button("💾 데이터 시트 저장", use_container_width=True):
            try:
                play_ws = connect_gsheet().worksheet("Player_Data")
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                save_v = [player['slot'], player['money'], player['pos'], json.dumps(player['mercs']), 
                          json.dumps(player['inv']), now_str, player['week'], player['month'], player['year']]
                play_ws.update(f'A{player["slot"]+1}:I{player["slot"]+1}', [save_v])
                st.success("저장 완료!")
            except Exception as e: st.error(f"저장 실패: {e}")
        if st.button("❌ 메인 화면으로", use_container_width=True):
            del st.session_state.player
            st.rerun()
