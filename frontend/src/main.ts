import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import DashboardPage from './pages/DashboardPage.vue'
import DiagnosePage from './pages/DiagnosePage.vue'
import IncidentsPage from './pages/IncidentsPage.vue'
import IncidentDetailPage from './pages/IncidentDetailPage.vue'
import InfrastructurePage from './pages/InfrastructurePage.vue'
import SupportPage from './pages/SupportPage.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
import FaqPage from './pages/FaqPage.vue'
import DailyReportsPage from './pages/DailyReportsPage.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/diagnose' },
    { path: '/login', redirect: '/diagnose' },
    { path: '/dashboard', component: DashboardPage, meta: { title: 'Dashboard' } },
    { path: '/diagnose', component: DiagnosePage, meta: { title: 'Quick Diagnose' } },
    { path: '/incidents', component: IncidentsPage, meta: { title: 'Incidents' } },
    { path: '/incidents/active', component: IncidentsPage, props: { status: 'active' }, meta: { title: 'Active Incidents' } },
    { path: '/incidents/resolved', component: IncidentsPage, props: { status: 'resolved' }, meta: { title: 'Resolved Incidents' } },
    { path: '/incidents/examples', component: IncidentsPage, props: { status: 'examples' }, meta: { title: 'Example Incidents' } },
    { path: '/incidents/:incidentId', component: IncidentDetailPage, meta: { title: 'Incident Workspace' } },
    ...['overview', 'kubernetes', 'database', 'api', 'llm', 'storage'].map(section => ({ path: `/infrastructure/${section}`, component: InfrastructurePage, props: { section }, meta: { title: 'Infrastructure' } })),
    { path: '/infrastructure', redirect: '/infrastructure/overview' },
    { path: '/knowledge/raft', component: KnowledgePage, meta: { title: 'Knowledge' } },
    ...['runbooks', 'documents'].map(section => ({ path: `/knowledge/${section}`, component: SupportPage, props: { section, area: 'Knowledge' }, meta: { title: 'Knowledge' } })),
    { path: '/knowledge', redirect: '/knowledge/raft' },
    { path: '/faq', component: FaqPage, meta: { title: 'FAQ Dashboard' } },
    { path: '/reports', component: DailyReportsPage, meta: { title: 'Daily Reports' } },
    ...['logs', 'tools', 'audit', 'settings'].map(section => ({ path: `/${section}`, component: SupportPage, props: { section, area: section }, meta: { title: section[0].toUpperCase() + section.slice(1) } })),
  ],
})

createApp(App).use(router).mount('#app')
