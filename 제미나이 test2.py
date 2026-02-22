import time
import json
import sys
import math
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 유틸리티 함수 (가장 먼저 정의) ---
def safe_int_input(prompt, min_val=None, max_val=None):
    """사용자로부터 안전하게 정수 입력을 받는 함수"""
    while True:
        try:
            line = input(prompt).strip()
            if not line: continue
            val = int(line)
            if min_val is not None and val < min_val:
                print(f"⚠️ {min_val} 이상의 숫자를 입력하세요.")
                continue
            if max_val is not None and val > max_val:
                print(f"⚠️ {max_val} 이하의 숫자를 입력하세요.")
                continue
            return val
        except ValueError:
            print("❌ 숫자만 입력하세요.")

# --- 2. 시트 연결 ---
def connect_gsheet():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        json_path = 'c:/Users/오리/Desktop/거상게임/credentials.json'
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        return gspread.authorize(creds).open("조선거상_DB")
    except Exception as e:
        print(f"❌ 연결 실패: {e}"); sys.exit()

doc = connect_gsheet()

# --- 3. 데이터 로드 및 초기화 ---
def load_all_data():
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
        initial_stocks = {}
        for row in vil_vals[1:]:
            v_name = row[0].strip()
            if not v_name: continue
            villages[v_name] = {'items': {}, 'x': int(row[1]), 'y': int(row[2])}
            initial_stocks[v_name] = {}
            if v_name != "용병 고용소":
                for i in range(3, len(headers)):
                    if i < len(row) and headers[i] in items_info and row[i]:
                        stock = int(row[i])
                        villages[v_name]['items'][headers[i]] = stock
                        initial_stocks[v_name][headers[i]] = stock
        
        play_ws = doc.worksheet("Player_Data")
        slots = play_ws.get_all_records()
        print("\n=== 💾 세이브 슬롯 선택 ===")
        for s in slots:
            print(f"[{s['slot']}] 위치: {s['pos']} | 잔액: {int(s.get('money', 0)):,}냥")
        
        # 이제 safe_int_input이 위에서 정의되었으므로 에러가 나지 않습니다.
        choice = safe_int_input("\n슬롯 번호 입력 >> ", 1, len(slots))
        p_row = next(s for s in slots if s['slot'] == choice)
        
        player = {
            'slot': choice, 'money': int(p_row.get('money', 0)), 'pos': str(p_row.get('pos', '한양')),
            'inv': json.loads(p_row.get('inventory', '{}')) if p_row.get('inventory') else {},
            'mercs': json.loads(p_row.get('mercs', '[]')) if p_row.get('mercs') else [],
            'year': int(p_row.get('year', 1)), 'month': int(p_row.get('month', 1)), 'week': int(p_row.get('week', 1)),
            'last_tick': time.time(),
            'stats': {'total_bought': 0, 'total_sold': 0, 'total_spent': 0, 'total_earned': 0, 'trade_count': 0}
        }
        return settings, items_info, merc_data, villages, initial_stocks, player
    except Exception as e:
        print(f"❌ 데이터 로드 오류: {e}"); sys.exit()

# 글로벌 변수 초기화
SETTINGS, ITEMS_INFO, MERC_DATA, VILLAGES, INITIAL_STOCKS, player = load_all_data()
market_data = {v: {i: {'stock': q, 'price': 0, 'old_price': 0} for i, q in data['items'].items()} for v, data in VILLAGES.items()}

# --- 4. 게임 로직 함수 ---
def get_weight():
    cw = sum(player['inv'].get(i, 0) * ITEMS_INFO[i]['w'] for i in player['inv'] if i in ITEMS_INFO)
    tw = 200 + sum(MERC_DATA[m]['w_bonus'] for m in player['mercs'] if m in MERC_DATA)
    return cw, tw

def update_prices():
    vol = SETTINGS.get('volatility', 500)
    for v_name, v_data in market_data.items():
        for i_name, i_info in v_data.items():
            i_info['old_price'] = i_info['price']
            base = ITEMS_INFO[i_name]['base']
            stock = i_info['stock']
            price = int(base * (1 + (vol / (stock + 10)))) if stock > 0 else base * 10
            # 계절 효과
            m = player['month']
            if m in [3,4,5] and i_name in ['인삼', '소가죽', '염색가죽']: price = int(price * 1.2)
            elif m in [6,7,8] and i_name == '비단': price = int(price * 1.3)
            elif m in [9,10,11] and i_name == '쌀': price = int(price * 1.3)
            elif m in [12,1,2] and i_name == '가죽갑옷': price = int(price * 1.5)
            i_info['price'] = price

def update_game_time():
    now = time.time()
    if now - player['last_tick'] >= 45: # 45초마다 1주
        player['last_tick'] = now
        player['week'] += 1
        if player['week'] > 4:
            player['week'] = 1
            player['month'] += 1
            print("\n📦 [월초 리셋] 새로운 달이 시작되어 재고가 초기화되었습니다!")
            for v_name, items in INITIAL_STOCKS.items():
                for i_name, stock in items.items():
                    market_data[v_name][i_name]['stock'] = stock
            if player['month'] > 12:
                player['month'] = 1; player['year'] += 1
        return True
    return False

