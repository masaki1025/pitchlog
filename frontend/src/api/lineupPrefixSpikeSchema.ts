import canonical from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'

/** 正式候補schema自身の閉variantを使用する。旧候補の二重追加を避ける。 */
export const lineupPrefixSpikeSchema = canonical
