// 作者候補。未受理・未実装。真正性/在籍/開始成功を表す型ではない。
export type CanonicalUUID = string
export type OneToNineDecimal = '1'|'2'|'3'|'4'|'5'|'6'|'7'|'8'|'9'
export type FieldingRoleWire = Readonly<{kind:'fielding';position:OneToNineDecimal}> | Readonly<{kind:'designated-hitter'}>
export type Nine<T> = readonly [T,T,T,T,T,T,T,T,T]
export type NineOrTen<T> = Nine<T> | readonly [T,T,T,T,T,T,T,T,T,T]
export type EntryInput = Readonly<{player_id:CanonicalUUID;batting_order:OneToNineDecimal|null;fielding_position:FieldingRoleWire}>
export type SideInput = Readonly<{team_id:CanonicalUUID;entries:NineOrTen<EntryInput>}>
export type Request = Readonly<{dh:boolean;away:SideInput;home:SideInput}>
export type BattingSlotWire = Readonly<{kind:'none'}> | Readonly<{kind:'slot';slot:OneToNineDecimal}>
export type ProjectedEntryWire = Readonly<{player:Readonly<{kind:'official';player_id:CanonicalUUID}>;batting_slot:BattingSlotWire;roles:readonly [FieldingRoleWire];entry_origin:Readonly<{kind:'initial'}>}>
export type ProjectedTeamWire<S extends 'away'|'home'> = Readonly<{team_id:CanonicalUUID;side:S;participants:NineOrTen<ProjectedEntryWire>}>
export type ProjectionWire = Readonly<{teams:readonly [ProjectedTeamWire<'away'>,ProjectedTeamWire<'home'>]}>
export type ErrorCode = 'INVALID_JSON'|'INVALID_REQUEST'|'INVALID_DECIMAL_INTEGER'|'INVALID_INITIAL_LINEUP'|'UNSUPPORTED_INITIAL_ROSTER_SCOPE'
export type Response = Readonly<{ok:true;value:ProjectionWire}> | Readonly<{ok:false;error:Readonly<{code:ErrorCode}>}>
