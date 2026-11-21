<template>
  <view
    class="eye-gaze"
    :class="[`is-${state}`, { 'on-block': onBlock, 'is-blink': blinking, 'is-reduced': reduced }]"
    :style="rootStyle"
    role="img"
    :aria-label="label"
  >
    <view class="eyes">
      <view v-for="i in 2" :key="i" class="eye">
        <view class="eye-inner">
          <view class="iris" :style="irisStyle">
            <view class="pupil"></view>
            <view class="shine"></view>
          </view>
        </view>
        <view class="lid"></view>
      </view>
    </view>
    <view v-if="state === 'due'" class="pulse-wrap">
      <view class="pulse"></view>
      <view class="pulse p2"></view>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  progress: { type: Number, default: 1 },
  size: { type: Number, default: 180 },
  onBlock: { type: Boolean, default: false },
  reducedMotion: { type: Boolean, default: false },
})

const LABELS = {
  idle: '它安静地看着',
  focus: '它正在看着你的专注',
  abandon: '它把视线移开了',
  done: '它眯起了眼睛',
  due: '它睁大了眼睛，时间到了',
  snooze: '它半闭着眼，在等你',
}

const label = computed(() => LABELS[props.state] || LABELS.idle)

const blinking = ref(false)
const prefersReduced = ref(false)

// #ifdef H5
try {
  if (typeof window !== 'undefined' && window.matchMedia) {
    prefersReduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
} catch (e) {}
// #endif

const reduced = computed(() => props.reducedMotion || prefersReduced.value)

const rootStyle = computed(() => {
  // 非到点状态收紧上下留白，让同样的尺寸看起来更大；到点保留脉冲环的空间。
  const ratio = props.state === 'due' ? 110 / 180 : 74 / 180
  return {
    width: `${uni.upx2px(props.size)}px`,
    height: `${uni.upx2px(props.size * ratio)}px`,
    '--eye-gaze-scale': String(props.size / 180),
  }
})

const motionTick = ref(0)

const gaze = computed(() => {
  const t = motionTick.value
  if (props.state === 'focus') {
    // 跟随倒计时的主轨迹 + 更快的小幅摆动，让眼神一直在动。
    const p = Math.min(1, Math.max(0, props.progress))
    const angle = (1 - p) * Math.PI * 2 - Math.PI / 2
    return {
      x: Math.cos(angle) * 8 + Math.sin(t * 0.9) * 2.6,
      y: Math.sin(angle) * 5 + Math.cos(t * 0.65) * 1.8,
    }
  }
  if (props.state === 'idle') {
    // 空闲时左右缓慢扫视，每 0.65s 更新一次。
    return {
      x: Math.sin(t * 0.75) * 7,
      y: Math.cos(t * 0.5) * 4,
    }
  }
  return { x: 0, y: 0 }
})

const irisStyle = computed(() => {
  if (reduced.value) {
    return { '--gaze-x': '0px', '--gaze-y': '0px', transition: 'none' }
  }
  return {
    '--gaze-x': `${uni.upx2px(gaze.value.x)}px`,
    '--gaze-y': `${uni.upx2px(gaze.value.y)}px`,
  }
})

let blinkTimer = null
let lidTimer = null
let motionTimer = null

function clearTimers() {
  if (blinkTimer) {
    clearTimeout(blinkTimer)
    blinkTimer = null
  }
  if (lidTimer) {
    clearTimeout(lidTimer)
    lidTimer = null
  }
}

function clearMotion() {
  if (motionTimer) {
    clearInterval(motionTimer)
    motionTimer = null
  }
}

function startMotion() {
  clearMotion()
  if (reduced.value) return
  motionTimer = setInterval(() => {
    motionTick.value += 1
  }, 650)
}

function blinkOnce(done) {
  blinking.value = true
  lidTimer = setTimeout(() => {
    blinking.value = false
    done()
  }, 140)
}

function scheduleBlink() {
  clearTimers()
  if (reduced.value) return
  if (props.state !== 'idle' && props.state !== 'focus') return
  // 提高频率：空闲 2–3.8s，专注中 3.2–6s，并偶尔连眨两次。
  const min = props.state === 'focus' ? 3200 : 2000
  const max = props.state === 'focus' ? 6000 : 3800
  const delay = min + Math.random() * (max - min)
  blinkTimer = setTimeout(() => {
    blinkOnce(() => {
      if (Math.random() < 0.3) {
        blinkTimer = setTimeout(() => {
          blinkOnce(scheduleBlink)
        }, 150)
      } else {
        scheduleBlink()
      }
    })
  }, delay)
}

watch(
  () => props.state,
  () => {
    blinking.value = false
    scheduleBlink()
  }
)

watch(reduced, () => {
  blinking.value = false
  if (reduced.value) {
    clearMotion()
  } else {
    startMotion()
  }
  scheduleBlink()
})

onMounted(() => {
  startMotion()
  scheduleBlink()
})

onUnmounted(() => {
  clearTimers()
  clearMotion()
})
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.eye-gaze {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  /* 默认调色：放在 --ik-card 上 */
  --eye-sclera: var(--ik-card);
  --eye-iris: var(--ik-primary);
  --eye-pupil: var(--ik-t1);
  --eye-lid: var(--ik-card);
}
/* 放在 --ik-block 人格卡上：眼白用 on-block，瞳孔用 block，眼皮跟卡底一致 */
.eye-gaze.on-block {
  --eye-sclera: var(--ik-on-block);
  --eye-pupil: var(--ik-block);
  --eye-lid: var(--ik-block);
}

.eyes {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
  transform: scale(var(--eye-gaze-scale, 1));
  transform-origin: center;
  transition: transform 0.35s ease;
}

.eye {
  position: relative;
  width: 70rpx;
  height: 48rpx;
  border-radius: 50%;
  overflow: hidden;
  background: var(--eye-sclera);
}

.eye-inner {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  transition: transform 0.28s ease;
}

.iris {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 31rpx;
  height: 31rpx;
  margin: -15.5rpx 0 0 -15.5rpx;
  border-radius: 50%;
  background: var(--eye-iris);
  box-shadow: 0 0 12rpx var(--eye-iris);
  transform: translate(var(--gaze-x, 0), var(--gaze-y, 0));
  transition: transform 0.5s cubic-bezier(0.2, 0.7, 0.3, 1);
}

.pupil {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 15rpx;
  height: 15rpx;
  margin: -7.5rpx 0 0 -7.5rpx;
  border-radius: 50%;
  background: var(--eye-pupil);
}

.shine {
  position: absolute;
  left: 5rpx;
  top: 4rpx;
  width: 6rpx;
  height: 6rpx;
  border-radius: 50%;
  background: var(--ik-on-primary);
  opacity: 0.95;
}

/* 眨眼：整块眼皮盖下来，颜色等于卡底，所以看起来像眼睛合上 */
.lid {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--eye-lid);
  transform: scaleY(0);
  transform-origin: center;
  transition: transform 0.12s ease;
}
.is-blink .lid {
  transform: scaleY(1);
}

