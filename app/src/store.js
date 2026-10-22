import { reactive } from 'vue'

// 跨页面共享数据（首页拿到答案后，学习路径页从这里读）
export const store = reactive({
  learningPath: null, // { prerequisites: [], body: '', consolidation: [] }
  knowledgePoint: '',
  source: '',
})
