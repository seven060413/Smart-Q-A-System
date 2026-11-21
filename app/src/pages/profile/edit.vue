<template>
  <view class="page theme-root" :style="themeVars">
    <ThemeBackground />
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

      <!-- 年级 -->
      <view class="info-item" @click="openGradeModal">
        <text class="info-label">年级</text>
        <view class="info-value-box">
          <text class="info-value" :class="{ 'is-empty': !displayGrade }">
            {{ displayGrade || '未设置' }}
          </text>
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

    <!-- 👇 年级选择底部抽屉 👇 -->
    <view v-if="showGradeModal" class="modal-mask grade-mask" @click="closeGradeModal">
      <view class="grade-sheet" @click.stop>
        <view class="sheet-handle"></view>
        <text class="sheet-title">选择年级</text>
        <text class="sheet-subtitle">
          诊断、错题和学情趋势默认按这个年级展示；聊天仍按内容跨年级回答。
        </text>

        <view class="grade-section">
          <text class="grade-section-label">小学</text>
          <view class="grade-grid">
            <view
              v-for="item in primaryGrades"
              :key="item.value"
              class="grade-chip"
              :class="{ active: tempGrade === item.value }"
              @click="tempGrade = item.value"
            >
              <text>{{ item.label }}</text>
              <text v-if="tempGrade === item.value" class="grade-check">✓</text>
            </view>
          </view>
        </view>

        <view class="grade-section">
          <text class="grade-section-label">初中</text>
          <view class="grade-grid">
            <view
              v-for="item in juniorGrades"
              :key="item.value"
              class="grade-chip"
              :class="{ active: tempGrade === item.value }"
              @click="tempGrade = item.value"
            >
              <text>{{ item.label }}</text>
              <text v-if="tempGrade === item.value" class="grade-check">✓</text>
            </view>
          </view>
        </view>

        <view
          class="grade-chip grade-chip-none"
          :class="{ active: tempGrade === null }"
          @click="tempGrade = null"
        >
          暂不设置
        </view>

        <view class="modal-actions grade-actions">
          <view class="modal-btn cancel" @click="closeGradeModal">取消</view>
          <view class="modal-btn confirm" @click="saveGrade">保存</view>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { store } from '../../store.js'
import { updateProfile } from '../../api.js'
import { themeVars } from '../../theme/theme.js'

// 年级选项：与后端 users.grade 的 1-9 一一对应。
// 诊断/趋势/错题只接受 1-9；高中年级不在本次「我的」资料范围内。
const GRADE_OPTIONS = [
  { value: 1, label: '一年级' },
  { value: 2, label: '二年级' },
  { value: 3, label: '三年级' },
  { value: 4, label: '四年级' },
  { value: 5, label: '五年级' },
  { value: 6, label: '六年级' },
  { value: 7, label: '七年级' },
  { value: 8, label: '八年级' },
  { value: 9, label: '九年级' },
]
const primaryGrades = GRADE_OPTIONS.slice(0, 6)
const juniorGrades = GRADE_OPTIONS.slice(6)

const customAvatar = ref('')
const customNickname = ref('')
const customGrade = ref(null)
const saving = ref(false)

// 弹窗状态
const showNicknameModal = ref(false)
const tempNickname = ref('')
const showGradeModal = ref(false)
const tempGrade = ref(null)

// 显示的用户名
const displayNickname = computed(() => {
  if (customNickname.value) return customNickname.value
  return store.auth.user?.display_name || store.auth.user?.username || '未登录'
})

// 当前年级：本地/后端任一来源，null 表示未设置。
const currentGrade = computed(() => {
  if (customGrade.value != null) return customGrade.value
  const backendGrade = store.auth.user?.grade
  return Number.isInteger(backendGrade) ? backendGrade : null
})

const displayGrade = computed(() => {
  const item = GRADE_OPTIONS.find((g) => g.value === currentGrade.value)
  return item ? item.label : ''
})

// 首字母
const userInitial = computed(() => displayNickname.value.charAt(0))

