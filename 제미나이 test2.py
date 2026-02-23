import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

# 1. 시트 안전 로드 함수
def get_ws(doc, name):
    try: return doc.worksheet(name)
    except:
        for s in doc.worksheets():
            if name in s.title: return s
        return None

# 2. 가격 변동 로직 (가격변동개선.py)
def calc_price(item, stock, items_info, settings):
    base = items_info[item]['base']
    ratio = stock / 100 # 기준재고 100
    if ratio < 0.5: factor = 2.5
    elif ratio < 1.0: factor = 1.8
    else: factor = 1.0
    return int(base * factor)

# --- 메인 로직 시작 ---
doc = connect_db() # 연결 로직 생략 (기존과 동일)
if doc:
    # 데이터 로드 (에러 방지 적용)
    set_ws = get_ws(doc, "Setting_Data")
    item_ws = get_ws(doc, "Item_Data")
    vill_ws = get_ws(doc, "Village_Data")
    merc_ws = get_ws(doc, "Balance_Data")
    
    settings = {r['변수명']: float(r['값']) for r in set_ws.get_all_records() if r.get('변수명')}
    items_info = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in item_ws.get_all_records()}
    mercs_db = {r['name']: {'price': int(r['price']), 'w_bonus': int(r.get('weight_bonus', 0))} for r in merc_ws.get_all_records()}
    all_villages = vill_ws.get_all_records()

    # 플레이어 세션 (인벤토리 및 용병 정보 포함)
    if 'player' not in st.session_state:
        st.session_state.player = { 'pos': '한양', 'money': 100000, 'inv': {}, 'mercs': [] }
    
    p = st.session_state.player

    # --- 상단 정보 레이아웃 ---
    st.title(f"🏯 조선거상 미니")
    
    # 상단 정보 요약 (소지금, 무게, 용병수)
    curr_w = sum(p['inv'].get(i, 0) * items_info[i]['w'] for i in p['inv'] if i in items_info)
    max_w = 200 + sum(mercs_db[m]['w_bonus'] for m in p['mercs'] if m in mercs_db)
    
    st.markdown(f"""
    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <b>📍 현재 위치:</b> {p['pos']} | <b>💰 소지금:</b> {p['money']:,}냥 | <b>⚖️ 무게:</b> {curr_w}/{max_w}근
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🚩 이동", "🎒 내 상단 정보", "⚔️ 용병소"])

    with tab1: # 저잣거리
        if p['pos'] == "용병 고용소":
            st.info("이곳은 고용소입니다. 상점을 이용하려면 다른 마을로 이동하세요.")
        else:
            v_data = next((v for v in all_villages if v['village_name'] == p['pos']), None)
            for item in items_info.keys():
                stock = int(v_data.get(item, 0)) if v_data.get(item) else 0
                price = calc_price(item, stock, items_info, settings)
                
                with st.expander(f"{item} (시세: {price:,}냥)"):
                    qty = st.number_input("수량", 1, 999, key=f"q_{item}")
                    c1, c2 = st.columns(2)
                    if c1.button("매수", key=f"b_{item}"):
                        if p['money'] >= price * qty and curr_w + (items_info[item]['w'] * qty) <= max_w:
                            p['money'] -= price * qty
                            p['inv'][item] = p['inv'].get(item, 0) + qty
                            st.rerun()
                    if c2.button("매도", key=f"s_{item}"):
                        if p['inv'].get(item, 0) >= qty:
                            p['money'] += price * qty
                            p['inv'][item] -= qty
                            st.rerun()

    with tab2: # 이동 (고용소 <-> 마을 자유 이동)
        st.subheader("🚩 행선지 선택")
        for v in all_villages:
            if v['village_name'] == p['pos']: continue
            col_v, col_btn = st.columns([3, 1])
            col_v.write(f"**{v['village_name']}**")
            if col_btn.button("이동", key=f"move_{v['village_name']}"):
                p['pos'] = v['village_name']
                st.rerun()

    with tab3: # 내 상단 정보 (인벤토리 + 용병 해고)
        st.subheader("🎒 보따리 및 용병단")
        
        # 인벤토리
        st.write("**[소지품]**")
        for it, count in p['inv'].items():
            if count > 0: st.write(f"- {it}: {count}개")
        
        st.divider()
        
        # 용병 목록 및 해고
        st.write("**[고용된 용병]**")
        for idx, m_name in enumerate(p['mercs']):
            c_info, c_btn = st.columns([3, 1])
            c_info.write(f"{m_name} (+{mercs_db[m_name]['w_bonus']}근)")
            if c_btn.button("해고", key=f"fire_{idx}"):
                # 해고 시 무게 초과 체크
                if curr_w > max_w - mercs_db[m_name]['w_bonus']:
                    st.error("무게가 너무 무거워 용병을 보낼 수 없습니다!")
                else:
                    p['mercs'].pop(idx)
                    st.rerun()

    with tab4: # 용병소
        if p['pos'] != "용병 고용소":
            st.warning("용병 고용소로 이동해야 합니다.")
        else:
            for m_name, info in mercs_db.items():
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{m_name}** ({info['price']:,}냥)")
                if c2.button("고용", key=f"h_{m_name}"):
                    if len(p['mercs']) < settings['max_mercenaries'] and p['money'] >= info['price']:
                        p['money'] -= info['price']
                        p['mercs'].append(m_name)
                        st.rerun()
