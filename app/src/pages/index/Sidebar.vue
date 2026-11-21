<template>
  <view class="sidebar-root">
    <!-- 1. 侧边栏遮罩层（拖动时随位移渐显） -->
    <view
      v-if="(visible || dragOffset > 0) && !showAvatarViewer"
      class="sidebar-mask"
      :style="maskStyle"
      @click="closeSidebar"
    ></view>

    <!-- 2. 侧滑抽屉（支持跟手拖出 / 左滑关闭） -->
    <view
      class="sidebar-drawer"
      :class="{ 'is-open': visible, 'is-dragging': dragging || closeDragging }"
      :style="drawerStyle"
      @touchstart="onDrawerTouchStart"
      @touchmove="onDrawerTouchMove"
      @touchend="onDrawerTouchEnd"
      @touchcancel="onDrawerTouchEnd"
    >
      
      <!-- 顶部用户信息区 -->
      <view class="user-profile">
        <!-- 点击头像，只打开大图预览，不直接弹相册 -->
        <view class="avatar-wrapper" @click="openAvatarViewer">
          <image v-if="customAvatar" :src="customAvatar" class="avatar-img" mode="aspectFill" />
          <view v-else class="avatar-text">{{ userInitial }}</view>
        </view>
        
        <!-- 点击昵称跳转到编辑资料页 -->
        <text class="nickname" @click="editNickname">{{ displayNickname }}</text>
        
        <text class="username" @click="openAvatarViewer">@{{ username }} · 点击换头像</text>
      </view>

      <!-- 菜单列表区：纯文字，分组 + 主色胶囊选中 -->
      <view class="menu-list">
        <view v-for="group in menuGroups" :key="group.title" class="menu-group">
          <text class="menu-group-title">{{ group.title }}</text>
          <view
            v-for="item in group.items"
            :key="item.key"
            class="menu-item"
            :class="{ 'is-active': currentMenu === item.key }"
            @click="handleMenuClick(item)"
          >
            <text class="menu-text">{{ item.name }}</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 3. 👇 全屏头像预览与上传页面 👇 -->
    <view v-if="showAvatarViewer" class="avatar-viewer-page">
      <!-- 顶部导航 / 关闭按钮 -->
      <view class="viewer-header">
        <text class="close-btn" @click="closeAvatarViewer">✕</text>
      </view>

      <!-- 中间头像大图展示 -->
      <view class="viewer-content">
        <image v-if="customAvatar" :src="customAvatar" class="big-avatar" mode="aspectFill" />
        <view v-else class="big-avatar-text">{{ userInitial }}</view>
      </view>

      <!-- 底部操作区：自建相册 / 拍照入口 -->
      <view class="viewer-footer">
        <view class="viewer-actions">
          <view class="viewer-action" @click="pickAvatar('album')">
            <wd-icon name="image" custom-class="viewer-action__icon" />
            <text>从相册选择</text>
          </view>
          <view class="viewer-action" @click="pickAvatar('camera')">
            <wd-icon name="camera" custom-class="viewer-action__icon" />
            <text>拍照</text>
          </view>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup>
// 👇 新增引入了 watch
import { computed, ref, onMounted, watch } from 'vue'
import { store } from '../../store.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  currentMenu: { type: String, default: 'study' },
  // 宿主页左边缘拖动时传入：0 表示未拖动
  dragOffset: { type: Number, default: 0 },
  dragging: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'select-menu'])

// ================= 抽屉跟随手势 =================
const closeDrag = ref(0)        // 已打开状态下左滑关闭的位移（负数 px）
const closeDragging = ref(false)
let drawerStartX = 0
let drawerStartY = 0
let drawerAxisLocked = false

function drawerWidth() {
  try {
    const width = uni.getSystemInfoSync().windowWidth || 375
    return Math.min(width * 0.76, 320)
  } catch (e) {
    return 280
  }
}

const drawerStyle = computed(() => {
  if (props.visible) {
    return closeDrag.value ? { transform: `translateX(${closeDrag.value}px)` } : {}
  }
  if (props.dragOffset > 0) {
    return { transform: `translateX(calc(-100% + ${props.dragOffset}px))` }
  }
  return {}
})

