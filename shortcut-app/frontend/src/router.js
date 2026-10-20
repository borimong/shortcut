import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth.js'
import { CHANGE_ROLES } from './labels.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'landing', component: () => import('./views/LandingView.vue'), meta: { public: true, landing: true } },
    { path: '/board', name: 'board', component: () => import('./views/BoardView.vue') },
    { path: '/callsheet', name: 'callsheet', component: () => import('./views/CallsheetView.vue') },
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
  scrollBehavior: (to) => (to.hash ? { el: to.hash, top: 72, behavior: 'smooth' } : { top: 0 })
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    return auth.isLoggedIn && to.name === 'login' ? '/board' : true
  }
  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles && !to.meta.roles.includes(auth.user?.role)) {
    return '/board'
  }
  return true
})

export default router
