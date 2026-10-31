<template>
  <!-- 悬浮胶囊导航：固定底部、安全区、占位由 Wot UI 组件负责 -->
  <view class="app-tabbar-wrap">
    <wd-tabbar
      :model-value="active"
      fixed
      placeholder
      safe-area-inset-bottom
      shape="round"
      :z-index="100"
      active-color="#2b6cb0"
      inactive-color="#8a8f99"
      custom-style="left: 50%; right: auto; bottom: calc(8px + env(safe-area-inset-bottom)); transform: translateX(-50%); width: calc(100% - 48px); max-width: 420px; margin-left: 0; margin-right: 0; border-radius: 28px; background: #ffffff; box-shadow: 0 6px 20px rgba(43, 108, 176, 0.14); --wot-tabbar-height: 56px; --wot-tabbar-item-icon-size: 26px; --wot-tabbar-item-title-font-size: 11px;"
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
import { TAB_ITEMS, switchTab } from '../tabbar.js'

const props = defineProps({
  active: {
    type: String,
    required: true,
  },
})

function handleChange({ value }) {
  if (!value || value === props.active) return
  switchTab(value)
}
</script>

<style>
/* 与 Wot UI 的 56px + 8px 悬浮间距 + 安全区保持一致，避免首帧占位高度变化 */
.app-tabbar-wrap {
  flex: 0 0 auto;
  height: calc(64px + env(safe-area-inset-bottom));
}
</style>
