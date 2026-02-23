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

# --- 1. 페이지 설정 (최상단) ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="centered")

# --- 2. [필독] 세션 상태 초기화 (AttributeError 방지) ---
if 'game_started' not in st.session_state:
    st.session_state.game_started = False
if 'player' not in st.session_state:
    st.session_state.player = None

# --- 3. 데이터 로드 함수 (사용자 원본 gspread 로직 유지) ---
@st.cache_resource
def load_game_data():
    try:
        # 서비스 계정 키를 이용한 gspread 인증 (st.secrets["gspread"] 필요)
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        doc = client.open("조선거상_DB")
        
        # 1. 설정 데이터 (변동성, 환불비율 등)
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        
        # 2. 아이템 정보 (기본가, 무게)
        items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        
        # 3. 용병 정보 (가격, 무게 보너스)
        mercs_data = {r['name']: {'price': int(r['price']), 'weight_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        
        # 4. 마을 재고 데이터 (국가별 시트 통합)
        market_data = {}
        for ws in doc.worksheets():
            if "_Village_Data" in ws.title:
                city_list = ws.get_all_records()
                for city_row in city_list:
                    city_name = city_row.pop('village_name')
                    market_data[city_name] = {item: {'stock': int(stock) if stock != "" else 0} for item, stock in city_row.items()}
        
        player_slots = doc.worksheet("Player_Data").get_all_records()
        return doc, settings, items_info, mercs_data, market_data, player_slots
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None

# --- 4. 가격 변동 계산 함수 (Setting_Data의 volatility 반영) ---
def get_price(item_name, city, items_info, market_data, settings):
    base = items_info[item_name]['base']
    stock = market_data[city][item_name]['stock']
    vol = settings.get('volatility', 5000) / 1000 # 5000 -> 5.0
    
    if stock <= 0: return base * 5 # 재고 없으면 5배 폭등
    
    # [수식] (100 / 현재재고) ^ (변동성 / 4) -> 재고가 100보다 적으면 가격 상승
    ratio = 100 / stock
    factor = math.pow(ratio, (vol / 4))
    
    # Setting_Data의 min/max_price_rate 적용
    factor = max(settings.get('min_price_rate', 0.4), min(settings.get('max_price_rate', 3.0), factor))
    return int(base * factor)

# --- 5. 게임 메인 로직 ---
data = load_game_data()

if data:
    doc, settings, items_info, mercs_data, market_data, player_slots = data
    
    if not st.session_state.game_started:
        # [슬롯 선택 화면]
        st.title("🏯 조선거상 미니")
        for i, p in enumerate(player_slots):
            with st.container(border=True):
                st.write(f"💾 **슬롯 {i+1}** | 📍 {p.get('pos','한양')} | 💰 {int(p.get('money',0)):,}냥")
                if st.button(f"슬롯 {i+1} 시작", key=f"slot_{i}"):
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
        
        # [실시간 무게 계산]
        max_w = 200 + sum([mercs_data.get(m, {'weight_bonus':0})['weight_bonus'] for m in player['mercs']])
        curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])
        
        # 상단 정보 바
        st.info(f"💰 {player['money']:,}냥 | 📦 {curr_w}/{max_w}근 | ⏰ {30 - int(time.time() - player['start_time']) % 30}초 후 다음 달")

        tab1, tab2, tab3 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 팔도 이동"])

        with tab1: # 저잣거리
            city = player['pos']
            st.subheader(f"📍 {city} 시장")
            for item in items_info:
                if item in market_data[city]:
                    current_p = get_price(item, city, items_info, market_data, settings)
                    stock = market_data[city][item]['stock']
                    col1, col2, col3 = st.columns([2,1,1])
                    col1.write(f"**{item}** ({stock}개)")
                    col2.write(f"{current_p:,}냥")
                    if col3.button("거래", key=f"btn_{item}"):
                        st.session_state.active_trade = {'name': item, 'price': current_p, 'weight': items_info[item]['w']}

            # [사용자 원본의 분할 체결 로직]
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                amt = st.number_input(f"{at['name']} 수량 입력 (99999 등)", 1, 1000000, 100)
                
                c_buy, c_sell = st.columns(2)
                if c_buy.button("🚀 분할 매수"):
                    log_p = st.empty()
                    logs = []
                    completed = 0
                    while completed < amt:
                        batch = min(100, amt - completed)
                        current_p = get_price(at['name'], city, items_info, market_data, settings)
                        
                        # 실제 무게/재화 체크
                        if player['money'] < current_p * batch or curr_w + (at['weight'] * batch) > max_w or market_data[city][at['name']]['stock'] < batch:
                            logs.append("❌ 중단 (자원/무게 부족)")
                            break
                        
                        player['money'] -= current_p * batch
                        player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + batch
                        market_data[city][at['name']]['stock'] -= batch
                        curr_w += at['weight'] * batch
                        completed += batch
                        
                        logs.append(f"📦 {at['name']} {batch}개 매수 중... ({completed}/{amt})")
                        log_p.markdown(f'<div style="background:#f0f2f6;padding:10px;border-radius:5px;">{"<br>".join(logs[-5:])}</div>', unsafe_allow_html=True)
                        time.sleep(0.01)
                    st.rerun()

        with tab2: # 용병 관리 (해고 포함)
            st.write("### 🛡️ 내 상단 용병")
            refund_rate = settings.get('fire_refund_rate', 0.5)
            for i, m_name in enumerate(player['mercs']):
                c_m, c_b = st.columns([3, 1])
                refund = int(mercs_data[m_name]['price'] * refund_rate)
                c_m.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
                if c_b.button(f"해고 ({refund:,}냥)", key=f"fire_{i}"):
                    player['money'] += refund
                    player['mercs'].pop(i)
                    st.rerun()

        with tab3: # 이동 로직
            # 사용자님의 기존 이동 로직 및 저장 버튼 삽입
            st.write("🚩 다른 마을로 이동하시겠습니까?")
            for country, cities in market_data.items(): # 단순화된 예시
                if st.button(f"{country} 이동"):
                    player['pos'] = country
                    st.rerun()