onMounted(() => {
  // 优先用后端返回的 avatar，fallback 到本地缓存
  if (store.auth.user?.avatar) {
    customAvatar.value = store.auth.user.avatar
  } else {
    const savedAvatar = uni.getStorageSync('user_avatar')
    if (savedAvatar) customAvatar.value = savedAvatar
  }
  
  // 优先用后端返回的 display_name，fallback 到本地缓存
  if (store.auth.user?.display_name) {
    customNickname.value = store.auth.user.display_name
  } else {
    const savedNickname = uni.getStorageSync('custom_nickname')
    if (savedNickname) customNickname.value = savedNickname
  }

  // 年级：后端优先；游客/后端未设置时读取本地缓存。
  if (Number.isInteger(store.auth.user?.grade)) {
    customGrade.value = store.auth.user.grade
  } else {
    const savedGrade = uni.getStorageSync('user_grade')
    const parsed = Number(savedGrade)
    if (savedGrade !== '' && savedGrade != null && Number.isInteger(parsed) && parsed >= 1 && parsed <= 9) {
      customGrade.value = parsed
    }
  }
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
      reader.onload = async (e) => {
        const base64 = e.target.result
        customAvatar.value = base64
        uni.setStorageSync('user_avatar', base64)
        await saveAvatarToServer(base64)
      }
      reader.readAsDataURL(res.tempFiles[0])
      // #endif
      // #ifndef H5
      uni.getFileSystemManager().readFile({
        filePath: tempFilePath,
        encoding: 'base64',
        success: async (data) => {
          const base64Str = 'data:image/jpeg;base64,' + data.data
          customAvatar.value = base64Str
          uni.setStorageSync('user_avatar', base64Str)
          await saveAvatarToServer(base64Str)
        }
      })
      // #endif
    }
  })
}

