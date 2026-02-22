import streamlit as st
import time
import json
import gspread
from google.oauth2.service_account import Credentials

# --- [수정] 모바일 화면 최적화 설정 ---
st.set_page_config(page_title="조선거상", layout="centered")

def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gspread"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None

doc = connect_gsheet()
# (중략: load_all_data 등 원본 로직 유지)

# --- [수정] 모바일 UI 배치 및 엔터키(버튼) 로직 ---
def main_game_ui():
    st.title("🏯 조선거상 미니")
    
    # 1. 상태 정보 (모바일에서 한눈에 보이게 요약)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("현재 위치", player['pos'])
    with col2:
        st.metric("잔액", f"{player['money']:,}냥")

    st.divider()

    # 2. 물건 대량 구매/판매 섹션 (키보드 입력 가능하게)
    st.subheader("🛒 물품 거래")
    
    # 아이템 선택
    item_list = list(ITEMS_INFO.keys())
    selected_item = st.selectbox("물건 선택", item_list)
    
    # [핵심] 숫자 직접 타이핑 입력창 (엔터 대신 버튼 클릭)
    # text_input으로 하면 모바일 키보드가 더 잘 뜨고 1000개 등 대량 입력이 쉽습니다.
    qty_str = st.text_input("수량 입력 (숫자만 입력)", value="1")
    
    col3, col4 = st.columns(2)
    with col3:
        if st.button("💰 매수하기", use_container_width=True):
            try:
                qty = int(qty_str)
                # 원본의 buy(selected_item, qty) 로직 호출
                st.success(f"{selected_item} {qty}개 매수 시도!")
            except:
                st.error("숫자를 정확히 입력하세요.")
                
    with col4:
        if st.button("📦 매도하기", use_container_width=True):
            try:
                qty = int(qty_str)
                # 원본의 sell(selected_item, qty) 로직 호출
                st.success(f"{selected_item} {qty}개 매도 시도!")
            except:
                st.error("숫자를 정확히 입력하세요.")

    # 3. 이동 섹션 (버튼 배치 정리)
    st.subheader("🚩 마을 이동")
    village_list = list(VILLAGES.keys())
    target_vil = st.selectbox("목적지 선택", village_list)
    if st.button(f"{target_vil}(으)로 이동", use_container_width=True):
        # 원본의 move_to(target_vil) 로직 호출
        st.info(f"{target_vil} 마을로 이동합니다.")

# 게임 실행
if doc:
    main_game_ui()
