<template>
  <!-- 悬浮胶囊导航：固定底部、安全区、占位由 Wot UI 组件负责 -->
  <view class="app-tabbar-wrap">
    <wd-tabbar
      :model-value="active"
      fixed
      placeholder
      safe-area-inset-bottom
      :z-index="100"
      :active-color="activeColor"
      :inactive-color="inactiveColor"
      :custom-style="tabbarStyle"
      @change="handleChange"
    >
      <wd-tabbar-item
        v-for="item in TAB_ITEMS"
        :key="item.path"
        :name="item.path"
        :title="item.title"
        :icon="item.icon"
      />
    </wd-tabbar>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { TAB_ITEMS } from '../tabbar.js'
import { tokens } from '../theme/theme.js'

const props = defineProps({
  active: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['change'])

const activeColor = computed(() => tokens.value.primary)
const inactiveColor = computed(() => tokens.value.t3)
const tabbarStyle = computed(() =>
  `left: 0; right: 0; bottom: 0; transform: none; width: 100%; max-width: none;` +
  `border-radius: 0; background: ${tokens.value.card}; box-shadow: none;` +
  `--wot-tabbar-height: 56px; --wot-tabbar-item-icon-size: 26px;` +
  `--wot-tabbar-item-title-font-size: 11px;`
)

function handleChange({ value }) {
  if (!value || value === props.active) return
  emit('change', value)
}
</script>

<style>
/* 与 Wot UI 实际底栏高度严格一致：56px + 安全区，避免和输入区之间出现空隙 */
.app-tabbar-wrap {
  flex: 0 0 auto;
  height: calc(56px + env(safe-area-inset-bottom));
  background: var(--ik-card);
}
</style>
