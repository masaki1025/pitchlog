<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <main>
    <h1 v-if="route.name === 'home'">PitchLog</h1>
    <RouterView />
  </main>
</template>
