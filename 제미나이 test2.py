import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import math
import time
from datetime import datetime
import pandas as pd

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="조선거상 미니", page_icon="🏯", layout="wide")

if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = []

# --- 2. 데이터 연동 ---
@st.cache_resource
def get_gsheet_client():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gspread"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds).open("조선거상_DB")
    except: return None

@st.cache_data(ttl=600)
def load_static_db():
    doc = get_gsheet_client()
    if not doc: return None
    try:
        settings = {r['변수명']: float(r['값']) for r in doc.worksheet("Setting_Data").get_all_records() if r.get('변수명')}
        items = {r['item_name']: {'base': int(r['base_price']), 'w': int(r['weight'])} for r in doc.worksheet("Item_Data").get_all_records()}
        mercs = {r['name']: {'price': int(r['price']), 'w_bonus': int(r['weight_bonus'])} for r in doc.worksheet("Balance_Data").get_all_records()}
        return settings, items, mercs
    except: return None

# --- 3. 핵심 엔진 함수 ---
def get_status(player, items_info, mercs_info):
    curr_w = sum(int(count) * items_info.get(item, {}).get('w', 0) for item, count in player['inventory'].items())
    max_w = 1000 + sum(mercs_info.get(m, {}).get('w_bonus', 0) for m in player['mercs'])
    return curr_w, max_w

def calculate_price(item_name, stock, items_info, settings):
    base = items_info.get(item_name, {}).get('base', 100)
    vol = settings.get('volatility', 5000) / 1000
    try:
        curr_s = int(str(stock).replace(',','')) if stock else 5000
    except: curr_s = 5000
    ratio = 5000 / max(1, curr_s) 
    return int(base * max(0.5, min(20.0, math.pow(ratio, (vol / 4)))))

