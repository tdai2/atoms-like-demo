/**
 * 「免费开始」入口的跨页面意图。
 *
 * 登录会离开当前页面（由平台登录页与 /auth/callback 接管），落点不由本应用决定，
 * 因此点击时先把意图写入 sessionStorage，等账号态解析为已登录后再消费：
 * 回到首页需求输入区并聚焦输入框，让用户可以直接开始生成。
 */

const INTENT_KEY = 'atoms:start-free-intent';

type FocusListener = () => void;

const focusListeners = new Set<FocusListener>();

/** sessionStorage 在部分隐私模式下不可用，读写失败时降级为「无意图」。 */
function safeSession(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function markStartFreeIntent(): void {
  try {
    safeSession()?.setItem(INTENT_KEY, '1');
  } catch {
    // 忽略：无法持久化意图时仍允许后续交互。
  }
}

export function peekStartFreeIntent(): boolean {
  try {
    return safeSession()?.getItem(INTENT_KEY) === '1';
  } catch {
    return false;
  }
}

/** 读取并清除意图，避免一次点击被重复消费。 */
export function consumeStartFreeIntent(): boolean {
  if (!peekStartFreeIntent()) return false;
  try {
    safeSession()?.removeItem(INTENT_KEY);
  } catch {
    // 忽略：读取已确认成功，清除失败不应阻断跳转。
  }
  return true;
}

/** 订阅「回到输入区并聚焦」事件，返回取消订阅函数。 */
export function onStartFreeFocus(listener: FocusListener): () => void {
  focusListeners.add(listener);
  return () => {
    focusListeners.delete(listener);
  };
}

/** 通知已挂载的首页需求输入区执行滚动与聚焦。 */
export function emitStartFreeFocus(): void {
  focusListeners.forEach((listener) => listener());
}
