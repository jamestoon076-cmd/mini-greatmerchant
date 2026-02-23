import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime

# --- 1. 시세 변동 핵심 로직 (volatility 반영) ---
def get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings):
    """재고가 적으면 비싸지고, 많으면 싸지는 volatility 기반 수식"""
    base_price = items_info[item_name]['base']
    max_s = item_max_stocks.get(item_name, 100)
    vol = settings.get('volatility', 5000) / 1000
    
    # 재고가 없거나 잘못된 데이터일 경우 5배 폭등
    try:
        curr_s = int(stock)
        if curr_s <= 0: return base_price * 5
    except: return base_price
    
    # 재고 비율에 따른 가격 지수 계산
    ratio = max_s / curr_s
    factor = math.pow(ratio, (vol / 4))
    
    # 최소 0.5배 ~ 최대 20배 범위 내에서 가격 결정
    return int(base_price * max(0.5, min(20.0, factor)))

# --- 2. 시간 표시 로직 (초 단위 포함) ---
def get_time_display_with_sec(start_time):
    elapsed = int(time.time() - start_time)
    months_passed = elapsed // 30 # 30초 = 1달
    seconds_left = 30 - (elapsed % 30)
    year = 1592 + (months_passed // 12)
    month = (months_passed % 12) + 1
    return f"{year}년 {month}월 ({seconds_left}초 후 다음 달)"

# --- 3. 데이터 로드 및 메인 루프 ---
# (사용자님의 기존 load_data 함수 및 세션 관리 로직 유지)
# ... [중략: 기존 gspread 연동 및 슬롯 선택 부분] ...

if st.session_state.game_started:
    player = st.session_state.player
    # 상단 정보바 계산 (무게 보너스 합산)
    max_weight = 200 + sum([mercs_data.get(m, {}).get('weight_bonus', 0) for m in player['mercs']])
    curr_weight = sum([items_info.get(it, {}).get('w', 0) * qty for it, qty in player['inventory'].items() if it in items_info])

    # [상단 UI 영역]
    st.info(f"📍 **{player['pos']}** | 💰 **{player['money']:,}냥** | 📦 **{curr_weight}/{max_weight}근** | ⏰ **{get_time_display_with_sec(player['start_time'])}**")

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🛡️ 용병 고용소", "🚩 팔도 이동", "👤 상단 정보"])

    with tab1: # 🛒 저잣거리 (수정된 가격변동 적용)
        # 현재 마을 시트 데이터 로드
        v_data = next((v for r in regions.values() for v in r if v['village_name'] == player['pos']), None)
        
        if v_data:
            st.write(f"### {player['pos']} 특산물 시세")
            for item_name, info in items_info.items():
                stock = v_data.get(item_name, 0)
                if stock == "": continue # 재고 데이터 없는 품목 패스
                
                # 핵심: volatility와 재고를 반영한 가격 계산
                current_price = get_dynamic_price(item_name, stock, item_max_stocks, items_info, settings)
                
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item_name}** ({stock}개)")
                c2.write(f"{current_price:,}냥")
                if c3.button("거래", key=f"trade_{item_name}"):
                    st.session_state.active_trade = {'name': item_name, 'price': current_price, 'weight': info['w']}

            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                with st.container(border=True):
                    st.write(f"**{at['name']} 매매** (무게: {at['weight']}근)")
                    amt = st.number_input("수량 입력", 1, 100000, 1, key="trade_amt")
                    
                    col_buy, col_sell = st.columns(2)
                    if col_buy.button("매수하기"):
                        total_cost = at['price'] * amt
                        if player['money'] >= total_cost and curr_weight + (at['weight'] * amt) <= max_weight:
                            player['money'] -= total_cost
                            player['inventory'][at['name']] = player['inventory'].get(at['name'], 0) + amt
                            st.rerun()
                        else: st.error("❌ 자금 부족 또는 무게 초과!")
                        
                    if col_sell.button("매도하기"):
                        if player['inventory'].get(at['name'], 0) >= amt:
                            player['money'] += at['price'] * amt
                            player['inventory'][at['name']] -= amt
                            st.rerun()
                        else: st.error("❌ 보유 수량 부족!")

    with tab2: # 🛡️ 용병 고용소 (원본 코드 보강)
        if player['pos'] == "용병 고용소":
            st.write("### 🛡️ 상단 용병 고용")
            for m_name, m_info in mercs_data.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.write(f"**{m_name}**\n(+{m_info['weight_bonus']}근)")
                col2.write(f"{m_info['price']:,}냥")
                if col3.button("고용", key=f"hire_{m_name}"):
                    if len(player['mercs']) < settings.get('max_mercenaries', 5) and player['money'] >= m_info['price']:
                        player['money'] -= m_info['price']
                        player['mercs'].append(m_name)
                        st.success(f"{m_name}을 고용했습니다!")
                        st.rerun()
                    else: st.error("고용 불가 (돈 부족 또는 정원 초과)")
        else:
            st.warning("📍 '용병 고용소' 마을로 이동해야 용병을 고용할 수 있습니다.")

    with tab3: # 🚩 팔도 이동 (국가별 그룹화 적용)
        countries = list(regions.keys())
        selected_tabs = st.tabs(countries)
        for i, country in enumerate(countries):
            with selected_tabs[i]:
                for v in regions[country]:
                    if v['village_name'] == player['pos']: continue
                    col_v, col_btn = st.columns([3, 1])
                    col_v.write(f"**{v['village_name']}**")
                    if col_btn.button("이동", key=f"move_{country}_{v['village_name']}"):
                        player['pos'] = v['village_name']
                        st.rerun()

    with tab4: # 👤 상단 정보 (인벤토리 상세 출력)
        st.write("### 🎒 보유 물품 목록")
        if any(qty > 0 for qty in player['inventory'].values()):
            for item, qty in player['inventory'].items():
                if qty > 0: st.write(f"- {item}: {qty}개")
        else: st.write("보유한 물품이 없습니다.")
        
        st.divider()
        if st.button("💾 현재 상태 저장", use_container_width=True):
            # 저장 로직 (사용자 원본 save_player_data 활용)
            st.success("저장되었습니다!")
