<template>
  <!-- 悬浮胶囊导航：固定底部、安全区、占位由 Wot UI 组件负责 -->
  <view class="app-tabbar-wrap">
    <wd-tabbar
      :model-value="active"
      fixed
      placeholder
      safe-area-inset-bottom
      :z-index="100"
      active-color="#2b6cb0"
      inactive-color="#8a8f99"
      custom-style="left: 0; right: 0; bottom: 0; transform: none; width: 100%; max-width: none; border-radius: 0; background: #f5f6f8; box-shadow: none; --wot-tabbar-height: 56px; --wot-tabbar-item-icon-size: 26px; --wot-tabbar-item-title-font-size: 11px;"
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
