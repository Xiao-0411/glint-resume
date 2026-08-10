<template>
  <svg
    class="brand-mark"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    fill="none"
    role="img"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
  >
    <path
      d="m24 3.5 1.65 4.85L30.5 10l-4.85 1.65L24 16.5l-1.65-4.85L17.5 10l4.85-1.65L24 3.5Z"
      fill="#F59E0B"
    />
    <path d="m11.5 10.5 5.75 6.25M36.5 10.5l-5.75 6.25" stroke="#6366F1" stroke-width="4" stroke-linecap="round" />
    <path d="M8 22.5h32" stroke="#111827" stroke-width="4.5" stroke-linecap="round" />
    <path d="M20.75 23c0 8.25-3.75 14.5-11.75 19" stroke="#111827" stroke-width="4.5" stroke-linecap="round" />
    <path d="M27.25 23v9.25c0 6.25 3.5 9.25 9.75 9.25h3.5" stroke="#6366F1" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" />
    <path d="m37 37.75 3.75 3.75L37 45.25" stroke="#6366F1" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 32 },
  label: { type: String, default: '' }
})
</script>

<style scoped>
.brand-mark {
  display: block;
  flex: 0 0 auto;
  overflow: visible;
}
</style>
