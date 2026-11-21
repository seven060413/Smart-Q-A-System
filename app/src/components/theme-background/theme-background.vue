<template>
  <!-- 主题插件背景图：铺满视口，层级低于页面内容，不拦截点击 -->
  <image
    v-if="backgroundImage"
    class="theme-bg"
    :src="backgroundImage"
    mode="aspectFill"
  />
</template>

<script setup>
import { backgroundImage } from '../../theme/theme.js'
</script>

<style>
.theme-bg {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 100%;
  /* 负层级：位于页面根节点背景之上、所有内容之下 */
  z-index: -1;
  pointer-events: none;
}
</style>
