<template>
  <view class="vw-icon" :style="{ width: size + 'rpx', height: size + 'rpx' }">
    <view class="vw-dot"></view>
    <view class="vw-arc vw-arc-1"></view>
    <view class="vw-arc vw-arc-2"></view>
  </view>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 40 },
})
</script>

<style scoped>
/* 圆环 + 圆点 + 两道声波，颜色继承父级 currentColor。 */
.vw-icon {
  position: relative;
  box-sizing: border-box;
  border: 3rpx solid currentColor;
  border-radius: 50%;
  flex: 0 0 auto;
}

.vw-dot {
  position: absolute;
  left: 20%;
  top: 50%;
  width: 14%;
  height: 14%;
  margin-top: -7%;
  border-radius: 50%;
  background: currentColor;
}

.vw-arc {
  position: absolute;
  top: 50%;
  box-sizing: border-box;
  border: 3rpx solid currentColor;
  border-top-color: transparent;
  border-bottom-color: transparent;
  border-left-color: transparent;
  border-radius: 50%;
  transform: translateY(-50%);
}

.vw-arc-1 {
  left: 40%;
  width: 24%;
  height: 38%;
}

.vw-arc-2 {
  left: 61%;
  width: 20%;
  height: 62%;
}
</style>
