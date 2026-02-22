import time
import json
import sys
import math
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 시트 연결 & 데이터 로드 ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"❌ 연결 실패: {e}")
        st.stop()

@st.cache_data(ttl=60) # 1분마다 데이터 새로고침
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
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name: continue
            villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if i < len(row) and headers[i] in items_info and row[i]:
                        villages[v_name]['items'][headers[i]] = int(row[i])
        
        play_ws = doc.worksheet("Player_Data")
        slots = play_ws.get_all_records()
        
        return settings, items_info, merc_data, villages, slots
    except Exception as e:
        st.error(f"❌ 데이터 로드 오류: {e}")
        return None

# --- 2. 게임 필수 함수 (원본 로직 이식) ---
def get_weight(player, items_info, merc_data):
    cw = sum(player['inv'].get(i, 0) * items_info[i]['w'] for i in player['inv'] if i in items_info)
    tw = 200 + sum(merc_data[m]['w_bonus'] for m in player['mercs'] if m in merc_data)
    return cw, tw

def get_current_price(item_name, stock, settings, items_info, month):
    vol = settings.get('volatility', 500)
    base = items_info[item_name]['base']
    price = int(base * (1 + (vol / (stock + 10)))) if stock > 0 else base * 10
    # 계절 효과
    if month in [3,4,5] and item_name in ['인삼', '소가죽', '염색가죽']: price = int(price * 1.2)
    elif month in [6,7,8] and item_name == '비단': price = int(price * 1.3)
    elif month in [9,10,11] and item_name == '쌀': price = int(price * 1.3)
    elif month in [12,1,2] and item_name == '가죽갑옷': price = int(price * 1.5)
    return price

# --- 3. 메인 화면 구성 ---
st.set_page_config(page_title="조선거상 웹", layout="wide")
SETTINGS, ITEMS_INFO, MERC_DATA, VILLAGES, SLOTS = get_initial_data()

if 'player' not in st.session_state:
    st.title("🏯 조선거상 미니 게임")
    st.write("### 💾 세이브 슬롯 선택")
    for s in SLOTS:
        st.write(f"[{s['slot']}] 위치: {s['pos']} | 잔액: {int(s.get('money', 0)):,}냥")
    
    choice = st.number_input("슬롯 번호를 선택하세요", min_value=1, max_value=len(SLOTS), step=1)
    if st.button("🎮 게임 시작하기"):
        p_row = next(s for s in SLOTS if s['slot'] == choice)
        st.session_state.player = {
            'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
            'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
            'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
            'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1))
        }
        st.rerun()
else:
    player = st.session_state.player
    cw, tw = get_weight(player, ITEMS_INFO, MERC_DATA)
    
    # 상단 정보바
    st.title(f"🏯 {player['pos']}")
    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("💰 잔액", f"{player['money']:,} 냥")
    col_info2.metric("⚖️ 무게", f"{cw} / {tw} 근")
    col_info3.metric("📅 날짜", f"{player['year']}년 {player['month']}월 {player['week']}주")

    # 메뉴 탭
    tab1, tab2, tab3, tab4 = st.tabs(["🛒 시장", "🚚 이동", "📦 가방/용병", "💾 저장/종료"])

    with tab1: # 시장 (구매/판매)
        if player['pos'] == "용병 고용소":
            st.write("### ⚔️ 용병 고용")
            for m_name, d in MERC_DATA.items():
                if st.button(f"{m_name} 고용 ({d['price']:,}냥 | 무게+{d['w_bonus']})"):
                    if m_name in player['mercs']: st.warning("이미 보유 중입니다.")
                    elif player['money'] >= d['price']:
                        player['money'] -= d['price']
                        player['mercs'].append(m_name)
                        st.success(f"{m_name} 고용 완료!")
                        st.rerun()
                    else: st.error("잔액이 부족합니다.")
        else:
            st.write("### 🛍️ 물품 거래")
            v_items = VILLAGES[player['pos']]['items']
            for i_name, stock in v_items.items():
                price = get_current_price(i_name, stock, SETTINGS, ITEMS_INFO, player['month'])
                c1, c2, c3 = st.columns([2, 1, 2])
                c1.write(f"**{i_name}** (재고: {stock})")
                c2.write(f"{price:,}냥")
                if c3.button(f"구매", key=f"buy_{i_name}"):
                    if player['money'] >= price and (cw + ITEMS_INFO[i_name]['w']) <= tw:
                        player['money'] -= price
                        player['inv'][i_name] = player['inv'].get(i_name, 0) + 1
                        VILLAGES[player['pos']]['items'][i_name] -= 1
                        st.rerun()
                    else: st.error("잔액 또는 무게 부족!")

    with tab2: # 이동
        st.write("### 🚚 마을 이동")
        for t_name, t_data in VILLAGES.items():
            if t_name == player['pos']: continue
            dist = math.sqrt((VILLAGES[player['pos']]['x']-t_data['x'])**2 + (VILLAGES[player['pos']]['y']-t_data['y'])**2)
            cost = int(dist * SETTINGS.get('travel_cost', 15))
            if st.button(f"{t_name} (비용: {cost:,}냥)"):
                if player['money'] >= cost:
                    player['money'] -= cost
                    player['pos'] = t_name
                    # 이동 시 시간 경과 로직 추가 가능
                    st.rerun()
                else: st.error("비용이 부족합니다.")

    with tab3: # 인벤토리
        st.write(f"### 📦 내 가방")
        st.write(player['inv'])
        st.write(f"### ⚔️ 보유 용병")
        st.write(", ".join(player['mercs']) if player['mercs'] else "없음")

    with tab4: # 저장 및 종료
        if st.button("💾 게임 데이터 저장하기"):
            try:
                doc = connect_gsheet()
                play_ws = doc.worksheet("Player_Data")
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                save_v = [player['slot'], player['money'], player['pos'], 
                          json.dumps(player['mercs']), json.dumps(player['inv']), now,
                          player['week'], player['month'], player['year']]
                play_ws.update(f'A{player["slot"]+1}:I{player["slot"]+1}', [save_v])
                st.success("구글 시트에 저장 완료!")
            except Exception as e: st.error(f"저장 실패: {e}")
        
        if st.button("❌ 게임 종료 (메인으로)"):
            del st.session_state.player
            st.rerun()
