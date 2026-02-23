import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# --- 1. 유틸리티 함수 (안전한 숫자 변환) ---
def safe_int(value, default=0):
    if value == "" or value is None or str(value).strip() == "":
        return default
    try:
        return int(float(value))
    except ValueError:
        return default

# --- 2. 시세 계산 로직 (가격변동개선.py 기준) ---
def get_current_price(item_name, current_stock, items_info, settings):
    if item_name not in items_info: return 0
    base = items_info[item_name]['base']
    initial_stock = 100 # 기준 재고 (필요시 DB화)
    
    if current_stock <= 0:
        return int(base * settings.get('max_price_rate', 3.0))
    
    stock_ratio = current_stock / initial_stock
    # 재고 비율에 따른 가격 배율
    if stock_ratio < 0.5: factor = 2.5
    elif stock_ratio < 1.0: factor = 1.8
    else: factor = 1.0
        
    return int(base * factor)

# --- 3. 데이터 로드 및 앱 시작 ---
@st.cache_resource
def get_db():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

doc = get_db()
if doc:
    # 데이터 프리로딩
    settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
    mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in doc.worksheet("Balance_Data").get_all_records()}
    
    # 마을 데이터 (국가별 시트가 없을 경우 기본 Village_Data 시트 사용)
    all_villages = doc.worksheet("Village_Data").get_all_records()
    
    # 세션 관리
    if 'player' not in st.session_state:
        # 로그인/슬롯 선택 로직 (간략화)
        p_data = doc.worksheet("Player_Data").get_all_records()[0] # 1번 슬롯 예시
        st.session_state.player = {
            'slot': p_data['slot'], 'money': int(p_data['money']), 'pos': p_data['pos'],
            'mercs': json.loads(p_data['mercs']) if p_data['mercs'] else [],
            'inv': json.loads(p_data['inventory']) if p_data['inventory'] else {}
        }

    p = st.session_state.player

    # --- UI 레이아웃 ---
    st.title(f"🏯 조선거상 ({p['pos']})")
    
    # 상단 상태바
    curr_w = sum(p['inv'].get(it, 0) * items_info[it]['w'] for it in p['inv'] if it in items_info)
    max_w = 200 + sum(mercs_db[m]['w_bonus'] for m in p['mercs'] if m in mercs_db)
    
    col_stat1, col_stat2 = st.columns(2)
    col_stat1.metric("💰 소지금", f"{p['money']:,}냥")
    col_stat2.metric("⚖️ 상단 무게", f"{curr_w} / {max_w} 근")

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "👨‍전 상단 정보", "⚔️ 고용소"])

    # [TAB 1: 저잣거리]
    with tab1:
        v_data = next((v for v in all_villages if v['village_name'] == p['pos']), None)
        if v_data and p['pos'] != "용병 고용소":
            st.subheader(f"🏬 {p['pos']} 상점")
            for item in items_info.keys():
                stock = safe_int(v_data.get(item, 0))
                price = get_current_price(item, stock, items_info, settings)
                
                with st.expander(f"{item} (가격: {price:,}냥 | 재고: {stock}개)"):
                    qty = st.number_input("수량", min_value=1, max_value=max(1, stock), key=f"q_{item}")
                    c_b, c_s = st.columns(2)
                    if c_b.button("매수", key=f"buy_{item}"):
                        if p['money'] >= price * qty and curr_w + (items_info[item]['w'] * qty) <= max_w:
                            p['money'] -= price * qty
                            p['inv'][item] = p['inv'].get(item, 0) + qty
                            st.rerun()
                        else: st.error("자금 또는 무게 부족!")
        else:
            st.info("이곳에는 상점이 없습니다. 다른 마을로 이동하세요.")

    # [TAB 2: 이동 (용병 고용소 -> 저잣거리 문제 해결)]
    with tab2:
        st.subheader("🚩 팔도강산 이동")
        # 현재 위치를 제외한 모든 마을 목록 표시
        for v in all_villages:
            if v['village_name'] == p['pos']: continue
            col_v, col_m = st.columns([3, 1])
            col_v.write(f"**{v['village_name']}**")
            if col_m.button("이동하기", key=f"mv_{v['village_name']}"):
                p['pos'] = v['village_name']
                st.rerun()

    # [TAB 3: 상단 정보 (인벤토리 및 용병 해고)]
    with tab3:
        st.subheader("📦 내 상단 정보")
        
        # 1. 인벤토리 섹션
        st.write("**[소지 물품]**")
        inv_items = {k: v for k, v in p['inv'].items() if v > 0}
        if inv_items:
            for it, count in inv_items.items():
                st.write(f"- {it}: {count}개 ({items_info[it]['w'] * count}근)")
        else:
            st.caption("가방이 비어있습니다.")
        
        st.divider()
        
        # 2. 용병단 섹션 (해고 기능)
        st.write("**[우리 용병단]**")
        if p['mercs']:
            for idx, m_name in enumerate(p['mercs']):
                col_m_info, col_m_btn = st.columns([3, 1])
                col_m_info.write(f"{idx+1}. {m_name} (+{mercs_db[m_name]['w_bonus']}근)")
                if col_m_btn.button("해고", key=f"fire_{idx}"):
                    # 해고 시 무게 체크 (현재 짐이 너무 많으면 해고 불가)
                    potential_max_w = max_w - mercs_db[m_name]['w_bonus']
                    if curr_w > potential_max_w:
                        st.error("짐이 너무 무거워 용병을 보낼 수 없습니다!")
                    else:
                        p['mercs'].pop(idx)
                        st.success(f"{m_name}을(를) 해고했습니다.")
                        st.rerun()
        else:
            st.caption("고용된 용병이 없습니다.")

    # [TAB 4: 고용소]
    with tab4:
        if p['pos'] == "용병 고용소":
            st.subheader("⚔️ 용병 고용")
            for m_name, info in mercs_db.items():
                col1, col2 = st.columns([3, 1])
                col1.write(f"**{m_name}** (💰 {info['price']:,}냥)")
                if col2.button("고용하기", key=f"hire_{m_name}"):
                    if len(p['mercs']) < settings.get('max_mercenaries', 5) and p['money'] >= info['price']:
                        p['money'] -= info['price']
                        p['mercs'].append(m_name)
                        st.rerun()
                    else: st.error("고용 불가 (인원 초과 또는 자금 부족)")
        else:
            st.warning("용병 고용은 '용병 고용소' 마을에서만 가능합니다.")
            if st.button("용병 고용소로 즉시 이동"):
                p['pos'] = "용병 고용소"
                st.rerun()
