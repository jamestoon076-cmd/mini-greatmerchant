import streamlit as st
import time
import math
import json
from datetime import datetime

# --- [중요] 매매 로직: 100개씩 끊어서 실제 체결 및 로그 출력 ---
def execution_trade(item_name, amount, price, weight, mode, player, market_data, city, max_w, curr_w):
    """
    사용자님의 원본 로직: 100개씩 실제로 체결하며 로그를 남기고 무게/돈을 실시간 업데이트
    """
    progress_placeholder = st.empty()
    log_messages = []
    
    # 실제 체결 가능 수량 계산 (무게 및 자금 제한)
    item_info = items_info[item_name]
    unit_weight = item_info['w']
    
    step = 100
    completed = 0
    
    while completed < amount:
        batch = min(step, amount - completed)
        
        if mode == "매수":
            # 매수 조건 체크: 돈 & 무게
            if player['money'] < price * batch:
                log_messages.append(f"❌ 자금 부족으로 중단 (체결: {completed}개)")
                break
            if curr_w + (unit_weight * batch) > max_w:
                log_messages.append(f"❌ 무게 초과로 중단 (체결: {completed}개)")
                break
            if market_data[city][item_name]['stock'] < batch:
                log_messages.append(f"❌ 재고 부족으로 중단 (체결: {completed}개)")
                break
                
            # 실제 데이터 반영
            player['money'] -= price * batch
            player['inventory'][item_name] = player['inventory'].get(item_name, 0) + batch
            market_data[city][item_name]['stock'] -= batch
            curr_w += unit_weight * batch
            
        else:  # 매도
            if player['inventory'].get(item_name, 0) < batch:
                log_messages.append(f"❌ 물량 부족으로 중단 (체결: {completed}개)")
                break
            
            player['money'] += price * batch
            player['inventory'][item_name] -= batch
            market_data[city][item_name]['stock'] += batch
            curr_w -= unit_weight * batch

        completed += batch
        log_messages.append(f"📦 {item_name} {batch}개 {mode} 중... ({completed}/{amount})")
        
        # 실시간 로그 출력 (원본 스타일)
        with progress_placeholder.container():
            st.markdown(f"""<div class="trade-progress">{"<br>".join(log_messages[-5:])}</div>""", unsafe_allow_html=True)
        time.sleep(0.01)

    return completed

# --- [신규] 용병 해고 로직 (Setting_Data 연동) ---
def fire_mercenary(player, merc_index, mercs_data, settings):
    merc_name = player['mercs'][merc_index]
    refund_rate = settings.get('fire_refund_rate', 0.5)
    refund_amount = int(mercs_data[merc_name]['price'] * refund_rate)
    
    player['money'] += refund_amount
    player['mercs'].pop(merc_index)
    st.warning(f"🛡️ {merc_name} 해고 완료! {refund_amount:,}냥이 환불되었습니다.")
    time.sleep(0.5)
    st.rerun()

# --- 인게임 UI 부분 (상단 정보 & 탭) ---
if st.session_state.game_started:
    player = st.session_state.player
    # 현재 무게 실시간 계산
    max_w = 200 + sum([mercs_data[m]['weight_bonus'] for m in player['mercs']])
    curr_w = sum([items_info[it]['w'] * qty for it, qty in player['inventory'].items() if it in items_info])

    # 상단 메트릭 (소지금, 무게, 시간초)
    m1, m2, m3, m4 = st.columns(4)
    money_placeholder = m1.empty()
    money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
    m2.metric("📦 무게", f"{curr_w}/{max_w}근")
    
    # 시간초 (30초 = 1달) 카운트다운
    elapsed = int(time.time() - player['start_time'])
    sec_left = 30 - (elapsed % 30)
    m3.metric("⏰ 다음 달", f"{sec_left}초")
    m4.metric("📅 일자", get_time_display(player))

    tab1, tab2, tab3, tab4 = st.tabs(["🛒 저잣거리", "🛡️ 용병 관리", "🚩 이동", "👤 정보"])

    with tab1: # 저잣거리 (수량 99999 입력 대응)
        city = player['pos']
        # [재고 기반 동적 시세 로직 적용 부분]
        # ... (생략: get_dynamic_price 호출) ...

        with st.expander("💎 물품 매매", expanded=True):
            target_item = st.selectbox("품목 선택", list(items_info.keys()))
            trade_amt = st.number_input("수량 입력 (최대치 입력 가능)", 1, 1000000, 100)
            
            c_buy, c_sell = st.columns(2)
            if c_buy.button("🚀 전량 매수"):
                # 실제 체결 함수 호출 (100개씩 로그 찍으며 처리)
                done = execution_trade(target_item, trade_amt, current_price, unit_weight, "매수", 
                                       player, market_data, city, max_w, curr_w)
                st.success(f"✅ 총 {done}개 매수 완료!")
                st.rerun()

    with tab2: # 용병 관리 (해고 기능)
        st.write("### 🛡️ 상단 용병단")
        if not player['mercs']:
            st.write("보유 용병 없음")
        else:
            for i, m_name in enumerate(player['mercs']):
                col_info, col_btn = st.columns([3, 1])
                col_info.write(f"**{m_name}** (+{mercs_data[m_name]['weight_bonus']}근)")
                if col_btn.button(f"해고", key=f"fire_{i}"):
                    fire_mercenary(player, i, mercs_data, settings)

    # ... (이하 이동 및 저장 로직 사용자 원본과 동일)