const maskStyle = computed(() => {
  if (props.visible || !props.dragOffset) return {}
  const opacity = Math.min(1, props.dragOffset / Math.max(1, drawerWidth()))
  return { opacity }
})

function onDrawerTouchStart(e) {
  if (!props.visible || showAvatarViewer.value) return
  const t = e.touches && e.touches[0]
  if (!t) return
  drawerStartX = t.clientX
  drawerStartY = t.clientY
  drawerAxisLocked = false
  closeDrag.value = 0
  closeDragging.value = true
}

function onDrawerTouchMove(e) {
  if (!closeDragging.value) return
  const t = e.touches && e.touches[0]
  if (!t) return
  const dx = t.clientX - drawerStartX
  const dy = t.clientY - drawerStartY
  if (!drawerAxisLocked) {
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return
    // 竖向滚动、或向右拖：不拦截
    if (Math.abs(dy) > Math.abs(dx) || dx > 0) {
      closeDragging.value = false
      closeDrag.value = 0
      return
    }
    drawerAxisLocked = true
  }
  closeDrag.value = Math.max(-drawerWidth(), Math.min(0, dx))
}

function onDrawerTouchEnd() {
  if (!closeDragging.value) return
  const shouldClose = closeDrag.value < -Math.max(56, drawerWidth() * 0.22)
  closeDragging.value = false
  closeDrag.value = 0
  if (shouldClose) closeSidebar()
}

watch(() => props.visible, (visible) => {
  if (visible) return
  closeDragging.value = false
  closeDrag.value = 0
})

const menuGroups = [
  {
    title: '导航',
    items: [
      { name: '学习', key: 'study' },
      { name: '自律', key: 'self' },
      { name: '我的', key: 'profile' },
    ],
  },
  {
    title: '功能',
    items: [
      { name: '学习路径', key: 'path' },
      { name: '学情诊断', key: 'diagnosis' },
      { name: '历史会话', key: 'history' },
    ],
  },
]

// ================= 👇 昵称显示逻辑 👇 =================
const customNickname = ref('')

// 显示优先级：本地修改的昵称 > 账号本身的后端昵称 > 账号名 > 默认小明
const displayNickname = computed(() => {
  if (customNickname.value) return customNickname.value
  return store.auth.user?.display_name || store.auth.user?.username || '小明'
})

const username = computed(() => store.auth.user?.username || 'xiaoming')
const userInitial = computed(() => displayNickname.value.charAt(0))

// 点击昵称跳转到编辑资料页
function editNickname() {
  closeSidebar() 
  uni.navigateTo({ url: '/pages/profile/edit' }) 
}
// ==========================================================

// --- 头像状态控制 ---
const customAvatar = ref('')
const showAvatarViewer = ref(false) // 控制全屏白底预览页显示

// 👇 抽离出读取缓存的函数
function loadUserInfoFromStorage() {
  const savedAvatar = uni.getStorageSync('user_avatar')
  customAvatar.value = savedAvatar || ''
  
  const savedNickname = uni.getStorageSync('custom_nickname')
  customNickname.value = savedNickname || ''
}

onMounted(() => {
  loadUserInfoFromStorage()
})

// 👇 新增：监听 visible 属性，只要侧边栏打开，就重新读取最新数据
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadUserInfoFromStorage()
  }
})

// 打开全屏预览页
function openAvatarViewer() {
  showAvatarViewer.value = true
}

// 关闭全屏预览页
function closeAvatarViewer() {
  showAvatarViewer.value = false
}

// 在预览页中选择来源，直接调用对应相册/相机
function pickAvatar(sourceType) {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [sourceType],
    success: (res) => {
      const tempFilePath = res.tempFilePaths[0]
      
      // #ifdef H5
      const reader = new FileReader()
      reader.onload = (e) => {
        customAvatar.value = e.target.result
        uni.setStorageSync('user_avatar', e.target.result)
        uni.showToast({ title: '头像修改成功', icon: 'success' })
      }
      reader.readAsDataURL(res.tempFiles[0])
      // #endif
      
      // #ifndef H5
      uni.getFileSystemManager().readFile({
        filePath: tempFilePath,
        encoding: 'base64',
        success: (data) => {
          const base64Str = 'data:image/jpeg;base64,' + data.data
          customAvatar.value = base64Str
          uni.setStorageSync('user_avatar', base64Str)
          uni.showToast({ title: '头像修改成功', icon: 'success' })
        }
      })
      // #endif
    }
  })
}

