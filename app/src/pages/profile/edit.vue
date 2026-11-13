<template>
  <view class="page">
    <!-- 1. 自定义顶部导航栏 -->
    <view class="nav-bar">
      <text class="back-btn" @click="goBack">‹</text>
      <text class="nav-title">编辑资料</text>
      <text class="nav-space"></text>
    </view>

    <!-- 2. 头像展示区 -->
    <view class="avatar-section">
      <view class="avatar-container" @click="changeAvatar">
        <image v-if="customAvatar" :src="customAvatar" class="avatar-img" mode="aspectFill" />
        <view v-else class="avatar-text">{{ userInitial }}</view>
        <!-- 右下角的相机图标 -->
        <view class="camera-badge">
          <view class="camera-lens"></view>
        </view>
      </view>
    </view>

    <!-- 3. 表单信息区 -->
    <view class="info-card">
      <!-- 昵称 -->
      <view class="info-item" @click="openNicknameModal">
        <text class="info-label">昵称</text>
        <view class="info-value-box">
          <text class="info-value">{{ displayNickname }}</text>
          <text class="info-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 👇 4. 自定义的精美修改昵称弹窗 👇 -->
    <view v-if="showNicknameModal" class="modal-mask" @click="closeNicknameModal">
      <!-- 阻止点击内容区关闭弹窗 -->
      <view class="modal-content" @click.stop>
        <text class="modal-title">修改昵称</text>
        
        <!-- 输入框 -->
        <view class="modal-input-wrapper">
          <input 
            class="modal-input" 
            type="text" 
            v-model="tempNickname" 
            placeholder="请输入新昵称"
            :maxlength="20"
            focus
          />
        </view>
        
        <!-- 按钮组 -->
        <view class="modal-actions">
          <view class="modal-btn cancel" @click="closeNicknameModal">取消</view>
          <view class="modal-btn confirm" @click="saveNickname">确定</view>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { store } from '../../store.js'

const customAvatar = ref('')
const customNickname = ref('')

// 弹窗状态
const showNicknameModal = ref(false)
const tempNickname = ref('')

// 显示的用户名
const displayNickname = computed(() => {
  if (customNickname.value) return customNickname.value
  return store.auth.user?.display_name || store.auth.user?.username || '未登录'
})

// 首字母
const userInitial = computed(() => displayNickname.value.charAt(0))

onMounted(() => {
  const savedAvatar = uni.getStorageSync('user_avatar')
  if (savedAvatar) customAvatar.value = savedAvatar
  
  const savedNickname = uni.getStorageSync('custom_nickname')
  if (savedNickname) customNickname.value = savedNickname
})

// 返回上一页
function goBack() {
  uni.navigateBack()
}

// 修改头像逻辑
function changeAvatar() {
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
        uni.showToast({ title: '头像修改成功', icon: 'none' })
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
          uni.showToast({ title: '头像修改成功', icon: 'none' })
        }
      })
      // #endif
    }
  })
}

// 打开自定义弹窗
function openNicknameModal() {
  tempNickname.value = displayNickname.value // 默认填入当前名字
  showNicknameModal.value = true
}

// 关闭弹窗
function closeNicknameModal() {
  showNicknameModal.value = false
}

// 保存昵称
function saveNickname() {
  const newName = tempNickname.value.trim()
  if (!newName) {
    return uni.showToast({ title: '昵称不能为空', icon: 'none' })
  }
  if (newName.length > 20) {
    return uni.showToast({ title: '昵称不能超过20字', icon: 'none' })
  }
  
  customNickname.value = newName
  uni.setStorageSync('custom_nickname', newName)
  if (store.auth.user) store.auth.user.display_name = newName
  
  closeNicknameModal()
  uni.showToast({ title: '修改成功', icon: 'success' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background-color: #f5f6f8;
}

/* 顶部导航栏 */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 44px 20px 16px 20px;
  background: #f5f6f8;
}
.back-btn {
  font-size: 32px;
  color: #333;
  width: 40px;
  cursor: pointer;
  font-weight: 300;
  line-height: 1;
}
.nav-title {
  font-size: 18px;
  font-weight: bold;
  color: #000;
}
.nav-space {
  width: 40px;
}

/* 头像区域 */
.avatar-section {
  display: flex;
  justify-content: center;
  padding: 20px 0 40px 0;
}
.avatar-container {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  position: relative;
  cursor: pointer;
  background: #8daebf;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}
.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}
.avatar-text {
  font-size: 40px;
  color: #fff;
  font-weight: bold;
}
.camera-badge {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 28px;
  height: 28px;
  background: #fff;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 2px 6px rgba(0,0,0,0.15);
}
.camera-lens {
  width: 14px;
  height: 12px;
  border: 2px solid #333;
  border-radius: 3px;
  position: relative;
}
.camera-lens::after {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 4px; height: 4px;
  border-radius: 50%;
  background: #333;
}

/* 列表卡片区域 */
.info-card {
  background: #ffffff;
  border-radius: 16px;
  margin: 0 20px;
  padding: 0 20px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.02);
}
.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 0;
  cursor: pointer;
}
.info-label {
  font-size: 16px;
  font-weight: bold;
  color: #000;
}
.info-value-box {
  display: flex;
  align-items: center;
  gap: 8px;
}
.info-value {
  font-size: 15px;
  color: #666;
}
.info-arrow {
  font-size: 22px;
  color: #ccc;
  line-height: 1;
}

/* ================= 👇 自定义弹窗样式 👇 ================= */
.modal-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 9999;
  display: flex;
  justify-content: center;
  align-items: center;
  animation: fadeIn 0.2s ease;
}

.modal-content {
  width: 80%;
  max-width: 320px;
  background: #ffffff;
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.1);
  animation: scaleUp 0.2s ease;
}

.modal-title {
  display: block;
  text-align: center;
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin-bottom: 20px;
}

.modal-input-wrapper {
  background: #f5f6f8;
  border-radius: 12px;
  padding: 0 16px;
  margin-bottom: 24px;
  border: 1px solid #eee;
}

.modal-input {
  height: 48px;
  font-size: 16px;
  color: #333;
}

.modal-actions {
  display: flex;
  gap: 12px;
}

.modal-btn {
  flex: 1;
  height: 44px;
  line-height: 44px;
  text-align: center;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
}

.modal-btn.cancel {
  background: #f5f6f8;
  color: #666;
}

.modal-btn.confirm {
  background: #2f6fd0;
  color: #fff;
}

/* 简单的动画效果 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes scaleUp {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
</style>