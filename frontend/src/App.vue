<script setup lang="ts">
import { CircleHelp } from 'lucide-vue-next'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

async function returnToHome(): Promise<void> {
  await router.push({ name: 'home' })
}
</script>

<template>
  <main>
    <header v-if="route.name === 'home'" class="flex items-center gap-3 p-4">
      <h1 class="text-xl font-extrabold">PitchLog</h1>
      <RouterLink
        :to="{ name: 'help' }"
        aria-label="使い方を開く"
        class="ml-auto flex min-h-12 items-center gap-2 rounded-xl px-3 font-bold text-slate-700 hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        <CircleHelp :size="18" />
        使い方
      </RouterLink>
    </header>
    <RouterView v-slot="{ Component }">
      <component
        :is="Component"
        v-if="route.name === 'help'"
        @back="returnToHome"
      />
      <component :is="Component" v-else />
    </RouterView>
  </main>
</template>
