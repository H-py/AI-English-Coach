import { http } from './request'
import type {
  LoginResponse,
  RegisterPayload,
  LoginPayload,
  TokenResponse,
  User,
  UpdateUserPayload
} from '@/types/auth'

/**
 * 认证与用户相关 API 封装。
 *
 * http 已在响应拦截器中对后端统一信封解包，因此各方法直接返回业务数据。
 * 需 Bearer token 的接口由请求拦截器自动注入。
 */
export const authApi = {
  /** 注册：成功后返回 access/refresh token 与用户信息 */
  register(data: RegisterPayload): Promise<LoginResponse> {
    return http.post('/auth/register', data)
  },

  /** 登录：成功后返回 access/refresh token 与用户信息 */
  login(data: LoginPayload): Promise<LoginResponse> {
    return http.post('/auth/login', data)
  },

  /** 刷新 access token */
  refresh(refreshToken: string): Promise<TokenResponse> {
    return http.post('/auth/refresh', { refresh_token: refreshToken })
  },

  /** 登出：需登录态，服务端可使当前令牌失效 */
  logout(): Promise<void> {
    return http.post('/auth/logout')
  },

  /** 获取当前登录用户信息 */
  getMe(): Promise<User> {
    return http.get('/users/me')
  },

  /** 更新当前用户资料（头像 / 英语水平） */
  updateMe(data: UpdateUserPayload): Promise<User> {
    return http.put('/users/me', data)
  }
}
