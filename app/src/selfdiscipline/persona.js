// 人格化文案：统一的“它”的语气，全部原创。
// A = 基础（温和），B = 严格（更短、更冷）。v1 只影响文案，不影响点数。

const LINES = {
  focus_start: {
    A: [
      '计时开始了。我在这儿，不说话。',
      '这一段归你了。我替你看着时间。',
      '好，开始吧。剩下的交给计时。'
    ],
    B: [
      '开始。别让我等太久。',
      '计时器走了。做你该做的。',
      '开始。别分心。'
    ]
  },
  focus_25: {
    A: [
      '还有一半多。别急着看表。',
      '进度不错，继续。',
      '时间还够。把手上这一段做完。'
    ],
    B: [
      '还剩不少。继续。',
      '别松。还早。',
      '中段最容易走神。稳住。'
    ]
  },
  focus_5: {
    A: [
      '最后五分钟了。收个尾。',
      '快到了。别在这时候分心。',
      '还剩一小段。坚持住。'
    ],
    B: [
      '还剩五分钟。别停。',
      '收尾。',
      '最后一点。做完。'
    ]
  },
  focus_done: {
    A: [
      '做到了。这次我记下了。',
      '时间到。你把它做完了。',
      '一段完整的专注。收好。'
    ],
    B: [
      '完成。下一件。',
      '时间到。记下了。',
      '做完了。可以走了。'
    ]
  },
  focus_early: {
    A: [
      '提前收工。理由你自己留着。',
      '没到点就结束了。记在这里。',
      '提前完成也算完成，点数按实际算。'
    ],
    B: [
      '提前结束。记下了。',
      '没到点。按实际算。',
      '提前。可以。'
    ]
  },
  focus_abandon: {
    A: [
      '停下了。原因可以晚点再说。',
      '这次没走完。我记了一笔。',
      '停在这里。下次再来。'
    ],
    B: [
      '停了。点数没有。',
      '放弃。记下。',
      '停了。'
    ]
  },
  report_start: {
    A: [
      '报备好了。我帮你记着时间。',
      '去吧。到点我会叫你。',
      '说好了几分钟就几分钟。我等着。'
    ],
    B: [
      '报备了。到点提醒。',
      '记下了。到点回来。',
      '去吧。别超。'
    ]
  },
  report_due: {
    A: [
      '你报备的时间到了。',
      '到点了。回来看一眼。',
      '时间到了。你说的那些分钟用完了。'
    ],
    B: [
      '到点了。',
      '时间到。回来。',
      '报备结束。'
    ]
  },
  report_done: {
    A: [
      '说结束就结束。这次算数。',
      '按时回来。不错。',
      '收住了。我记下这次。'
    ],
    B: [
      '完成。',
      '按时。记下。',
      '结束了。'
    ]
  },
  report_extend: {
    A: [
      '再给你五分钟。我继续看着。',
      '又多了五分钟。别让它变成习惯。',
      '好，延长一次。时间重新开始走。'
    ],
    B: [
      '五分钟。就一次。',
      '延长。别习惯。',
      '再五分钟。'
    ]
  },
  report_overdue: {
    A: [
      '已经超时了。不扣分，但你心里有数。',
      '过了点还没回来。我先把这笔挂着。',
      '超时未结算。等你想起来了再说。'
    ],
    B: [
      '超时了。',
      '过了。还没结算。',
      '超时。记着。'
    ]
  },
  checkin_due: {
    A: [
      '今天的清单还亮着。',
      '还有事情没划掉。',
      '看一眼今天的清单吧。'
    ],
    B: [
      '清单没清。',
      '还有没划的。',
      '清单。'
    ]
  },
  checkin_done: {
    A: [
      '划掉一项。很好。',
      '又少一件。继续。',
      '这一项今天不会再烦你了。'
    ],
    B: [
      '清一项。',
      '少一件。',
      '记下。'
    ]
  },
  checkin_all: {
    A: [
      '今天没有欠账。',
      '全清。今天可以了。',
      '清单空了。我记下这一天。'
    ],
    B: [
      '全清。',
      '清零。',
      '今天没有欠账。'
    ]
  },
  checkin_none: {
    A: [
      '今天还没有安排。要现在写一条吗？',
      '清单是空的。先加一条。',
      '没有任何每日事项。从一条开始。'
    ],
    B: [
      '空。去加一条。',
      '什么都没有。加。',
      '清单为空。'
    ]
  },
  empty_today: {
    A: [
      '今天还没有安排。要现在写一条吗？',
      '还没有记录。先开一场专注？',
      '这里很安静。你可以从一件小事开始。'
    ],
    B: [
      '空。开始。',
      '什么都没有。做点事。',
      '空着。'
    ]
  },
  stats_empty: {
    A: [
      '这段时间没有数据。先去做一点。',
      '还没有可统计的事情。',
      '空图表。等你的第一条记录。'
    ],
    B: [
      '没数据。',
      '空的。',
      '没有记录。'
    ]
  }
}

const counters = new Map()

function pickIndex(key, length) {
  const current = counters.get(key)
  let next
  if (current === undefined) {
    next = Math.floor(Math.random() * length)
  } else {
    next = (current + 1) % length
  }
  counters.set(key, next)
  return next
}

function interpolate(text, vars) {
  return String(text).replace(/\{(\w+)\}/g, (match, name) => {
    const value = vars && vars[name]
    return value === undefined || value === null ? '' : String(value)
  })
}

/**
 * 取一条人格文案。
 * @param {string} event 事件键
 * @param {'A'|'B'} strictness 严格度
 * @param {object} vars { task, minutes, done, left }
 */
export function personaLine(event, strictness = 'A', vars = {}) {
  const group = LINES[event]
  if (!group) return interpolate(vars && vars.fallback ? vars.fallback : '', vars)
  const tone = strictness === 'B' ? 'B' : 'A'
  const list = group[tone] && group[tone].length ? group[tone] : group.A
  const index = pickIndex(`${event}:${tone}`, list.length)
  return interpolate(list[index], vars)
}

/** 悬浮窗标题轮换（原创） */
export const GUARD_TITLES = ['我正在看哦', '看见你了', '别走太远']

export function guardTitle(seed = 0) {
  const index = Math.abs(Math.floor(Number(seed) || 0)) % GUARD_TITLES.length
  return GUARD_TITLES[index]
}

/** 通知文案：短、可读、不暴露目的 */
export function notificationText(kind, refName = '') {
  if (kind === 'focus') return { title: '专注结束', body: '时间到了。抬头。' }
  if (kind === 'report') return { title: '报备到点', body: '你报备的时间到了。' }
  return { title: '每日打卡', body: '今天的清单还亮着。' }
}
