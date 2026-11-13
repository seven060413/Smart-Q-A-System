<template>
  <view>
    <!-- 1. 侧边栏遮罩层 -->
    <view v-if="visible && !showAvatarViewer" class="sidebar-mask" @click="closeSidebar"></view>

    <!-- 2. 侧滑抽屉 -->
    <view class="sidebar-drawer" :class="{ 'is-open': visible }">
      
      <!-- 顶部用户信息区 -->
      <view class="user-profile">
        <!-- 点击头像，只打开大图预览，不直接弹相册 -->
        <view class="avatar-wrapper" @click="openAvatarViewer">
          <image v-if="customAvatar" :src="customAvatar" class="avatar-img" mode="aspectFill" />
          <view v-else class="avatar-text">{{ userInitial }}</view>
          <view class="camera-icon">📷</view>
        </view>
        
        <!-- 点击昵称跳转到编辑资料页 -->
        <text class="nickname" @click="editNickname">{{ displayNickname }}</text>
        
        <text class="username" @click="openAvatarViewer">@{{ username }} · 点击换头像</text>
      </view>

      <!-- 菜单列表区 -->
      <view class="menu-list">
        <view 
          v-for="(item, index) in menuItems" 
          :key="index"
          class="menu-item"
          :class="{ 'is-active': currentMenu === item.key }"
          @click="handleMenuClick(item)"
        >
          <view class="menu-icon" :class="{ 'icon-active': currentMenu === item.key }"></view>
          <text class="menu-text">{{ item.name }}</text>
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

      <!-- 底部操作区 -->
      <view class="viewer-footer">
        <view class="upload-btn" @click="triggerUpload">
          <text class="upload-text">上传新头像</text>
          <!-- 纯 CSS 绘制的精美图片图标 -->
          <view class="css-icon-image"></view>
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
  currentMenu: { type: String, default: 'study' }
})
const emit = defineEmits(['close', 'select-menu'])

const menuItems = [
  { name: '学习', key: 'study' },
  { name: '学习路径', key: 'path' },
  { name: '视频讲解', key: 'video' },
  { name: '历史会话', key: 'history' },
  { name: '我的', key: 'profile' }
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

// 在预览页中点击“上传新头像”，才真正触发相册
function triggerUpload() {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
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
}
.sidebar-drawer {
  position: fixed; top: 0; left: 0; bottom: 0;
  width: 76%; max-width: 320px; background: #fcfcfc; z-index: 1001;
  transform: translateX(-100%); transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  display: flex; flex-direction: column;
  border-top-right-radius: 30px; border-bottom-right-radius: 30px;
}
.sidebar-drawer.is-open { transform: translateX(0); }

.user-profile { padding: 60px 24px 32px 24px; display: flex; flex-direction: column; }
.avatar-wrapper {
  width: 64px; height: 64px; border-radius: 50%; position: relative;
  margin-bottom: 16px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.avatar-img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.avatar-text {
  width: 100%; height: 100%; background: #ffffff; color: #2f6fd0;
  font-size: 28px; font-weight: 600; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.camera-icon {
  position: absolute; bottom: -2px; right: -2px; width: 22px; height: 22px;
  background: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}

.nickname { 
  font-size: 20px; 
  font-weight: 600; 
  color: #1f2329; 
  margin-bottom: 4px; 
  cursor: pointer;
  display: inline-block;
  width: fit-content;
}
.nickname:hover {
  opacity: 0.7;
}

.username { font-size: 12px; color: #8a9099; cursor: pointer; }

.menu-list { flex: 1; padding: 0 16px; overflow-y: auto; }
.menu-item { display: flex; align-items: center; padding: 16px; margin-bottom: 8px; border-radius: 12px; cursor: pointer; }
.menu-item.is-active { background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
.menu-icon { width: 14px; height: 14px; border-radius: 4px; background: #dcdfe6; margin-right: 16px; }
.menu-icon.icon-active { background: #2f6fd0; }
.menu-text { font-size: 15px; color: #333; }
.menu-item.is-active .menu-text { color: #1f2329; font-weight: 600; }


/* --- 👇 全屏预览页样式 👇 --- */
.avatar-viewer-page {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #f5f6f8; 
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
  color: #333;
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
  background: #fff;
}

.big-avatar-text {
  width: 240px;
  height: 240px;
  border-radius: 50%; 
  background: #e8f0fb;
  color: #2f6fd0;
  font-size: 90px;
  font-weight: bold;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.05);
}

.viewer-footer {
  position: absolute;
  bottom: 40px;
  left: 20px;
  right: 20px;
}

.upload-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ffffff; 
  padding: 24px;
  border-radius: 16px;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.04); 
  border: 1px solid #eee;
}
.upload-text {
  font-size: 16px;
  font-weight: 500;
  color: #1f2329;
}

.css-icon-image {
  width: 22px;
  height: 22px;
  border: 2px solid #8a9099; 
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}
.css-icon-image::before {
  content: '';
  position: absolute;
  top: 4px;
  right: 4px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: #8a9099;
}
.css-icon-image::after {
  content: '';
  position: absolute;
  bottom: -3px;
  left: -3px;
  width: 18px;
  height: 18px;
  background-color: #8a9099;
  transform: rotate(45deg);
}
</style>