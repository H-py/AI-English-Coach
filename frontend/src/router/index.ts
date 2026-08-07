import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getAccessToken } from '@/utils'

/**
 * 路由表。
 *
 * 布局与路由配合：
 *  - `/` 走 DefaultLayout（侧边栏 + 顶栏 + 内容区），其下挂载各业务视图，
 *    整体 requiresAuth，未登录将被守卫重定向到 /login。
 *  - `/admin` 走 AdminLayout（独立管理后台布局），其下挂载管理视图，
 *    整体 requiresAuth + requiresAdmin，非管理员将被重定向到 /。
 *  - `/login`、`/register` 走 AuthLayout（独立居中布局），已登录用户访问会被重定向。
 *  - 兜底 404 -> NotFoundView。
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue'),
        meta: { title: 'Home' }
      },
      {
        path: 'articles',
        name: 'articles',
        component: () => import('@/views/ArticleListView.vue'),
        meta: { title: 'Articles' }
      },
      {
        path: 'articles/:id',
        name: 'article-detail',
        component: () => import('@/views/ArticleDetailView.vue'),
        meta: { title: 'Article Detail' }
      },
      {
        path: 'vocabulary',
        name: 'vocabulary',
        component: () => import('@/views/VocabularyView.vue'),
        meta: { title: 'Vocabulary' }
      },
      {
        path: 'sentences',
        name: 'sentences',
        component: () => import('@/views/SentenceCollectionView.vue'),
        meta: { title: 'Sentences' }
      },
      {
        path: 'history',
        name: 'history',
        component: () => import('@/views/ReadingHistoryView.vue'),
        meta: { title: 'Reading History' }
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: 'Profile' }
      }
    ]
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: '',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/DashboardView.vue'),
        meta: { title: 'Admin Dashboard' }
      },
      {
        path: 'articles',
        name: 'admin-articles',
        component: () => import('@/views/admin/ArticleListView.vue'),
        meta: { title: 'Article Management' }
      },
      {
        path: 'articles/new',
        name: 'admin-article-create',
        component: () => import('@/views/admin/ArticleEditView.vue'),
        meta: { title: 'Create Article' }
      },
      {
        path: 'articles/:id/edit',
        name: 'admin-article-edit',
        component: () => import('@/views/admin/ArticleEditView.vue'),
        meta: { title: 'Edit Article' }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/UserListView.vue'),
        meta: { title: 'User Management' }
      }
    ]
  },
  {
    path: '/login',
    component: () => import('@/layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        name: 'login',
        component: () => import('@/views/LoginView.vue'),
        meta: { title: 'Login' }
      }
    ]
  },
  {
    path: '/register',
    component: () => import('@/layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        name: 'register',
        component: () => import('@/views/RegisterView.vue'),
        meta: { title: 'Register' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: 'Not Found' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

/**
 * 全局路由守卫：
 *  - 页面刷新后首次导航时，若本地有 token 则从后端拉取最新用户信息，
 *    确保 role 等字段与数据库一致（避免 localStorage 中旧数据导致角色判断错误）；
 *  - 目标路由需要认证且当前未登录 -> 跳 /login，并带上 redirect query；
 *  - 目标路由需要管理员且当前非管理员 -> 跳 /；
 *  - 已登录但访问 /login 或 /register -> 根据角色跳转首页或管理后台；
 *  - 其余放行。
 */

/** 标记本次页面生命周期内是否已从后端刷新过用户信息 */
let userInitialized = false

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // 页面刷新后首次导航：若有 token 则拉取最新用户信息，防止 localStorage 旧数据导致角色判断错误
  if (!userInitialized) {
    userInitialized = true
    if (getAccessToken()) {
      try {
        await auth.fetchUser()
      } catch {
        // token 无效或过期，清除本地认证态并跳转登录
        auth.clearAuth()
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }
  }

  // 需要认证但未登录
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 需要管理员但非管理员
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { path: '/' }
  }

  // 已登录却访问登录/注册页 -> 根据角色跳转
  if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return { path: auth.isAdmin ? '/admin' : '/' }
  }

  return true
})

export default router
