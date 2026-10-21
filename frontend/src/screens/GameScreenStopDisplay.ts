/**
 * 停止UIだけが受け取る表示契約。
 *
 * 正式な runtime DTO・停止判定・再送可否ではない。phase、端末未確認件数、
 * 訂正に関する注意の表示値だけを受け取る。
 */
export interface StopDisplay {
  phase:
    | 'unavailable'
    | 'read-failed'
    | 'sending-stopped'
    | 'confirmation-pending'
    | 'resume-inquiry'
  deviceUnconfirmed?:
    | { kind: 'count'; value: number }
    | { kind: 'unavailable' }
    | { kind: 'read-failed' }
  /** 呼出元が渡す表示用の注意。証拠の有無や訂正可否は画面で判定しない。 */
  correctionNotice?:
    | 'commit-unknown'
    | 'old-request-block-unconfirmed'
    | 'cancellation-evidence-missing'
}