/* 状态 */
.is-focus .eye-inner {
  transform: scale(1.07);
}
.is-abandon .eye-inner {
  transform: translate(10rpx, 3rpx) scaleY(0.82);
}
.is-done .eye-inner {
  transform: translateY(-3rpx) scaleY(0.42);
}
.is-snooze .eye-inner {
  transform: scaleY(0.55);
}
.is-due .eye-inner {
  transform: scale(1.2);
}

/* 到点：双层脉冲环，跟着整体尺寸一起缩放 */
.pulse-wrap {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: scale(var(--eye-gaze-scale, 1));
  pointer-events: none;
}
.pulse {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 150rpx;
  height: 150rpx;
  margin: -75rpx 0 0 -75rpx;
  border: 3rpx solid var(--ik-primary);
  border-radius: 50%;
  animation: eye-pulse 1.1s ease-out infinite;
}
.pulse.p2 {
  border-width: 2rpx;
  animation-delay: 0.55s;
}

/* reduced motion：保留静态状态，关闭眨眼、视线过渡与脉冲 */
.is-reduced .iris,
.is-reduced .eye-inner,
.is-reduced .eyes {
  transition: none;
}
.is-reduced .pulse {
  animation: none;
  opacity: 0.35;
  transform: scale(0.9);
}

@keyframes eye-pulse {
  0% {
    opacity: 0.8;
    transform: scale(0.6);
  }
  100% {
    opacity: 0;
    transform: scale(1.3);
  }
}
</style>
