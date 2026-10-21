<script setup lang="ts">
import { useId } from 'vue'
import type {
  ObservationAnswer,
  PlayObservationQuestion,
} from './GameScreenPlayObservationTypes'

const props = defineProps<{
  question: PlayObservationQuestion
  value: ObservationAnswer
}>()
const emit = defineEmits<{ change: [value: ObservationAnswer] }>()
const fieldId = useId()

function choose(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  emit(
    'change',
    props.question.options.some((option) => option.id === id) ? id : null,
  )
}

function toggle(id: string, checked: boolean) {
  if (!props.question.options.some((option) => option.id === id)) return
  const selected = Array.isArray(props.value) ? props.value : []
  const next = checked
    ? [...selected, id]
    : selected.filter((item) => item !== id)
  emit('change', next.length ? next : null)
}
</script>

<template>
  <div class="min-w-0 space-y-1" :data-question-key="question.key">
    <fieldset v-if="question.multiple" class="grid min-w-0 gap-1">
      <legend class="text-sm font-bold">
        {{ question.label }} <span v-if="question.required">（入力対象）</span>
      </legend>
      <label
        v-for="option in question.options"
        :key="option.id"
        class="flex min-w-0 items-start gap-2 rounded border border-slate-300 p-2 text-sm dark:border-slate-600"
      >
        <input
          type="checkbox"
          :value="option.id"
          :checked="Array.isArray(value) && value.includes(option.id)"
          @change="
            toggle(option.id, ($event.target as HTMLInputElement).checked)
          "
        />
        <span class="min-w-0 wrap-anywhere">{{ option.label }}</span>
      </label>
    </fieldset>
    <template v-else>
      <label :for="fieldId" class="block text-sm font-bold">
        {{ question.label }} <span v-if="question.required">（入力対象）</span>
      </label>
      <select
        :id="fieldId"
        :value="typeof value === 'string' ? value : ''"
        class="w-full min-w-0 rounded border border-slate-300 bg-white p-2 text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
        @change="choose"
      >
        <option value="">未選択</option>
        <option
          v-for="option in question.options"
          :key="option.id"
          :value="option.id"
        >
          {{ option.label }}
        </option>
      </select>
    </template>
  </div>
</template>
