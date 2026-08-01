import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/**
 * 路由表。
 *
 * 布局与路由配合：
 *  - `/` 走 DefaultLayout（侧边栏 + 顶栏 + 内容区），其下挂载各业务视图，
 *    整体 requiresAuth，未登录将被守卫重定向到 /login。
 *  - `/login`、`/register` 走 AuthLayout（独立居中布局），已登录用户访问会被重定向回 `/`。
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
 *  - 目标路由需要认证且当前未登录 -> 跳 /login，并带上 redirect query 以便登录后回跳；
 *  - 已登录但访问 /login 或 /register -> 跳 /，避免重复登录；
 *  - 其余放行。
 *
 * 登录态基于 auth store 的 user 是否存在判断，user 通过 useStorage 恢复，
 * 因此刷新页面后仍保持有效。token 过期由 axios 401 拦截器兜底处理。
 */
router.beforeEach((to) => {
  const auth = useAuthStore()

  // 需要认证但未登录
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已登录却访问登录/注册页 -> 回首页
  if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return { path: '/' }
  }

  return true
})

export default router
