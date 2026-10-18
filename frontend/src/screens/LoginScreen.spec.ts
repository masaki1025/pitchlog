import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiSessionUnverifiedError, apiRequest } from '../api/client'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import LoginScreen from './LoginScreen.vue'

const tenant = '12345678-1234-1234-1234-123456789abc'
const dto = { tenant_id: tenant, team_name: '認可済みチーム' }
const reply = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
function deferred() {
  let resolve!: (value: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
let pinia: Pinia
let wrapper: VueWrapper | undefined
const fetchMock = vi.fn<typeof fetch>()
async function screen() {
  wrapper = mount(LoginScreen, { global: { plugins: [pinia] } })
  await flushPromises()
  return wrapper
}
async function submit(view: VueWrapper) {
  await view.get('input[name="team_name"]').setValue(' 入力チーム ')
  await view.get('input[name="password"]').setValue('test-password')
  await view.get('form').trigger('submit')
  await flushPromises()
}
async function click(view: VueWrapper, text: string) {
  const found = view.findAll('button').find((item) => item.text() === text)
  if (!found) throw new Error('対象ボタンなし')
  await found.trigger('click')
  await flushPromises()
}
beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  fetchMock.mockReset().mockImplementation(async () => reply({}, 401))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  disposePinia(pinia)
  queryClient.clear()
  vi.unstubAllGlobals()
})
describe('LoginScreenの正規認証経路', () => {
  it('直接mountはsessionのみ確認し未認証なら入力を許す', async () => {
    const view = await screen()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/auth/session')
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(view.find('[role="alert"]').exists()).toBe(false)
  })
  it('login ackではemitせずsession DTO検証後だけemitする', async () => {
    const view = await screen()
    const pending = deferred()
    fetchMock
      .mockResolvedValueOnce(reply({ status: 'authenticated' }))
      .mockReturnValueOnce(pending.promise)
    await submit(view)
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(view.get('[role="status"]').text()).toContain('確認中')
    expect(
      (view.get('input[name="password"]').element as HTMLInputElement).value,
    ).toBe('')
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({
      team_name: '入力チーム',
      password: 'test-password',
    })
    pending.resolve(reply(dto))
    await flushPromises()
    expect(view.emitted('authenticated')).toEqual([[]])
    expect(useAuthStore().teamId).toBe(tenant)
  })
  it.each([401, 403, 404, 500])(
    'HTTP %iは固定拒否で内部詳細を漏らさない',
    async (status) => {
      const view = await screen()
      fetchMock.mockResolvedValueOnce(
        reply({ detail: '存在する秘密チーム' }, status),
      )
      await submit(view)
      expect(view.get('[role="alert"]').text()).toBe(
        'ログインできませんでした。入力内容をご確認ください。',
      )
      expect(view.text()).not.toContain('存在する秘密チーム')
      expect(view.emitted('authenticated')).toBeUndefined()
    },
  )
  it('429は一般案内だけを表示する', async () => {
    const view = await screen()
    fetchMock.mockResolvedValueOnce(reply({}, 429))
    await submit(view)
    expect(view.get('[role="alert"]').text()).toContain('しばらく待って')
  })
  it.each(['network', 'invalid-dto'])(
    'session %sを成功・認証拒否と同一扱いしない',
    async (kind) => {
      const view = await screen()
      fetchMock.mockResolvedValueOnce(reply({ status: 'authenticated' }))
      if (kind === 'network')
        fetchMock.mockRejectedValueOnce(new TypeError('通信断'))
      else
        fetchMock.mockResolvedValueOnce(
          reply({ tenant_id: tenant, team_name: 1 }),
        )
      await submit(view)
      expect(view.get('[role="alert"]').text()).toContain(
        '認証状態を確認できません',
      )
      expect(view.emitted('authenticated')).toBeUndefined()
      expect(useAuthStore().isAuthenticated).toBe(false)
    },
  )
  it('二重submitを抑止し資格情報を自動再送しない', async () => {
    const view = await screen()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    await submit(view)
    await view.get('form').trigger('submit')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    pending.resolve(reply({}, 503))
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(
      (view.get('input[name="password"]').element as HTMLInputElement).value,
    ).toBe('')
  })
  it('明示再確認はGETだけで資格情報を再送しない', async () => {
    fetchMock.mockResolvedValueOnce(reply({}, 503))
    const view = await screen()
    fetchMock.mockResolvedValueOnce(reply(dto))
    await click(view, '状態を再確認')
    expect(fetchMock.mock.calls.map(([, options]) => options?.method)).toEqual([
      'GET',
      'GET',
    ])
    expect(view.emitted('authenticated')).toEqual([[]])
  })
  it.each([false, true])(
    'logout結果確定=%sだけで入力へ戻り未確認を完了にしない',
    async (confirmed) => {
      fetchMock.mockResolvedValueOnce(reply({}, 503))
      const view = await screen()
      fetchMock.mockResolvedValueOnce(
        confirmed ? reply({ status: 'logged_out' }) : reply({}, 503),
      )
      await click(view, 'ログアウトしてやり直す')
      expect(view.find('[role="alert"]').exists()).toBe(!confirmed)
      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(view.emitted('authenticated')).toBeUndefined()
    },
  )
  it('新しいproviderで再生成すると保存値を認証証拠にしない', async () => {
    fetchMock.mockResolvedValueOnce(reply(dto))
    const first = await screen()
    expect(first.emitted('authenticated')).toEqual([[]])
    first.unmount()
    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    const second = await screen()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(second.emitted('authenticated')).toBeUndefined()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
  it('旧session応答は新世代を上書きせずemitしない', async () => {
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    const view = await screen()
    const auth = useAuthStore()
    auth.signIn({ teamId: tenant, teamName: 'B' })
    pending.resolve(reply(dto))
    await flushPromises()
    expect(auth.teamName).toBe('B')
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(view.get('[role="alert"]').text()).toContain(
      '認証状態を確認できません',
    )
  })
  it('旧loginのCookie不確実性は新世代を無効化するが成功はemitしない', async () => {
    const view = await screen()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    await submit(view)
    const auth = useAuthStore()
    auth.signIn({ teamId: tenant, teamName: 'B' })
    queryClient.setQueryData(['new-tenant'], 'B')
    pending.resolve(reply({ status: 'authenticated' }))
    await flushPromises()
    expect(auth.isAuthenticated).toBe(false)
    expect(queryClient.getQueryData(['new-tenant'])).toBeUndefined()
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('unmount後の遅延成功はemitしない', async () => {
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    const view = await screen()
    view.unmount()
    wrapper = undefined
    pending.resolve(reply(dto))
    await flushPromises()
    expect(view.emitted('authenticated')).toBeUndefined()
  })
  it('HTML入力を展開せずlabel・autocomplete・submitを維持する', async () => {
    const view = await screen()
    await view
      .get('input[name="team_name"]')
      .setValue('<img src=x onerror=alert(1)>')
    expect(view.find('img').exists()).toBe(false)
    expect(
      view.get('input[name="team_name"]').element.closest('label')?.textContent,
    ).toContain('チーム名')
    expect(view.get('input[name="password"]').attributes('autocomplete')).toBe(
      'current-password',
    )
    expect(view.get('button[type="submit"]').text()).toBe('ログイン')
    expect(view.text()).not.toContain('チーム新規登録')
  })
  it('mount時の不正DTOを未確認にしtenant通信と変更要求を送らない', async () => {
    fetchMock.mockResolvedValueOnce(reply({ ...dto, extra: true }))
    const view = await screen()
    expect(view.get('[role="alert"]').text()).toContain(
      '認証状態を確認できません',
    )
    await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(
      ApiSessionUnverifiedError,
    )
    await expect(
      apiRequest('POST', '/players', { body: { name: '送信しない' } }),
    ).rejects.toBeInstanceOf(ApiSessionUnverifiedError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(view.emitted('authenticated')).toBeUndefined()
  })
  it('旧logoutのCookie変更可能性は新tenantを無効化し旧完了を表示しない', async () => {
    fetchMock.mockResolvedValueOnce(reply({}, 503))
    const view = await screen()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    await click(view, 'ログアウトしてやり直す')
    const auth = useAuthStore()
    auth.signIn({ teamId: tenant, teamName: 'B' })
    queryClient.setQueryData(['new-tenant'], 'B')
    pending.resolve(reply({ status: 'logged_out' }))
    await flushPromises()
    expect(auth.isAuthenticated).toBe(false)
    expect(queryClient.getQueryData(['new-tenant'])).toBeUndefined()
    expect(view.get('[role="alert"]').text()).toContain(
      '認証状態を確認できません',
    )
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('A→B→Cの世代切替後の旧loginから成功や資格情報再送を採らない', async () => {
    const view = await screen()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    await submit(view)
    const auth = useAuthStore()
    auth.signIn({ teamId: tenant, teamName: 'B' })
    auth.signOut()
    auth.signIn({
      teamId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      teamName: 'C',
    })
    pending.resolve(reply({ status: 'authenticated' }))
    await flushPromises()
    expect(auth.isAuthenticated).toBe(false)
    expect(view.emitted('authenticated')).toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    fetchMock.mockResolvedValueOnce(reply(dto))
    await click(view, '状態を再確認')
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe('GET')
    expect(view.emitted('authenticated')).toEqual([[]])
    expect(auth.teamName).toBe('認可済みチーム')
  })
  it('確定認証後に別世代へ切り替わると画面の成功状態を流用しない', async () => {
    fetchMock.mockResolvedValueOnce(reply(dto))
    const view = await screen()
    expect(view.emitted('authenticated')).toHaveLength(1)
    const auth = useAuthStore()
    auth.beginSessionVerification()
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain(
      '認証状態を確認できません',
    )
    expect(view.emitted('authenticated')).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('再確認の連打と確認中のlogoutを抑止する', async () => {
    fetchMock.mockResolvedValueOnce(reply({}, 503))
    const view = await screen()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    await click(view, '状態を再確認')
    await view.get('form').trigger('submit')
    expect(
      view
        .findAll('button')
        .every((item) => item.attributes('disabled') !== undefined),
    ).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    pending.resolve(reply({}, 503))
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain(
      '認証状態を確認できません',
    )
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('チーム名入力とサーバー応答内容を拒否文言へ混ぜない', async () => {
    const view = await screen()
    await view
      .get('input[name="team_name"]')
      .setValue('<script>存在しないチーム</script>')
    await view.get('input[name="password"]').setValue('test-password')
    fetchMock.mockResolvedValueOnce(reply({ detail: '<img src=x>実在名' }, 401))
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toBe(
      'ログインできませんでした。入力内容をご確認ください。',
    )
    expect(view.find('script').exists()).toBe(false)
    expect(view.find('img').exists()).toBe(false)
    expect(localStorage.getItem('bb.auth')).toBeNull()
  })
})