function closeSidebar() {
  emit('close')
}

function handleMenuClick(item) {
  emit('select-menu', item)
  closeSidebar()
}
</script>

<style scoped>
/* --- 原有侧边栏样式 --- */
.sidebar-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4); z-index: 1000;
  transition: opacity 0.18s ease;
}
.sidebar-drawer {
  position: fixed; top: 0; left: 0; bottom: 0;
  width: 76%; max-width: 320px; background: var(--ik-card); z-index: 1001;
  transform: translateX(-100%); transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  display: flex; flex-direction: column;
  border-top-right-radius: 30px; border-bottom-right-radius: 30px;
}
.sidebar-drawer.is-open { transform: translateX(0); }
/* 跟手拖动时取消过渡，松手后再恢复动画 */
.sidebar-drawer.is-dragging { transition: none; }

.user-profile { padding: 60px 24px 32px 24px; display: flex; flex-direction: column; }
.avatar-wrapper {
  width: 64px; height: 64px; border-radius: 50%; position: relative;
  margin-bottom: 16px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.avatar-img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.avatar-text {
  width: 100%; height: 100%; background: var(--ik-primary-weak); color: var(--ik-primary);
  font-size: 28px; font-weight: 600; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.nickname {
  font-size: 20px;
  font-weight: 600;
  color: var(--ik-t1);
  margin-bottom: 4px;
  cursor: pointer;
  display: inline-block;
  width: fit-content;
}
.nickname:hover {
  opacity: 0.7;
}

.username { font-size: 12px; color: var(--ik-t3); cursor: pointer; }

.menu-list { flex: 1; padding: 4px 12px 24px; overflow-y: auto; }
.menu-group + .menu-group { margin-top: 18px; }
.menu-group-title {
  display: block;
  padding: 0 14px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ik-t3);
}
.menu-item {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 14px;
  margin-bottom: 4px;
  border-radius: 12px;
  cursor: pointer;
}
.menu-item:not(.is-active):active { background: var(--ik-soft); }
.menu-item.is-active { background: var(--ik-primary-weak); }
.menu-text { font-size: 15px; color: var(--ik-t1); }
.menu-item.is-active .menu-text { color: var(--ik-primary); font-weight: 600; }


/* --- 👇 全屏预览页样式 👇 --- */
.avatar-viewer-page {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: var(--ik-bg); 
  z-index: 2000; 
  display: flex;
  flex-direction: column;
}

.viewer-header {
  padding: 40px 20px;
  display: flex;
  align-items: center;
}
.close-btn {
  font-size: 24px;
  color: var(--ik-t1);
  cursor: pointer;
  padding: 10px;
  font-weight: 300;
}

.viewer-content {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding-bottom: 80px; 
}

.big-avatar {
  width: 300px;
  height: 300px;
  border-radius: 50%; 
  object-fit: cover;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1); 
  background: var(--ik-card);
}

.big-avatar-text {
  width: 240px;
  height: 240px;
  border-radius: 50%; 
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-size: 90px;
  font-weight: bold;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.05);
}

.viewer-footer {
  position: absolute;
  bottom: calc(24px + env(safe-area-inset-bottom));
  left: 20px;
  right: 20px;
}

.viewer-actions {
  display: flex;
  background: var(--ik-card);
  border: 1px solid var(--ik-line);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}
.viewer-action {
  flex: 1;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 16px;
  color: var(--ik-t1);
  cursor: pointer;
}
.viewer-action + .viewer-action {
  border-left: 1px solid var(--ik-line);
}
.viewer-action:active {
  background: var(--ik-soft);
}
.viewer-action__icon {
  font-size: 20px;
  color: var(--ik-primary);
}
</style>