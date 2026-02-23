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

# --- 1. 페이지 설정 및 세션 초기화 (최상단) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. 데이터 로드 함수 (사용자님의 gspread 로직) ---
@st.cache_resource
def init_spreadsheet():
    try:
        # st.secrets["gspread"] 기반 인증
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        doc = client.open("조선거상_DB")
        
        # Setting_Data 로드 (volatility, fire_refund_rate 등)
        settings_ws = doc.worksheet("Setting_Data").get_all_records()
        settings = {r['변수명']: float(r['값']) for r in settings_ws if r.get('변수명')}
        
        # Item_Data 로드
        items_ws = doc.worksheet("Item_Data").get_all_records()
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in items_ws}
        
        # Balance_Data 로드 (용병)
        mercs_ws = doc.worksheet("Balance_Data").get_all_records()
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in mercs_ws}
        
        # 마을 재고 데이터
        market_data = {}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                rows = ws.get_all_records()
                for r in rows:
                    v_name = r.pop('village_name')
                    market_data[v_name] = {k: {'stock': int(v) if v != \"\" else 0} for k, v in r.items()}
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, market_data, player_slots
    except Exception as e:
        st.error(f"시트 로드 에러: {e}")
        return None

# 데이터 로드 실행
db_data = init_spreadsheet()

if db_data:
    doc, settings, items_info, mercs_data, market_data, player_slots = db_data

    # --- 3. 가격 변동 계산 (Setting_Data의 volatility 반영) ---
    def get_dynamic_price(item_name, city):
        base = items_info[item_name]['base']
        stock = market_data[city][item_name]['stock']
        vol = settings.get('volatility', 5000) / 1000 # 5.0
        
        if stock <= 0: return base * 5
        # 재고 기반 지수함수 (시트 변수 반영)
        ratio = 100 / stock
        factor = math.pow(ratio, (vol / 4))
        factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
        return int(base * factor)

    # --- 4. 메인 화면 로직 ---
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        for i, p in enumerate(player_slots):
            with st.container(border=True):
                st.write(f"💾 **슬롯 {i+1}** | 💰 {int(p.get('money',0)):,}냥 | 📍 {p.get('pos','한양')}")
                if st.button(f"슬롯 {i+1} 접속", key=f"slot_{i}"):
                    st.session_state.player = {
                        'money': int(p.get('money', 10000)),
                        'pos': p.get('pos', '한양'),
                        'inventory': json.loads(p['inventory']) if p.get('inventory') else {},
                        'mercs': json.loads(p['mercs']) if p.get('mercs') else [],
                        'start_time': time.time()
                    }
                    st.session_state.game_started = True
                    st.rerun()

    else:
        player = st.session_state.player
        current_city = player['pos']
        
        # 실시간 무게 계산
        max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        
        # 상단 정보 메트릭
        st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근 | ⏰ {int(settings.get('seconds_per_month', 180)) - int(time.time() - player['start_time']) % int(settings.get('seconds_per_month', 180))}초 후 다음 달")

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 해고", "🚩 이동"])

        with tab1:
            st.subheader(f"📍 {current_city} 시장")
            target_item = st.selectbox("품목", list(items_info.keys()))
            amt = st.number_input("수량 (99999 등 큰 숫자 가능)", 1, 1000000, 100)
            
            if st.button("🚀 실제 분할 매수 실행"):
                log_p = st.empty()
                logs = []
                done = 0
                while done < amt:
                    batch = min(100, amt - done)
                    price = get_dynamic_price(target_item, current_city)
                    
                    # 99999 입력 시 한도 체크 후 자동 중단
                    if player['money'] < price * batch or curr_w + (items_info[target_item]['w'] * batch) > max_w:
                        logs.append("❌ 자금/무게 부족으로 중단")
                        break
                    
                    player['money'] -= price * batch
                    player['inventory'][target_item] = player['inventory'].get(target_item, 0) + batch
                    market_data[current_city][target_item]['stock'] -= batch
                    curr_w += items_info[target_item]['w'] * batch
                    done += batch
                    
                    logs.append(f"📦 {target_item} {batch}개 매수 중... ({done}/{amt})")
                    log_p.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;font-family:monospace;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                    time.sleep(0.01)
                st.rerun()

        with tab2:
            st.write("### 🛡️ 상단 용병 해고")
            refund_rate = settings.get('fire_refund_rate', 0.5)
            for i, m_name in enumerate(player['mercs']):
                c1, c2 = st.columns([3, 1])
                refund = int(mercs_data[m_name]['price'] * refund_rate)
                c1.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
                if c2.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                    player['money'] += refund
                    player['mercs'].pop(i)
                    st.rerun()
