// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://pitchlog.test"}
/** 表示だけのcontroller double。実DB/実認可の代わりではない。 */
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import * as vocab from '../api/pitchTypeOptions'
import GameScreenUndoProduct from './GameScreenUndoProduct.vue'
import { GameScreenUndoProductController as Controller } from './GameScreenUndoProductController'
import { undoContext } from './GameScreenUndoProductProvider'
import { undoRead } from './GameScreenUndoProduct.test-support'
let pinia: Pinia
beforeEach(async () => {
  vi.stubGlobal('isSecureContext', true)
  pinia = createPinia()
  setActivePinia(pinia)
  const g = undoRead(3)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: g.checkpoint.content.scope.tenantId,
    teamName: '<script>fixture</script>',
  })
  vi.spyOn(vocab, 'readPitchTypeOptions').mockResolvedValue({
    items: [
      {
        key: 'pitch-type.straight',
        display_name: '<img src=x onerror=alert(1)>',
      },
    ],
    next_cursor: null,
  })
  vi.spyOn(Controller.prototype, 'load').mockResolvedValue('ready')
  vi.spyOn(Controller.prototype, 'context', 'get').mockReturnValue(
    await undoContext(
      g,
      g.checkpoint.content.scope.tenantId,
      g.page.items,
      true,
    ),
  )
  vi.spyOn(Controller.prototype, 'dispose').mockImplementation(() => {})
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('サーバー確認値だけを表示し、端末条件未確認では取消を確定しない', async () => {
  const action = vi
    .spyOn(Controller.prototype, 'undo')
    .mockResolvedValue('pending')
  const wrapper = mount(GameScreenUndoProduct, {
    props: { gameId: undoRead(3).id },
  })
  await flushPromises()
  expect(wrapper.get('[data-testid="undo-product-balls"]').text()).toBe('1')
  expect(wrapper.get('[data-testid="undo-product-depth"]').text()).toBe('1')
  expect(
    wrapper.get('[data-testid="undo-product-apply"]').attributes('disabled'),
  ).toBeDefined()
  await wrapper.get('[data-testid="undo-product-apply"]').trigger('click')
  expect(action).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('確認後の結果不明を保存成功と表示せず、文字列は自動escapeする', async () => {
  vi.spyOn(Controller.prototype, 'undo').mockResolvedValue('pending')
  const wrapper = mount(GameScreenUndoProduct, {
    props: { gameId: undoRead(3).id },
  })
  await flushPromises()
  for (const box of wrapper.findAll('input[type=checkbox]'))
    await box.setValue(true)
  await wrapper.get('[data-testid="undo-product-apply"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('[data-testid="undo-product-status"]').text()).toContain(
    '結果未確認',
  )
  expect(wrapper.find('img').exists()).toBe(false)
  expect(
    wrapper.get('[data-testid="undo-product-pitch-type"]').text(),
  ).toContain('<img src=x onerror=alert(1)>')
  expect(wrapper.emitted('saved')).toBeUndefined()
  wrapper.unmount()
})
