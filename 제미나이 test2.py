import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 세션 초기화 (AttributeError 방지) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False

# --- 2. 데이터 로드 함수 (SyntaxError 수정 완료) ---
@st.cache_resource
def init_spreadsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        doc = client.open("조선거상_DB")
        
        # Setting_Data (volatility, fire_refund_rate 등)
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        
        # Item_Data
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        
        # Balance_Data (용병)
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 마을 재고 데이터 (SyntaxError 수정 지점)
        market_data = {}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                for r in ws.get_all_records():
                    v_name = r.pop('village_name')
                    # 따옴표 앞의 불필요한 역슬래시 제거 완료
                    market_data[v_name] = {k: {'stock': int(v) if v != "" else 0} for k, v in r.items()}
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, market_data, player_slots
    except Exception as e:
        st.error(f"데이터 로드 에러: {e}")
        return None

# 데이터 호출
db_data = init_spreadsheet()

if db_data:
    doc, settings, items_info, mercs_data, market_data, player_slots = db_data

    # --- 3. 시세 계산 (시트의 volatility 5000 반영) ---
    def get_dynamic_price(item_name, city):
        base = items_info[item_name]['base']
        stock = market_data[city][item_name]['stock']
        vol = settings.get('volatility', 5000) / 1000  # 5.0
        
        if stock <= 0: return base * 5
        # 재고 기반 가격 변동 공식
        ratio = 100 / max(1, stock)
        factor = math.pow(ratio, (vol / 4))
        factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
        return int(base * factor)

    # --- 4. 메인 게임 화면 ---
    if not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        # 슬롯 선택 로직 (사용자 원본)
        for i, p in enumerate(player_slots):
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
        p_data = st.session_state.player
        current_city = p_data['pos']
        
        # 실시간 무게 계산
        max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in p_data['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in p_data['inventory'].items() if it in items_info])
        
        st.info(f"💰 {p_data['money']:,}냥 | 📦 {curr_w}/{max_w}근")

        tab1, tab2 = st.tabs(["🛒 시장", "🛡️ 용병"])

        with tab1:
            target = st.selectbox("품목", list(items_info.keys()))
            amt = st.number_input("수량(99999 입력 가능)", 1, 1000000, 100)
            
            if st.button("🚀 매수 실행"):
                log_area = st.empty()
                logs = []
                done = 0
                while done < amt:
                    batch = min(100, amt - done)
                    price = get_dynamic_price(target, current_city)
                    
                    # [핵심] 무게/자금 부족 시 즉시 루프 탈출
                    if p_data['money'] < price * batch or curr_w + (items_info[target]['w'] * batch) > max_w:
                        logs.append("⚠️ 무게 또는 자금 부족으로 중단!")
                        break
                    
                    # 체결 처리
                    p_data['money'] -= price * batch
                    p_data['inventory'][target] = p_data['inventory'].get(target, 0) + batch
                    market_data[current_city][target]['stock'] -= batch
                    curr_w += items_info[target]['w'] * batch
                    done += batch
                    
                    logs.append(f"📦 {target} {batch}개 매수 중... ({done}/{amt})")
                    log_area.markdown(f'<div style="background:#f0f2f6;padding:10px;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                    time.sleep(0.01)
                st.rerun()

        with tab2:
            st.write("### 🛡️ 용병 해고")
            refund_rate = settings.get('fire_refund_rate', 0.5)
            for i, m_name in enumerate(p_data['mercs']):
                col1, col2 = st.columns([3, 1])
                refund = int(mercs_data[m_name]['price'] * refund_rate)
                col1.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
                if col2.button(f"해고({refund:,}냥)", key=f"fire_{i}"):
                    p_data['money'] += refund
                    p_data['mercs'].pop(i)
                    st.rerun()
