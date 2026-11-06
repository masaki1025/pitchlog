import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BasicStatsTable from './BasicStatsTable.vue'
import type { BasicStatItem, PlayerBasicStats } from '../../api/stats'

function item(
  metric_id: string,
  label: string,
  display: string | null,
  state: BasicStatItem['state'] = 'available',
  reason: string | null = null,
): BasicStatItem {
  return {
    metric_id,
    label,
    state,
    value: display,
    display,
    reason,
    components: null,
  }
}

const batting = [
  item('pa', '打席', '4'),
  item('ab', '打数', '3'),
  item('h', '安打', '2'),
  item('avg', '打率', '.667(打数3)'),
]
const pitching = [
  item('appearances', '登板', null, 'source_unavailable', 'D03_SOURCE_PENDING'),
  item('innings_pitched', '投球回', '3.0'),
  item(
    'batters_faced',
    '打者数',
    null,
    'source_unavailable',
    'D04_SOURCE_PENDING',
  ),
  item('whip', 'WHIP', '1.00(投球回3)'),
]

const players: PlayerBasicStats[] = [
  {
    player_id: '00000000-0000-4000-8000-000000000001',
    player_name: '山田',
    uniform_number: '7',
    team_record_id: '00000000-0000-4000-8000-000000000010',
    team_name: '自チーム',
    is_pitcher: true,
    batting,
    pitching,
    pending: ['D03_SOURCE_PENDING', 'D04_SOURCE_PENDING'],
  },
  {
    player_id: '00000000-0000-4000-8000-000000000002',
    player_name: '佐藤',
    uniform_number: '9',
    team_record_id: '00000000-0000-4000-8000-000000000010',
    team_name: '自チーム',
    is_pitcher: false,
    batting,
    pitching,
    pending: [],
  },
]

describe('BasicStatsTable', () => {
  it('打撃・投手の表示値をそのまま描画し、未取得を0へ変えない', () => {
    const wrapper = mount(BasicStatsTable, {
      props: { players, periodLabel: '2026年通算' },
    })
    const text = wrapper.text()
    expect(text).toContain('2026年通算 打撃')
    expect(text).toContain('.667(打数3)')
    expect(text).toContain('3.0')
    expect(text).toContain('1.00(投球回3)')
    expect(text).toContain('登板: 正式な投手出場sourceが未接続')
    expect(text).toContain('打者数: 責任帰属sourceが未接続')
    // 投手表は is_pitcher=true の1名だけ。
    const pitchingTable = wrapper.findAll('table')[1]
    expect(pitchingTable?.text()).toContain('山田')
    expect(pitchingTable?.text()).not.toContain('佐藤')
  })

  it('0件はデータなしを表示する', () => {
    const wrapper = mount(BasicStatsTable, {
      props: { players: [], periodLabel: '2026年通算' },
    })
    expect(wrapper.text()).toContain('データなし')
  })
})