def sync_engine(doc):
    if 'start_time' not in st.session_state: st.session_state.start_time = time.time()
    elapsed = int(time.time() - st.session_state.start_time)
    c_month = elapsed // 180
    if 'last_reset_month' not in st.session_state: st.session_state.last_reset_month = 0
    if c_month > st.session_state.last_reset_month:
        try:
            st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            st.session_state.last_reset_month = c_month
        except: pass
    return (c_month // 12)+1, (c_month % 12)+1, ((elapsed % 180) // 45)+1, 45-(elapsed % 45)

# --- 4. 메인 로직 ---
static_data = load_static_db()
if static_data:
    settings, items_info, mercs_info = static_data
    doc = get_gsheet_client()
    year, month, week, remains = sync_engine(doc)

    if 'game_started' not in st.session_state or not st.session_state.game_started:
        st.title("🏯 조선거상 미니")
        slots = doc.worksheet("Player_Data").get_all_records()
        for i, p in enumerate(slots):
            if st.button(f"슬롯 {i+1} 접속 ({p['pos']})"):
                st.session_state.player = {
                    'money': int(p['money']), 'pos': p['pos'],
                    'inventory': json.loads(p['inventory']) if p['inventory'] else {},
                    'mercs': json.loads(p['mercs']) if p['mercs'] else []
                }
                st.session_state.slot_num = i+1
                st.session_state.game_started = True
                st.rerun()
    else:
        player = st.session_state.player
        c_w, m_w = get_status(player, items_info, mercs_info)

        # 상단 UI
        st.markdown(f"""
        <div style="background:#1a1a1a; color:#0f0; padding:15px; border-radius:10px; border:2px solid #444;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2 style="margin:0; color:white;">📅 {year}년 {month}월 {week}주차</h2>
                <h3 style="margin:0; color:#ff0;">⏱️ {remains}초 남음</h3>
            </div>
            <p style="margin:10px 0 0 0;">📍 <b>{player['pos']}</b> | 💰 <b>{player['money']:,}냥</b> | ⚖️ <b>{c_w:,} / {m_w:,} 斤</b></p>
        </div>""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 저잣거리", "🚩 이동", "⚔️ 용병 주막", "📊 통계 및 분석", "💾 저장"])

        with tab1: # 저잣거리
            if 'villages' not in st.session_state: st.session_state.villages = doc.worksheet("Village_Data").get_all_records()
            v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            v_data = st.session_state.villages[v_idx]

            for item in items_info.keys():
                s_val = int(v_data.get(item, 0)) if str(v_data.get(item,0)).isdigit() else 0
                price = calculate_price(item, s_val, items_info, settings)
                my_s = int(player['inventory'].get(item, 0))
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{item}** (재고:{s_val:,} | 보유:{my_s:,})")
                c2.write(f"**{price:,}냥**")
                if c3.button("거래", key=f"t_{item}"): st.session_state.active_trade = item
            
            if 'active_trade' in st.session_state:
                at = st.session_state.active_trade
                st.divider()
                st.subheader(f"📦 {at} 매매 실행")
                amt = st.number_input("수량", 1, 100000, 100)
                b_col, s_col = st.columns(2)
                
                if st.session_state.trade_logs:
                    st.code("\n".join(st.session_state.trade_logs[-5:]))

                if b_col.button("일괄 매수 시작"):
                    done = 0
                    st.session_state.trade_logs = []
                    while done < amt:
                        curr_weight, max_weight = get_status(player, items_info, mercs_info)
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, amt - done)
                        if curr_weight + (batch * items_info[at]['w']) > max_weight:
                            batch = max(0, int((max_weight - curr_weight) // items_info[at]['w']))
                            if batch <= 0: st.session_state.trade_logs.append("🛑 무게 초과!"); break
                        if cur_s < batch: batch = cur_s
                        if player['money'] < (p_now * batch) or batch <= 0: break
                        player['money'] -= (p_now * batch)
                        player['inventory'][at] = player['inventory'].get(at, 0) + batch
                        v_data[at] = int(v_data[at]) - batch
                        done += batch
                        st.session_state.trade_logs.append(f"✅ {done}/{amt}개 체결... (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

                if s_col.button("일괄 매도 시작"):
                    done = 0
                    st.session_state.trade_logs = []
                    target = min(amt, player['inventory'].get(at, 0))
                    while done < target:
                        cur_s = int(v_data[at])
                        p_now = calculate_price(at, cur_s, items_info, settings)
                        batch = min(100, target - done)
                        player['money'] += (p_now * batch)
                        player['inventory'][at] -= batch
                        v_data[at] = int(v_data[at]) + batch
                        done += batch
                        st.session_state.trade_logs.append(f"💰 {done}/{target}개 판매... (단가: {p_now:,}냥)")
                        time.sleep(0.01)
                    doc.worksheet("Village_Data").update_cell(v_idx+2, list(v_data.keys()).index(at)+1, v_data[at])
                    st.rerun()

        with tab2: # 이동
            st.subheader("🚩 팔도 강산 이동")
            cols = st.columns(3)
            for idx, v in enumerate(st.session_state.villages):
                if v['village_name'] == player['pos']: continue
                with cols[idx % 3]:
                    if st.button(f"🚩 {v['village_name']} 이동", use_container_width=True, key=f"mv_{v['village_name']}"):
                        player['pos'] = v['village_name']
                        st.rerun()

        with tab4: # 통계 및 분석 (요청 기능 추가)
            st.subheader("📈 상단 분석 보고서")
            
            # 자산 계산
            current_v_idx = next(i for i, v in enumerate(st.session_state.villages) if v['village_name'] == player['pos'])
            current_v_data = st.session_state.villages[current_v_idx]
            
            total_inv_value = 0
            inventory_stats = []
            
            for item, count in player['inventory'].items():
                if count <= 0: continue
                # 현재 위치 기준 시세 및 무게 계산
                cur_s = int(current_v_data.get(item, 5000))
                p_now = calculate_price(item, cur_s, items_info, settings)
                val = count * p_now
                weight = count * items_info[item]['w']
                total_inv_value += val
                
                inventory_stats.append({
                    "품목": item,
                    "보유 수량": f"{count:,}개",
                    "총 무게": f"{weight:,} 斤",
                    "현재지 단가": f"{p_now:,}냥",
                    "예상 판매가": f"{val:,}냥"
                })
            
            total_assets = player['money'] + total_inv_value
            
            # 요약 지표
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 총 자산 (현금+물품)", f"{total_assets:,}냥")
            m2.metric("💵 보유 현금", f"{player['money']:,}냥")
            m3.metric("📦 물품 가치", f"{total_inv_value:,}냥")
            
            st.divider()
            
            # 플레이어 인벤토리 현황 표시
            st.markdown("#### 🎒 내 인벤토리 상세 (순익 분석)")
            if inventory_stats:
                st.table(pd.DataFrame(inventory_stats))
            else:
                st.info("인벤토리가 비어 있습니다.")

            st.divider()
            
            # 전국 시장 분석 (최고가/최저가 도시 포함)
            st.markdown("#### 🔍 전국 품목 수급 및 시세 알림")
            market_analysis = []
            for item in items_info.keys():
                prices = []
                total_stock = 0
                for v in st.session_state.villages:
                    s = int(v.get(item, 5000))
                    p = calculate_price(item, s, items_info, settings)
                    prices.append((p, v['village_name']))
                    total_stock += s
                
                prices.sort() # 가격순 정렬
                min_p, min_v = prices[0]
                max_p, max_v = prices[-1]
                
                market_analysis.append({
                    "품목": item,
                    "전국 재고": f"{total_stock:,}",
                    "최저가 도시": f"{min_v} ({min_p:,}냥)",
                    "최고가 도시": f"{max_v} ({max_p:,}냥)",
                    "현재 수익률": f"{((max_p/min_p)-1)*100:.1f}%"
                })
            st.table(pd.DataFrame(market_analysis))

        with tab5: # 저장
            if st.button("💾 데이터 서버 저장"):
                ws = doc.worksheet("Player_Data")
                r_idx = st.session_state.slot_num + 1
                save_data = [st.session_state.slot_num, player['money'], player['pos'], 
                             json.dumps(player['mercs'], ensure_ascii=False), 
                             json.dumps(player['inventory'], ensure_ascii=False), 
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
                ws.update(f"A{r_idx}:F{r_idx}", [save_data])
                st.success("저장 완료!")
