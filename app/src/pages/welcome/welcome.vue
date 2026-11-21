
<template>
  <view class="welcome-page">
    <image
      class="welcome-image"
      src="/static/images/welcome.png"
      mode="aspectFill"
    />
  </view>
</template>

<script setup>
import { onLoad } from '@dcloudio/uni-app'

onLoad(() => {
  setTimeout(() => {
    uni.redirectTo({
      url: '/pages/auth/auth'
    })
  }, 2000)
})
</script>

<style>
.welcome-page {
  width: 100%;
  height: 100vh;
  background-color: #F7F8FF;
  overflow: hidden;
}

.welcome-image {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
