/**
 * 把 OCR 文本按题号拆成多道题。
 *
 * 只在“行首”识别题号，避免把算式里的 1/2、1.5 当成题号。
 * 如果整段没有题号，就返回一个整体，最后仍按单题处理。
 * PDF 的 [第 N 页] 先作为分页边界；页内没有题号时不会强行拆开。
 */

const QUESTION_START = /^\s*(?:\d{1,2}\s*[.、．)）]|[（(]\s*\d{1,2}\s*[）)]|[①-⑳]|第\s*[一二三四五六七八九十\d]+\s*题)\s*/

// “一、选择题”“二、填空题”这类是分区标题，不是题目本身
const SECTION_HEADING = /^\s*[一二三四五六七八九十]{1,3}\s*[、.．]\s*(?:选择题|填空题|解答题|计算题|判断题|应用题|操作题|综合题)\s*$/

const PAGE_MARKER = /^\[第\s*\d+\s*页\]\s*$/gm

function splitBlock(block) {
  const lines = block
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line && !SECTION_HEADING.test(line))

  if (!lines.length) return []

  const groups = []
  let preamble = []
  let current = []
  let seenQuestion = false

  for (const line of lines) {
    if (QUESTION_START.test(line)) {
      if (seenQuestion && current.length) {
        groups.push(current.join('\n').trim())
      }
      // 第一题前面如果有说明文字，归到第一题
      current = seenQuestion ? [line] : [...preamble, line]
      seenQuestion = true
    } else if (seenQuestion) {
      current.push(line)
    } else {
      preamble.push(line)
    }
  }

  if (current.length) {
    groups.push(current.join('\n').trim())
  } else if (preamble.length) {
    groups.push(preamble.join('\n').trim())
  }

  return groups.filter(Boolean)
}

function hasQuestionStart(block) {
  return block
    .split(/\n+/)
    .some((line) => QUESTION_START.test(line.trim()))
}

export function splitQuestionText(input) {
  const raw = String(input == null ? '' : input).trim()
  if (!raw) return []

  const pageBlocks = raw
    .split(PAGE_MARKER)
    .map((block) => block.trim())
    .filter(Boolean)

  if (!pageBlocks.length) return []

  // 整份文本完全没有题号：不按页硬拆，避免把一道跨页题拆成两道
  if (!pageBlocks.some(hasQuestionStart)) {
    const merged = raw.replace(PAGE_MARKER, '').trim()
    return merged ? [merged] : []
  }

  const groups = []
  for (const block of pageBlocks) {
    groups.push(...splitBlock(block))
  }

  const cleaned = groups.filter(Boolean)
  return cleaned.length ? cleaned : [raw.replace(PAGE_MARKER, '').trim()]
}
