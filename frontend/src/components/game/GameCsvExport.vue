<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { ApiError } from '../../api/client'
import { downloadPlayCsv } from '../../api/gameExports'

const props = defineProps<{ gameId: string }>()
const busy = ref(false)
const message = ref<string | null>(null)
const missing = ref<string[]>([])
const controller = ref<AbortController | null>(null)

function bytesToHex(value: ArrayBuffer): string {
  return [...new Uint8Array(value)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

async function verify(
  blob: Blob,
  contentLength: number | null,
  expectedSha: string | null,
): Promise<boolean> {
  if (contentLength !== null && blob.size !== contentLength) return false
  if (expectedSha !== null) {
    if (globalThis.crypto?.subtle === undefined) return false
    const actual = bytesToHex(
      await globalThis.crypto.subtle.digest(
        'SHA-256',
        await blob.arrayBuffer(),
      ),
    )
    if (actual !== expectedSha) return false
  }
  return true
}

function save(blob: Blob, filename: string | null): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename ?? `pitchlog-plays-${props.gameId}.zip`
  anchor.click()
  URL.revokeObjectURL(url)
}

async function download(): Promise<void> {
  if (busy.value) return
  busy.value = true
  message.value = null
  missing.value = []
  const abort = new AbortController()
  controller.value = abort
  try {
    const result = await downloadPlayCsv(props.gameId, abort.signal)
    if (!(await verify(result.blob, result.contentLength, result.sha256))) {
      message.value = '完成ZIPの長さまたはSHA-256が一致しないため保存しません'
      return
    }
    save(result.blob, result.filename)
    message.value = '毎球CSVを保存しました'
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) {
        message.value = 'ログイン状態を確認してください'
      } else if (error.status === 404) {
        message.value = '対象試合が見つかりません'
      } else if (error.status === 409) {
        missing.value = error.fields.map((field) => field.location)
        message.value = '毎球CSVの供給が不足しています（再試行できます）'
      } else {
        message.value = '毎球CSVを取得できませんでした（再試行できます）'
      }
    } else {
      message.value = '毎球CSVを取得できませんでした（再試行できます）'
    }
  } finally {
    if (controller.value === abort) controller.value = null
    busy.value = false
  }
}

function retry(): void {
  void download()
}

onBeforeUnmount(() => {
  controller.value?.abort()
})
</script>

<template>
  <section class="space-y-2 rounded-lg border p-3">
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-base font-semibold">毎球CSV</h2>
      <button
        type="button"
        class="rounded border px-3 py-1 text-sm disabled:opacity-40"
        :disabled="busy"
        @click="download"
      >
        {{ busy ? '取得中…' : '毎球CSVをダウンロード' }}
      </button>
      <button
        v-if="message !== null && missing.length > 0"
        type="button"
        class="rounded border px-3 py-1 text-sm"
        :disabled="busy"
        @click="retry"
      >
        再試行
      </button>
    </div>
    <p v-if="message !== null" class="text-sm">{{ message }}</p>
    <p v-if="missing.length > 0" class="text-xs text-slate-600">
      未供給: {{ missing.slice(0, 12).join(', ')
      }}{{ missing.length > 12 ? ' …' : '' }}
    </p>
  </section>
</template>
