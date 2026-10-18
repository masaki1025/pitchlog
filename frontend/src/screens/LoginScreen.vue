<script setup lang="ts">
import { LogIn } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ensureSessionVerified,
  login,
  logout,
  session,
  type LoginResult,
  type SessionResult,
} from '../api/auth'
import Button from '../components/ui/Button.vue'
import { useAuthStore } from '../stores/authStore'

const emit = defineEmits<{ authenticated: [] }>()
const auth = useAuthStore()
const teamName = ref('')
const password = ref('')
type State =
  | 'idle'
  | 'submitting'
  | 'verifying'
  | 'rejected'
  | 'rate-limited'
  | 'verification-unknown'
  | 'authenticated'
const state = ref<State>('verifying')
const pending = ref(false)
let mounted = true
let operation = 0
const busy = computed(() => pending.value)
const message = computed(() => {
  switch (state.value) {
    case 'rejected':
      return 'ログインできませんでした。入力内容をご確認ください。'
    case 'rate-limited':
      return 'しばらく待ってから、もう一度お試しください。'
    case 'verification-unknown':
      return '認証状態を確認できません。状態を再確認するか、ログアウトしてやり直してください。'
    default:
      return null
  }
})

function apply(result: SessionResult | LoginResult, initial = false): void {
  auth.syncFromStorage()
  if (result.authEpoch !== auth.authEpoch || result.status === 'stale') {
    state.value = 'verification-unknown'
    return
  }
  if (result.status === 'authenticated') {
    if (!auth.isAuthenticated || auth.teamId !== result.tenantId) {
      state.value = 'verification-unknown'
      return
    }
    state.value = 'authenticated'
    emit('authenticated')
  } else if (result.status === 'server-unauthenticated') {
    state.value = initial ? 'idle' : 'rejected'
  } else if (result.status === 'rejected') {
    state.value = result.httpStatus === 429 ? 'rate-limited' : 'rejected'
  } else {
    state.value = 'verification-unknown'
  }
}

async function verify(initial = false): Promise<void> {
  if (pending.value) return
  const id = ++operation
  pending.value = true
  state.value = 'verifying'
  try {
    const result = await (initial ? ensureSessionVerified() : session())
    if (mounted && id === operation) apply(result, initial)
  } catch {
    if (mounted && id === operation) state.value = 'verification-unknown'
  } finally {
    if (mounted && id === operation) pending.value = false
  }
}

async function submit(): Promise<void> {
  if (pending.value || !teamName.value.trim() || !password.value) return
  // 資格情報は1回の明示操作だけに渡し、再確認では再送しない。
  const credentials = {
    team_name: teamName.value.trim(),
    password: password.value,
  }
  password.value = ''
  const id = ++operation
  pending.value = true
  state.value = 'submitting'
  try {
    const result = await login(credentials)
    if (mounted && id === operation) apply(result)
  } catch {
    if (mounted && id === operation) state.value = 'verification-unknown'
  } finally {
    if (mounted && id === operation) pending.value = false
  }
}

async function signOut(): Promise<void> {
  if (pending.value) return
  const id = ++operation
  pending.value = true
  state.value = 'verifying'
  password.value = ''
  try {
    const result = await logout()
    if (!mounted || id !== operation) return
    auth.syncFromStorage()
    state.value =
      result.authEpoch === auth.authEpoch && result.status === 'logged-out'
        ? 'idle'
        : 'verification-unknown'
  } catch {
    if (mounted && id === operation) state.value = 'verification-unknown'
  } finally {
    if (mounted && id === operation) pending.value = false
  }
}

watch(
  () => auth.authEpoch,
  () => {
    password.value = ''
    if (pending.value && state.value === 'submitting') state.value = 'verifying'
    else if (!pending.value) state.value = 'verification-unknown'
  },
  { flush: 'sync' },
)
onMounted(() => void verify(true))
onBeforeUnmount(() => {
  mounted = false
  operation += 1
  password.value = ''
})
</script>

<template>
  <div
    class="flex min-h-dvh items-center justify-center bg-slate-50 p-4 dark:bg-slate-950"
  >
    <div class="w-full max-w-sm">
      <form
        :aria-busy="busy"
        class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900"
        @submit.prevent="submit"
      >
        <div class="mb-5 text-center">
          <div
            class="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-sky-600 text-xl font-black text-white"
            aria-hidden="true"
          >
            B
          </div>
          <h1 class="text-2xl font-extrabold">野球スコアリング</h1>
          <p class="mt-1 text-sm text-slate-400">
            チームの試合記録を、1球ずつすばやく
          </p>
        </div>
        <label class="mb-3 block">
          <span class="mb-1 block text-xs font-bold text-slate-500"
            >チーム名</span
          >
          <input
            v-model="teamName"
            type="text"
            name="team_name"
            autocomplete="username"
            placeholder="例: 筑波大学"
            maxlength="50"
            required
            :disabled="busy"
            class="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-base dark:border-slate-600 dark:bg-slate-800"
          />
        </label>
        <label class="mb-3 block">
          <span class="mb-1 block text-xs font-bold text-slate-500"
            >パスワード</span
          >
          <input
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            maxlength="128"
            required
            :disabled="busy"
            class="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-base dark:border-slate-600 dark:bg-slate-800"
          />
        </label>
        <p
          v-if="message"
          role="alert"
          class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300"
        >
          {{ message }}
        </p>
        <p v-if="busy" role="status" class="mb-3 text-sm">
          {{ state === 'submitting' ? '処理中…' : '認証状態を確認中…' }}
        </p>
        <Button
          type="submit"
          variant="primary"
          class="w-full"
          :disabled="busy || !teamName.trim() || !password"
        >
          <span class="inline-flex items-center gap-2">
            <LogIn :size="18" aria-hidden="true" />ログイン
          </span>
        </Button>
        <div v-if="state === 'verification-unknown'" class="mt-3 grid gap-2">
          <Button :disabled="busy" @click="verify()">状態を再確認</Button>
          <Button :disabled="busy" @click="signOut"
            >ログアウトしてやり直す</Button
          >
        </div>
      </form>
    </div>
  </div>
</template>
