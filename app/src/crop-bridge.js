/**
 * renderjs -> 逻辑层的回调桥。
 *
 * uni-app 的 renderjs 通过 ownerInstance.callMethod 调用页面 methods；
 * <script setup> 里的函数默认不在实例 methods 上，所以用这个模块把
 * setup 里的处理函数挂到 Options API 的 methods 上。
 */
export const cropBridge = {
  onWarped: null,
  onWarpError: null,
}