# --- 5. 명령 함수 ---
def buy():
    if player['pos'] == "용병 고용소":
        mercs = list(MERC_DATA.keys())
        for i, m in enumerate(mercs, 1):
            check = "✓" if m in player['mercs'] else " "
            print(f"[{i}][{check}] {m:<8} | {MERC_DATA[m]['price']:,}냥 | 보너스: +{MERC_DATA[m]['w_bonus']}근")
        idx = safe_int_input("\n고용할 번호 (0:취소) >> ", 0, len(mercs)) - 1
        if idx < 0: return
        m_name = mercs[idx]
        if m_name in player['mercs']: print("❌ 이미 보유 중!")
        elif player['money'] >= MERC_DATA[m_name]['price']:
            player['money'] -= MERC_DATA[m_name]['price']
            player['mercs'].append(m_name)
            print(f"⚔️ {m_name} 고용 완료!")
        else: print("❌ 잔액 부족")
    else:
        items = list(market_data[player['pos']].keys())
        if not items: print("❌ 판매 품목 없음"); return
        idx = safe_int_input("\n품목 번호 >> ", 1, len(items)) - 1
        item_name = items[idx]
        cw, tw = get_weight()
        max_q = min(market_data[player['pos']][item_name]['stock'], 
                    player['money'] // market_data[player['pos']][item_name]['price'],
                    (tw - cw) // ITEMS_INFO[item_name]['w'])
        print(f"💰 최대 {max_q}개 구매 가능")
        want = safe_int_input("구매 수량 >> ", 1, max_q if max_q > 0 else 1)
        
        total = 0
        while total < want:
            update_prices()
            p = market_data[player['pos']][item_name]['price']
            batch = min(100, want - total)
            for _ in range(batch):
                player['money'] -= p
                player['inv'][item_name] = player['inv'].get(item_name, 0) + 1
                market_data[player['pos']][item_name]['stock'] -= 1
                total += 1
            print(f"  ➤ {total}/{want} 구매 중... ({p:,}냥)")
            time.sleep(0.1)

def sell():
    owned = [i for i in player['inv'] if player['inv'].get(i, 0) > 0]
    if not owned: print("❌ 팔 물건이 없습니다."); return
    for i, name in enumerate(owned, 1):
        print(f"[{i}] {name:<8} | 보유: {player['inv'][name]} | 시세: {market_data[player['pos']][name]['price']:,}냥")
    print("[999] 전량 매도")
    choice = safe_int_input("\n판매할 번호 >> ", 1, 999)
    
    target_list = owned if choice >= 999 else [owned[choice-1]]
    for item_name in target_list:
        actual_target = player['inv'][item_name]
        total_sold = 0
        while total_sold < actual_target:
            update_prices()
            p = market_data[player['pos']][item_name]['price']
            batch = min(100, actual_target - total_sold)
            for _ in range(batch):
                player['money'] += p
                player['inv'][item_name] -= 1
                market_data[player['pos']][item_name]['stock'] += 1
                total_sold += 1
            print(f"  ➤ {item_name} {total_sold}/{actual_target} 판매 중... ({p:,}냥)")
            time.sleep(0.05)

def save_game():
    try:
        play_ws = doc.worksheet("Player_Data")
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_values = [player['slot'], player['money'], player['pos'], 
                       json.dumps(player['mercs']), json.dumps(player['inv']), now,
                       player['week'], player['month'], player['year']]
        play_ws.update(f'A{player["slot"]+1}:I{player["slot"]+1}', [save_values])
        print(f"✅ 저장 완료! ({now})")
    except Exception as e: print(f"❌ 저장 실패: {e}")

# --- 6. 메인 루프 ---
if __name__ == "__main__":
    while True:
        update_game_time()
        update_prices()
        cw, tw = get_weight()
        print(f"\n📅 {player['year']}년 {player['month']}월 {player['week']}주 | 🏠 {player['pos']} | 💰 {player['money']:,}냥 | ⚖️ {cw}/{tw}근")
        print("-" * 60)
        if player['pos'] != "용병 고용소":
            for i, (name, d) in enumerate(market_data[player['pos']].items(), 1):
                icon = "▲" if d['price'] > d['old_price'] and d['old_price'] != 0 else "▼" if d['price'] < d['old_price'] and d['old_price'] != 0 else "■"
                print(f"[{i}] {name:<8} | 가격: {d['price']:,}냥 {icon} | 재고: {d['stock']}")
        
        cmd = input("\n[1]구매 [2]판매 [3]이동 [4]인벤 [5]저장 [0]종료 >> ")
        if cmd == '1': buy()
        elif cmd == '2': sell()
        elif cmd == '3':
            towns = list(VILLAGES.keys())
            for i, t in enumerate(towns, 1):
                dist = math.sqrt((VILLAGES[player['pos']]['x']-VILLAGES[t]['x'])**2 + (VILLAGES[player['pos']]['y']-VILLAGES[t]['y'])**2)
                cost = int(dist * SETTINGS.get('travel_cost', 15))
                print(f"{i}. {t} ({cost:,}냥)")
            idx = safe_int_input("이동 번호 >> ", 1, len(towns)) - 1
            player['pos'] = towns[idx]; print(f"🚚 {towns[idx]} 도착!")
        elif cmd == '4':
            print(f"\n📦 인벤토리: {player['inv']}\n⚔️ 용병: {player['mercs']}")
        elif cmd == '5': save_game()
        elif cmd == '0': save_game(); break