                st.divider()
                col1, col2 = st.columns(2)
                col1.info(f"💰 총 가치: {total_value:,}냥")
                col2.info(f"⚖️ 총 무게: {total_weight}/{tw}근")
            else:
                st.write("인벤토리가 비어있습니다")
        
        # [탭3] 용병
        with tab3:
            st.subheader("⚔️ 내 용병")
            if player['mercs']:
                total_bonus = 0
                for merc in player['mercs']:
                    if merc in merc_data:
                        bonus = merc_data[merc]['w_bonus']
                        total_bonus += bonus
                        st.write(f"• **{merc}** (무게 +{bonus}근)")
                
                st.info(f"⚖️ 총 무게 보너스: +{total_bonus}근")
            else:
                st.write("고용한 용병이 없습니다")
        
        # [탭4] 통계
        with tab4:
            st.subheader("📊 거래 통계")
            stats = st.session_state.stats
            
            col1, col2 = st.columns(2)
            col1.metric("총 구매", f"{stats['total_bought']}개")
            col2.metric("총 판매", f"{stats['total_sold']}개")
            
            col3, col4 = st.columns(2)
            col3.metric("총 지출", f"{stats['total_spent']:,}냥")
            col4.metric("총 수익", f"{stats['total_earned']:,}냥")
            
            if stats['total_spent'] > 0:
                profit = stats['total_earned'] - stats['total_spent']
                profit_rate = (profit / stats['total_spent']) * 100
                st.metric("순이익", f"{profit:+,}냥", f"{profit_rate:+.1f}%")
            
            st.metric("거래 횟수", f"{stats['trade_count']}회")
        
        # [탭5] 기타
        with tab5:
            st.subheader("⚙️ 게임 메뉴")
            
            # 마을 이동
            st.write("**🚚 마을 이동**")
            towns = list(villages.keys())
            if player['pos'] in villages:
                curr_v = villages[player['pos']]
                move_options = []
                move_dict = {}
                
                for t in towns:
                    if t != player['pos']:
                        dist = math.sqrt((curr_v['x'] - villages[t]['x'])**2 + (curr_v['y'] - villages[t]['y'])**2)
                        cost = int(dist * settings.get('travel_cost', 15))
                        option_text = f"{t} (💰 {cost:,}냥)"
                        move_options.append(option_text)
                        move_dict[option_text] = (t, cost)
                
                if move_options:
                    selected = st.selectbox("이동할 마을", move_options)
                    if st.button("🚀 이동", use_container_width=True):
                        dest, cost = move_dict[selected]
                        if player['money'] >= cost:
                            player['money'] -= cost
                            player['pos'] = dest
                            money_placeholder.metric("💰 소지금", f"{player['money']:,}냥")
                            st.success(f"✅ {dest}로 이동했습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 잔액 부족")
                else:
                    st.write("이동 가능한 마을이 없습니다")
            
            st.divider()
            
            # 시간 정보
            st.write("**⏰ 시간 시스템**")
            remaining = 180 - int(time.time() - st.session_state.last_time_update)
            if remaining < 0:
                remaining = 0
            st.info(f"현실 3분 = 게임 1달\n\n다음 달까지: {remaining}초")
            
            st.divider()
            
            # 저장
            if st.button("💾 저장", use_container_width=True):
                if save_player_data(doc, player, st.session_state.stats, st.session_state.device_id):
                    st.success("✅ 저장 완료!")
            
            # 종료
            if st.button("🚪 메인으로", use_container_width=True):
                st.session_state.game_started = False
                st.cache_data.clear()
                st.rerun()
