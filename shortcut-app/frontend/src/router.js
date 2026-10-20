import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth.js'
import { CHANGE_ROLES } from './labels.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'board', component: () => import('./views/BoardView.vue') },
    {
      path: '/changes/new',
      name: 'change-new',
      component: () => import('./views/ChangeNewView.vue'),
      meta: { roles: CHANGE_ROLES }
    },
    { path: '/tasks/:id', name: 'task', component: () => import('./views/TaskView.vue') },
    { path: '/proposals', name: 'proposals', component: () => import('./views/ProposalListView.vue') },
    { path: '/proposals/:id', name: 'proposal', component: () => import('./views/ProposalView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ],
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    return auth.isLoggedIn && to.name === 'login' ? '/' : true
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles && !to.meta.roles.includes(auth.user?.role)) {
    return '/'
  }
  return true
})

export default router