/** 同步头像到后端 */
async function saveAvatarToServer(base64) {
  if (!store.auth.token) return
  try {
    saving.value = true
    const user = await updateProfile({ avatar: base64 })
    // 更新 store 和 localStorage
    if (store.auth.user) {
      store.auth.user.avatar = user.avatar
      store.auth.user.display_name = user.display_name
    }
    uni.setStorageSync('user_avatar', base64)
    uni.showToast({ title: '头像已同步保存', icon: 'success' })
  } catch (e) {
    console.error('头像同步失败:', e)
    uni.showToast({ title: '头像已保存到本地，同步失败', icon: 'none' })
  } finally {
    saving.value = false
  }
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

// ==================== 年级 ====================
function openGradeModal() {
  tempGrade.value = currentGrade.value
  showGradeModal.value = true
}

function closeGradeModal() {
  showGradeModal.value = false
}

/** 把年级同时写入页面状态、store 和本地缓存。 */
function applyGrade(value) {
  customGrade.value = value
  if (store.auth.user) store.auth.user.grade = value
  if (value != null) {
    uni.setStorageSync('user_grade', value)
  } else {
    uni.removeStorageSync('user_grade')
  }
}

async function saveGrade() {
  const next = tempGrade.value
  const previous = currentGrade.value
  const backendGrade = Number.isInteger(store.auth.user?.grade)
    ? store.auth.user.grade
    : null
  // 游客先存本地、登录后再打开编辑页时，即使显示值没变也要同步一次后端。
  const needsSync = !!store.auth.token && next !== backendGrade
  if (next === previous && !needsSync) {
    closeGradeModal()
    return
  }

  // 先乐观更新，保证从编辑页返回「我的」时立即可见。
  applyGrade(next)
  closeGradeModal()

  // 游客只存本地，登录后再次保存会同步到后端。
  if (!store.auth.token) {
    uni.showToast({ title: next ? '年级已保存到本地' : '已清除年级', icon: 'none' })
    return
  }

  try {
    saving.value = true
    const user = await updateProfile({ grade: next })
    const saved = Number.isInteger(user.grade) ? user.grade : null
    applyGrade(saved)
    uni.showToast({ title: next ? '年级已更新' : '已清除年级', icon: 'success' })
  } catch (e) {
    console.error('年级同步失败:', e)
    applyGrade(previous)
    uni.showToast({ title: '同步失败，请重试', icon: 'none' })
  } finally {
    saving.value = false
  }
}

// 保存昵称
async function saveNickname() {
  const newName = tempNickname.value.trim()
  if (!newName) {
    return uni.showToast({ title: '昵称不能为空', icon: 'none' })
  }
  if (newName.length > 20) {
    return uni.showToast({ title: '昵称不能超过20字', icon: 'none' })
  }
  
  customNickname.value = newName
  uni.setStorageSync('custom_nickname', newName)
  
  // 同步到后端
  if (store.auth.token) {
    try {
      saving.value = true
      const user = await updateProfile({ display_name: newName })
      if (store.auth.user) {
        store.auth.user.display_name = user.display_name
        store.auth.user.avatar = user.avatar
      }
    } catch (e) {
      console.error('昵称同步失败:', e)
      uni.showToast({ title: '昵称已保存本地，同步失败', icon: 'none' })
    } finally {
      saving.value = false
    }
  } else if (store.auth.user) {
    store.auth.user.display_name = newName
  }
  
  closeNicknameModal()
  uni.showToast({ title: '修改成功', icon: 'success' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background-color: var(--ik-bg);
}

/* 顶部导航栏 */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 44px 20px 16px 20px;
  background: var(--ik-bg);
}
.back-btn {
  font-size: 32px;
  color: var(--ik-t1);
  width: 40px;
  cursor: pointer;
  font-weight: 300;
  line-height: 1;
}
.nav-title {
  font-size: 18px;
  font-weight: bold;
  color: var(--ik-t1);
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
  background: var(--ik-soft);
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
  color: var(--ik-on-primary);
  font-weight: bold;
}
.camera-badge {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 28px;
  height: 28px;
  background: var(--ik-card);
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  box-shadow: 0 2px 6px rgba(0,0,0,0.15);
}
.camera-lens {
  width: 14px;
  height: 12px;
  border: 2px solid var(--ik-t1);
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
  background: var(--ik-t1);
}

/* 列表卡片区域 */
.info-card {
  background: var(--ik-card);
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
  color: var(--ik-t1);
}
.info-value-box {
  display: flex;
  align-items: center;
  gap: 8px;
}
.info-value {
  font-size: 15px;
  color: var(--ik-t2);
}
.info-arrow {
  font-size: 22px;
  color: var(--ik-t3);
  line-height: 1;
}
.info-item + .info-item {
  border-top: 1px solid var(--ik-line);
}
.info-value.is-empty {
  color: var(--ik-t3);
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
  background: var(--ik-card);
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
  color: var(--ik-t1);
  margin-bottom: 20px;
}

.modal-input-wrapper {
  background: var(--ik-bg);
  border-radius: 12px;
  padding: 0 16px;
  margin-bottom: 24px;
  border: 1px solid var(--ik-line);
}

.modal-input {
  height: 48px;
  font-size: 16px;
  color: var(--ik-t1);
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
  background: var(--ik-bg);
  color: var(--ik-t2);
}

.modal-btn.confirm {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

/* ================= 👇 年级底部抽屉 👇 ================= */
.grade-mask {
  align-items: flex-end;
}

.grade-sheet {
  width: 100%;
  max-width: 520px;
  background: var(--ik-card);
  border-radius: 24px 24px 0 0;
  padding: 10px 20px 28px;
  box-sizing: border-box;
  animation: slideUp 0.24s ease;
}

.sheet-handle {
  width: 40px;
  height: 4px;
  margin: 0 auto 14px;
  border-radius: 999px;
  background: var(--ik-line);
}

.sheet-title {
  display: block;
  text-align: center;
  font-size: 18px;
  font-weight: bold;
  color: var(--ik-t1);
}

.sheet-subtitle {
  display: block;
  margin-top: 6px;
  text-align: center;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ik-t3);
}

.grade-section {
  margin-top: 18px;
}

.grade-section-label {
  display: block;
  margin-left: 4px;
  font-size: 12px;
  color: var(--ik-t3);
  letter-spacing: 0.5px;
}

.grade-grid {
  display: flex;
  flex-wrap: wrap;
  margin: 8px -4px 0;
}

.grade-chip {
  position: relative;
  width: calc(33.333% - 8px);
  margin: 0 4px 8px;
  padding: 12px 0;
  text-align: center;
  font-size: 14px;
  color: var(--ik-t1);
  background: var(--ik-bg);
  border: 1px solid transparent;
  border-radius: 12px;
  box-sizing: border-box;
  cursor: pointer;
}

.grade-chip.active {
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
  border-color: var(--ik-primary);
  font-weight: 600;
}

.grade-check {
  position: absolute;
  top: 3px;
  right: 7px;
  font-size: 10px;
  line-height: 1;
  color: var(--ik-primary);
}

.grade-chip-none {
  width: calc(100% - 8px);
  margin-top: 2px;
  color: var(--ik-t3);
}

.grade-actions {
  margin-top: 18px;
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
@keyframes slideUp {
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}
</style>