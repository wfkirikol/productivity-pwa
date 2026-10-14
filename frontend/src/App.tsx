import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDownLeft,
  ArrowUpRight,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  ClipboardList,
  Coins,
  ListChecks,
  Menu,
  Moon,
  Play,
  Plus,
  Square,
  Sparkles,
  Sun,
  Timer,
  Trash2,
  Wallet,
  WandSparkles,
  Zap,
  X,
} from 'lucide-react'

type ActivityStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED'
type Recurrence = 'ONCE' | 'DAILY' | 'WEEKLY' | 'MONTHLY'
type ActivityPriority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'
type EnergyLevel = 'LOW' | 'MEDIUM' | 'HIGH'
type TransactionKind = 'EXPENSE' | 'INCOME'
type ReflectionSection = 'CONFLICT' | 'PSYCHOLOGY' | 'THOUGHT'
type Page = 'activities' | 'finance' | 'reflections'
type Theme = 'light' | 'dark' | 'grove'

type Activity = {
  id: number
  title: string
  category: string
  due_date: string
  status: ActivityStatus
  progress: number
  recurrence: Recurrence
  priority: ActivityPriority
  estimated_minutes: number | null
  energy_level: EnergyLevel
  focus_seconds: number
  parent_activity_id: number | null
  next_occurrence_id: number | null
  checklist_items: ChecklistItem[]
}

type ChecklistItem = {
  id: number
  title: string
  completed: boolean
  position: number
}

type FocusSession = {
  id: number
  activity_id: number | null
  started_at: string
  ended_at: string | null
  duration_seconds: number
}

type DailyPlan = {
  plan_date: string
  available_minutes: number
  planned_minutes: number
  selected: Activity[]
  deferred: Activity[]
}

type AIResponse = {
  text: string
  fallback: boolean
  scenario: 'motivation' | 'time_management' | 'decomposition'
}

type Transaction = {
  id: number
  amount: string
  kind: TransactionKind
  category: string
  linked_activity_id: number | null
  occurred_at: string
  note: string | null
}

type Reflection = {
  id: number
  section: ReflectionSection
  title: string
  content: string
  created_at: string
}

type ActivityDraft = Pick<Activity, 'title' | 'category' | 'due_date'> & {
  recurrence: Recurrence
  priority: ActivityPriority
  estimated_minutes: number | null
  energy_level: EnergyLevel
}

type TransactionDraft = {
  amount: string
  kind: TransactionKind
  category: string
  linked_activity_id: number | null
  note: string
}

type ReflectionDraft = Pick<Reflection, 'section' | 'title' | 'content'>

const API_ROOT = '/api/v1'
const USER_ID = Number(localStorage.getItem('productivity-user-id') ?? '1') || 1
const currency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': String(USER_ID),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : body?.detail
    throw new Error(detail || `Ошибка запроса (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(new Date(value))
}

function sectionName(section: ReflectionSection) {
  return { CONFLICT: 'Конфликтология', PSYCHOLOGY: 'Психология', THOUGHT: 'Мысли' }[section]
}

function App() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState<Page>('activities')
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('productivity-theme') as Theme) || 'light')
  const [menuOpen, setMenuOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [aiResponses, setAiResponses] = useState<Record<number, AIResponse>>({})
  const [timeAdvice, setTimeAdvice] = useState<AIResponse | null>(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('productivity-theme', theme)
  }, [theme])

  const activitiesQuery = useQuery({ queryKey: ['activities'], queryFn: () => request<Activity[]>('/activities') })
  const transactionsQuery = useQuery({ queryKey: ['transactions'], queryFn: () => request<Transaction[]>('/transactions') })
  const reflectionsQuery = useQuery({ queryKey: ['reflections'], queryFn: () => request<Reflection[]>('/reflections') })
  const activeFocusQuery = useQuery({ queryKey: ['focus'], queryFn: () => request<FocusSession | null>('/focus/active') })
  const dailyPlanQuery = useQuery({ queryKey: ['daily-plan'], queryFn: () => request<DailyPlan>('/planning/today') })
  const activities = activitiesQuery.data ?? []
  const transactions = transactionsQuery.data ?? []
  const reflections = reflectionsQuery.data ?? []
  const activeFocus = activeFocusQuery.data ?? null
  const dailyPlan = dailyPlanQuery.data

  const invalidate = (key: string) => queryClient.invalidateQueries({ queryKey: [key] })
  const createActivity = useMutation({
    mutationFn: (draft: ActivityDraft) => request<Activity>('/activities', { method: 'POST', body: JSON.stringify(draft) }),
    onSuccess: () => {
      invalidate('activities')
      invalidate('daily-plan')
    },
  })
  const updateActivity = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<Activity> }) =>
      request<Activity>(`/activities/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
    onSuccess: () => {
      invalidate('activities')
      invalidate('daily-plan')
    },
  })
  const deleteActivity = useMutation({
    mutationFn: (id: number) => request<void>(`/activities/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate('activities')
      invalidate('transactions')
      invalidate('daily-plan')
      invalidate('focus')
    },
  })
  const addChecklistItem = useMutation({
    mutationFn: ({ activityId, title }: { activityId: number; title: string }) =>
      request<ChecklistItem>(`/activities/${activityId}/checklist`, {
        method: 'POST',
        body: JSON.stringify({ title }),
      }),
    onSuccess: () => invalidate('activities'),
  })
  const toggleChecklistItem = useMutation({
    mutationFn: ({ activityId, itemId, completed }: { activityId: number; itemId: number; completed: boolean }) =>
      request<ChecklistItem>(`/activities/${activityId}/checklist/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify({ completed }),
      }),
    onSuccess: () => invalidate('activities'),
  })
  const deleteChecklistItem = useMutation({
    mutationFn: ({ activityId, itemId }: { activityId: number; itemId: number }) =>
      request<void>(`/activities/${activityId}/checklist/${itemId}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('activities'),
  })
  const startFocus = useMutation({
    mutationFn: (activityId: number) =>
      request<FocusSession>(`/activities/${activityId}/focus/start`, { method: 'POST' }),
    onSuccess: () => {
      invalidate('focus')
      invalidate('activities')
    },
  })
  const stopFocus = useMutation({
    mutationFn: (sessionId: number) => request<FocusSession>(`/focus/${sessionId}/stop`, { method: 'POST' }),
    onSuccess: () => {
      invalidate('focus')
      invalidate('activities')
    },
  })
  const updateDailyPlan = useMutation({
    mutationFn: (available_minutes: number) => request<DailyPlan>('/planning/today', {
      method: 'PUT',
      body: JSON.stringify({ available_minutes }),
    }),
    onSuccess: (plan) => queryClient.setQueryData(['daily-plan'], plan),
  })
  const motivateActivity = useMutation({
    mutationFn: (activity: Activity) => request<AIResponse>(`/ai/activities/${activity.id}/motivation`, {
      method: 'POST',
      body: JSON.stringify({ current_goal: activity.title, available_minutes: activity.estimated_minutes ?? 15 }),
    }),
    onSuccess: (response, activity) => {
      setAiResponses((previous) => ({ ...previous, [activity.id]: response }))
    },
  })
  const decomposeActivity = useMutation({
    mutationFn: (activity: Activity) => request<AIResponse>('/ai/decompose', {
      method: 'POST',
      body: JSON.stringify({ title: activity.title, description: `Категория: ${activity.category}. Приоритет: ${activity.priority}.` }),
    }),
    onSuccess: (response, activity) => {
      setAiResponses((previous) => ({ ...previous, [activity.id]: response }))
    },
  })
  const askTimeAdvice = useMutation({
    mutationFn: (availableMinutes: number) => request<AIResponse>('/ai/time-management', {
      method: 'POST',
      body: JSON.stringify({ available_minutes: availableMinutes }),
    }),
    onSuccess: setTimeAdvice,
  })
  const createTransaction = useMutation({
    mutationFn: (draft: TransactionDraft) => request<Transaction>('/transactions', {
      method: 'POST',
      body: JSON.stringify({ ...draft, amount: Number(draft.amount), note: draft.note || null }),
    }),
    onSuccess: () => invalidate('transactions'),
  })
  const deleteTransaction = useMutation({
    mutationFn: (id: number) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('transactions'),
  })
  const createReflection = useMutation({
    mutationFn: (draft: ReflectionDraft) => request<Reflection>('/reflections', { method: 'POST', body: JSON.stringify(draft) }),
    onSuccess: () => invalidate('reflections'),
  })
  const deleteReflection = useMutation({
    mutationFn: (id: number) => request<void>(`/reflections/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('reflections'),
  })
  const mutationError = [
    createActivity,
    updateActivity,
    deleteActivity,
    createTransaction,
    deleteTransaction,
    createReflection,
    deleteReflection,
    addChecklistItem,
    toggleChecklistItem,
    deleteChecklistItem,
    startFocus,
    stopFocus,
    updateDailyPlan,
    motivateActivity,
    decomposeActivity,
    askTimeAdvice,
  ].find((mutation) => mutation.isError)?.error

  const applyDecomposition = (activityId: number, text: string) => {
    const steps = text
      .split('\n')
      .map((line) => line.replace(/^\s*(?:\d+[.)]|[-•])\s*/, '').trim())
      .filter(Boolean)
      .slice(0, 4)
    steps.forEach((title) => addChecklistItem.mutate({ activityId, title }))
  }

  const saveProgress = (activity: Activity, progress: number) => {
    if (progress === 100 && activity.status !== 'COMPLETED') {
      if (!window.confirm(`Завершить задачу «${activity.title}»?`)) return false
      updateActivity.mutate({ id: activity.id, patch: { progress, status: 'COMPLETED' } })
      return true
    }
    updateActivity.mutate({ id: activity.id, patch: { progress } })
    return true
  }

  const net = transactions.reduce((sum, item) => sum + (item.kind === 'INCOME' ? 1 : -1) * Number(item.amount), 0)
  const activeCount = activities.filter((activity) => activity.status !== 'COMPLETED').length
  const isLoading = activitiesQuery.isLoading || transactionsQuery.isLoading || reflectionsQuery.isLoading || activeFocusQuery.isLoading || dailyPlanQuery.isLoading
  const error = activitiesQuery.error || transactionsQuery.error || reflectionsQuery.error || activeFocusQuery.error || dailyPlanQuery.error

  const navItems: { id: Page; label: string; icon: typeof ClipboardList; count: number }[] = [
    { id: 'activities', label: 'Активности', icon: ClipboardList, count: activeCount },
    { id: 'finance', label: 'Финансы', icon: Wallet, count: transactions.length },
    { id: 'reflections', label: 'Заметки', icon: Brain, count: reflections.length },
  ]
  const titles: Record<Page, { title: string; eyebrow: string }> = {
    activities: { title: 'Мой ритм', eyebrow: 'Планирование' },
    finance: { title: 'Деньги в порядке', eyebrow: 'Финансовый дневник' },
    reflections: { title: 'Личное пространство', eyebrow: 'Мысли и наблюдения' },
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <a className="brand" href="#home" onClick={(event) => event.preventDefault()}>
          <span className="brand-mark"><Check size={19} strokeWidth={3} /></span>
          <span>ритм<span className="brand-dot">.</span></span>
        </a>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav className="main-nav" aria-label="Основная навигация">
          {navItems.map(({ id, label, icon: Icon, count }) => (
            <button key={id} className={`nav-link ${page === id ? 'nav-link-active' : ''}`} onClick={() => { setPage(id); setMenuOpen(false) }}>
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
              <span className="nav-count">{count || ''}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="theme-label">ОФОРМЛЕНИЕ</div>
          <label className="theme-select-wrap">
            {theme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
            <span className="sr-only">Тема приложения</span>
            <select aria-label="Тема приложения" value={theme} onChange={(event) => setTheme(event.target.value as Theme)}>
              <option value="light">Светлая</option>
              <option value="dark">Тёмная</option>
              <option value="grove">Лесная</option>
            </select>
            <ChevronDown size={14} className="select-chevron" />
          </label>
          <div className="profile-row">
            <div className="avatar">Р</div>
            <div><strong>Мой профиль</strong><span>Личное пространство</span></div>
            <Sparkles size={16} className="profile-sparkle" />
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Открыть меню" onClick={() => setMenuOpen(!menuOpen)}>
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="breadcrumb"><span>Пространство</span><span className="breadcrumb-slash">/</span><strong>{navItems.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-date"><span className="online-dot" />Сегодня, {new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(new Date())}</div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">{titles[page].eyebrow}</div>
              <h1>{titles[page].title}</h1>
            </div>
            <div className="heading-date">{new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())}</div>
          </div>

          {isLoading && <div className="state-message">Загружаю ваше пространство…</div>}
          {error && <div className="error-banner" role="alert">Не удалось загрузить данные: {(error as Error).message}</div>}
          {mutationError && <div className="error-banner" role="alert">Не удалось сохранить изменение: {mutationError.message}</div>}
          {notice && <div className="notice-banner" role="status">{notice}<button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setNotice('')}><X size={16} /></button></div>}

          {!isLoading && !error && page === 'activities' && (
            <ActivitiesPage
              activities={activities}
              onCreate={(draft) => createActivity.mutate(draft)}
              onDelete={(activity) => {
                if (!window.confirm(`Удалить задачу «${activity.title}»? Финансовые записи сохранятся.`)) return
                deleteActivity.mutate(activity.id, { onSuccess: () => setNotice('Задача удалена. Связанные операции сохранены без привязки.') })
              }}
              onProgress={saveProgress}
              dailyPlan={dailyPlan}
              activeFocus={activeFocus}
              onSetCapacity={(minutes) => updateDailyPlan.mutate(minutes)}
              onAddChecklist={(activityId, title) => addChecklistItem.mutate({ activityId, title })}
              onToggleChecklist={(activityId, itemId, completed) => toggleChecklistItem.mutate({ activityId, itemId, completed })}
              onDeleteChecklist={(activityId, itemId) => deleteChecklistItem.mutate({ activityId, itemId })}
              onStartFocus={(activityId) => startFocus.mutate(activityId)}
              onStopFocus={() => activeFocus && stopFocus.mutate(activeFocus.id)}
              aiResponses={aiResponses}
              aiPending={motivateActivity.isPending || decomposeActivity.isPending}
              onMotivate={(activity) => motivateActivity.mutate(activity)}
              onDecompose={(activity) => decomposeActivity.mutate(activity)}
              onApplyDecomposition={applyDecomposition}
              timeAdvice={timeAdvice}
              isAskingTimeAdvice={askTimeAdvice.isPending}
              onAskTimeAdvice={() => askTimeAdvice.mutate(dailyPlan?.available_minutes ?? 360)}
              isSaving={createActivity.isPending || updateActivity.isPending}
            />
          )}
          {!isLoading && !error && page === 'finance' && (
            <FinancePage
              transactions={transactions}
              activities={activities}
              net={net}
              onCreate={(draft) => createTransaction.mutate(draft)}
              onDelete={(transaction) => {
                if (window.confirm(`Удалить запись «${transaction.category}»?`)) deleteTransaction.mutate(transaction.id)
              }}
              isSaving={createTransaction.isPending}
            />
          )}
          {!isLoading && !error && page === 'reflections' && (
            <ReflectionsPage
              reflections={reflections}
              onCreate={(draft) => createReflection.mutate(draft)}
              onDelete={(reflection) => {
                if (window.confirm(`Удалить заметку «${reflection.title}»?`)) deleteReflection.mutate(reflection.id)
              }}
              isSaving={createReflection.isPending}
            />
          )}

          <footer className="page-footer"><span>Ритм помогает держать важное рядом.</span><span>Данные синхронизируются с вашим пространством</span></footer>
        </div>
      </main>
    </div>
  )
}

function ActivitiesPage({
  activities,
  onCreate,
  onDelete,
  onProgress,
  dailyPlan,
  activeFocus,
  onSetCapacity,
  onAddChecklist,
  onToggleChecklist,
  onDeleteChecklist,
  onStartFocus,
  onStopFocus,
  aiResponses,
  aiPending,
  onMotivate,
  onDecompose,
  onApplyDecomposition,
  timeAdvice,
  isAskingTimeAdvice,
  onAskTimeAdvice,
  isSaving,
}: {
  activities: Activity[]
  onCreate: (draft: ActivityDraft) => void
  onDelete: (activity: Activity) => void
  onProgress: (activity: Activity, progress: number) => boolean
  dailyPlan: DailyPlan | undefined
  activeFocus: FocusSession | null
  onSetCapacity: (minutes: number) => void
  onAddChecklist: (activityId: number, title: string) => void
  onToggleChecklist: (activityId: number, itemId: number, completed: boolean) => void
  onDeleteChecklist: (activityId: number, itemId: number) => void
  onStartFocus: (activityId: number) => void
  onStopFocus: () => void
  aiResponses: Record<number, AIResponse>
  aiPending: boolean
  onMotivate: (activity: Activity) => void
  onDecompose: (activity: Activity) => void
  onApplyDecomposition: (activityId: number, text: string) => void
  timeAdvice: AIResponse | null
  isAskingTimeAdvice: boolean
  onAskTimeAdvice: () => void
  isSaving: boolean
}) {
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState<'ALL' | ActivityStatus>('ALL')
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('Личное')
  const [dueDate, setDueDate] = useState(() => new Date(Date.now() + 86_400_000).toISOString().slice(0, 16))
  const [recurrence, setRecurrence] = useState<Recurrence>('ONCE')
  const [priority, setPriority] = useState<ActivityPriority>('NORMAL')
  const [estimatedMinutes, setEstimatedMinutes] = useState('')
  const [energyLevel, setEnergyLevel] = useState<EnergyLevel>('MEDIUM')
  const [capacityDraft, setCapacityDraft] = useState(dailyPlan?.available_minutes ?? 360)
  const visible = activities.filter((activity) => filter === 'ALL' || activity.status === filter)

  useEffect(() => {
    if (dailyPlan) setCapacityDraft(dailyPlan.available_minutes)
  }, [dailyPlan?.available_minutes])

  function submit(event: FormEvent) {
    event.preventDefault()
    onCreate({
      title: title.trim(),
      category: category.trim(),
      due_date: new Date(dueDate).toISOString(),
      recurrence,
      priority,
      estimated_minutes: estimatedMinutes ? Number(estimatedMinutes) : null,
      energy_level: energyLevel,
    })
    setTitle('')
    setShowForm(false)
  }

  return (
    <>
      <div className="overview-strip">
        <div className="overview-copy"><span className="overview-icon"><CheckCircle2 size={20} /></span><div><strong>Шаг за шагом</strong><span>У каждого дела есть свой темп</span></div></div>
        <div className="overview-number"><strong>{activities.filter((activity) => activity.status === 'COMPLETED').length}</strong><span>выполнено всего</span></div>
        <button className="primary-button" onClick={() => setShowForm(!showForm)}>{showForm ? <X size={17} /> : <Plus size={17} />}<span>{showForm ? 'Закрыть' : 'Новая задача'}</span></button>
      </div>

      {showForm && <form className="entry-form activity-form" onSubmit={submit}>
        <div className="form-heading"><div><span className="eyebrow">НОВОЕ ДЕЛО</span><h2>Добавить активность</h2></div></div>
        <label>Название<input required maxLength={200} autoFocus placeholder="Например, подготовить презентацию" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <div className="form-grid">
          <label>Категория<input required maxLength={100} value={category} onChange={(event) => setCategory(event.target.value)} /></label>
          <label>Срок<input required type="datetime-local" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></label>
          <label>Повторение<select value={recurrence} onChange={(event) => setRecurrence(event.target.value as Recurrence)}><option value="ONCE">Один раз</option><option value="DAILY">Каждый день</option><option value="WEEKLY">Каждую неделю</option><option value="MONTHLY">Каждый месяц</option></select></label>
          <label>Приоритет<select value={priority} onChange={(event) => setPriority(event.target.value as ActivityPriority)}><option value="LOW">Низкий</option><option value="NORMAL">Обычный</option><option value="HIGH">Высокий</option><option value="URGENT">Срочный</option></select></label>
          <label>Оценка времени, мин<input type="number" min="1" max="1440" value={estimatedMinutes} onChange={(event) => setEstimatedMinutes(event.target.value)} placeholder="Например, 30" /></label>
          <label>Энергия<select value={energyLevel} onChange={(event) => setEnergyLevel(event.target.value as EnergyLevel)}><option value="LOW">Низкая</option><option value="MEDIUM">Средняя</option><option value="HIGH">Высокая</option></select></label>
        </div>
        <div className="form-actions"><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>Отмена</button><button className="primary-button" disabled={isSaving}>{isSaving ? 'Сохраняю…' : 'Создать задачу'}</button></div>
      </form>}

      {dailyPlan && <section className="planner-panel">
        <div className="planner-heading"><div><span className="eyebrow">ПЛАН НА СЕГОДНЯ</span><strong>{dailyPlan.planned_minutes} из {dailyPlan.available_minutes} мин</strong></div><label>Доступное время<input aria-label="Доступное время на сегодня" type="number" min="30" max="1440" step="30" value={capacityDraft} onChange={(event) => setCapacityDraft(Number(event.target.value))} /></label></div>
        <div className="planner-meter"><span style={{ width: `${Math.min(100, dailyPlan.planned_minutes / dailyPlan.available_minutes * 100)}%` }} /></div>
        <div className="planner-bottom"><div className="planner-selected"><strong>{dailyPlan.selected.length ? 'В фокусе' : 'План пока свободен'}</strong><span>{dailyPlan.selected.slice(0, 3).map((item) => item.title).join(' · ') || 'Задачи со сроком на ближайшие 7 дней появятся здесь'}</span></div><div className="planner-actions">{dailyPlan.deferred.length > 0 && <span>{dailyPlan.deferred.length} перенесено</span>}<button className="secondary-button" onClick={() => onSetCapacity(capacityDraft)}>Обновить план</button><button className="secondary-button ai-action-button" disabled={isAskingTimeAdvice} onClick={onAskTimeAdvice}><Sparkles size={14} />{isAskingTimeAdvice ? 'Думаю…' : 'Совет ИИ'}</button></div></div>
        {timeAdvice && <div className="ai-reply"><div className="ai-reply-heading"><Sparkles size={14} /><strong>Совет по плану</strong>{timeAdvice.fallback && <span>офлайн-подсказка</span>}</div><p>{timeAdvice.text}</p></div>}
      </section>}

      <div className="list-toolbar">
        <div><span className="eyebrow">ВАШ СПИСОК</span><h2>Активности <span className="muted-count">{visible.length}</span></h2></div>
        <div className="segmented" aria-label="Фильтр активностей">
          {[['ALL', 'Все'], ['PENDING', 'В планах'], ['IN_PROGRESS', 'В процессе'], ['COMPLETED', 'Готово']].map(([value, label]) => <button key={value} className={filter === value ? 'segment-active' : ''} onClick={() => setFilter(value as typeof filter)}>{label}</button>)}
        </div>
      </div>

      <div className="activity-list">
        {visible.map((activity) => <ActivityRow key={activity.id} activity={activity} onDelete={onDelete} onProgress={onProgress} activeFocus={activeFocus} onStartFocus={onStartFocus} onStopFocus={onStopFocus} onAddChecklist={onAddChecklist} onToggleChecklist={onToggleChecklist} onDeleteChecklist={onDeleteChecklist} aiResponse={aiResponses[activity.id]} aiPending={aiPending} onMotivate={onMotivate} onDecompose={onDecompose} onApplyDecomposition={onApplyDecomposition} />)}
        {visible.length === 0 && <EmptyState icon={<ClipboardList size={22} />} title="Здесь пока спокойно" text="Добавьте задачу, чтобы начать собирать свой день." />}
      </div>
    </>
  )
}

function ActivityRow({ activity, onDelete, onProgress, activeFocus, onStartFocus, onStopFocus, onAddChecklist, onToggleChecklist, onDeleteChecklist, aiResponse, aiPending, onMotivate, onDecompose, onApplyDecomposition }: {
  activity: Activity
  onDelete: (activity: Activity) => void
  onProgress: (activity: Activity, progress: number) => boolean
  activeFocus: FocusSession | null
  onStartFocus: (activityId: number) => void
  onStopFocus: () => void
  onAddChecklist: (activityId: number, title: string) => void
  onToggleChecklist: (activityId: number, itemId: number, completed: boolean) => void
  onDeleteChecklist: (activityId: number, itemId: number) => void
  aiResponse: AIResponse | undefined
  aiPending: boolean
  onMotivate: (activity: Activity) => void
  onDecompose: (activity: Activity) => void
  onApplyDecomposition: (activityId: number, text: string) => void
}) {
  const [progress, setProgress] = useState(activity.progress)
  const [expanded, setExpanded] = useState(false)
  const [checklistTitle, setChecklistTitle] = useState('')
  const [now, setNow] = useState(Date.now())
  useEffect(() => setProgress(activity.progress), [activity.progress])
  useEffect(() => {
    if (activeFocus?.activity_id !== activity.id) return
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [activeFocus?.activity_id, activity.id])
  const completed = activity.status === 'COMPLETED'
  const isFocused = activeFocus?.activity_id === activity.id
  const elapsed = isFocused ? Math.max(0, Math.floor((now - new Date(activeFocus.started_at).getTime()) / 1000)) : 0
  const commitProgress = (value: number) => {
    if (!onProgress(activity, value)) setProgress(activity.progress)
  }

  function submitChecklist(event: FormEvent) {
    event.preventDefault()
    if (!checklistTitle.trim()) return
    onAddChecklist(activity.id, checklistTitle.trim())
    setChecklistTitle('')
  }

  return (
    <article className={`activity-row ${completed ? 'activity-completed' : ''}`}>
      <div className="activity-state">{completed ? <CheckCircle2 size={21} /> : activity.status === 'IN_PROGRESS' ? <span className="state-progress"><Circle size={20} /><i /></span> : <Circle size={21} />}</div>
      <div className="activity-main">
        <div className="activity-title-line"><h3>{activity.title}</h3>{completed && <span className="done-label">Готово</span>}</div>
        <div className="activity-meta"><span>{activity.category}</span><span className="meta-separator">·</span><span>до {dateLabel(activity.due_date)}</span><span className={`priority-tag priority-${activity.priority.toLowerCase()}`}>{({ LOW: 'низкий', NORMAL: 'обычный', HIGH: 'высокий', URGENT: 'срочно' } as const)[activity.priority]}</span><span className="energy-tag" title={`Энергия: ${{ LOW: 'низкая', MEDIUM: 'средняя', HIGH: 'высокая' }[activity.energy_level]}`}><Zap size={11} />{{ LOW: 'низкая', MEDIUM: 'средняя', HIGH: 'высокая' }[activity.energy_level]}</span>{activity.estimated_minutes && <span className="effort-tag">~{activity.estimated_minutes} мин</span>}{activity.recurrence !== 'ONCE' && <><span className="meta-separator">·</span><span>{({ DAILY: 'ежедневно', WEEKLY: 'еженедельно', MONTHLY: 'ежемесячно' } as const)[activity.recurrence]}</span></>}</div>
        {activity.focus_seconds > 0 && <div className="focus-total"><Timer size={12} />В фокусе {Math.floor(activity.focus_seconds / 60)} мин</div>}
      </div>
      <button className={`icon-button checklist-toggle ${expanded ? 'tool-active' : ''}`} title="Открыть чек-лист" aria-label={`Чек-лист: ${activity.title}`} onClick={() => setExpanded(!expanded)}><ListChecks size={17} /><span>{activity.checklist_items.length || ''}</span></button>
      <button className="icon-button ai-row-action" title="Получить поддержку" aria-label={`Поддержка для задачи ${activity.title}`} disabled={aiPending} onClick={() => { setExpanded(true); onMotivate(activity) }}><Sparkles size={16} /></button>
      <button className="icon-button ai-row-action" title="Разбить задачу на шаги" aria-label={`Разбить задачу ${activity.title} на шаги`} disabled={aiPending} onClick={() => { setExpanded(true); onDecompose(activity) }}><WandSparkles size={16} /></button>
      {!completed && <button className={`icon-button focus-toggle ${isFocused ? 'focus-running' : ''}`} title={isFocused ? 'Остановить фокус-сессию' : activeFocus ? 'Сначала завершите текущую фокус-сессию' : 'Начать фокус-сессию'} aria-label={isFocused ? 'Остановить таймер' : 'Начать таймер'} disabled={Boolean(activeFocus && !isFocused)} onClick={isFocused ? onStopFocus : () => onStartFocus(activity.id)}>{isFocused ? <Square size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />}</button>}
      {isFocused && <span className="focus-clock">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</span>}
      <div className="progress-control">
        <label className="sr-only" htmlFor={`progress-${activity.id}`}>Прогресс: {progress}%</label>
        <input id={`progress-${activity.id}`} type="range" min="0" max="100" step="5" value={progress} disabled={completed} style={{ '--progress': `${progress}%` } as CSSProperties} onChange={(event) => setProgress(Number(event.target.value))} onPointerUp={(event) => commitProgress(Number(event.currentTarget.value))} onKeyUp={(event) => commitProgress(Number(event.currentTarget.value))} />
        <span>{progress}%</span>
      </div>
      <button className="icon-button row-delete" title="Удалить активность" aria-label={`Удалить ${activity.title}`} onClick={() => onDelete(activity)}><Trash2 size={16} /></button>
      {expanded && <div className="activity-details">
        {aiPending && <div className="ai-loading"><Sparkles size={14} />Готовлю короткий ответ…</div>}
        {aiResponse && <div className="ai-reply"><div className="ai-reply-heading"><Sparkles size={14} /><strong>{aiResponse.scenario === 'decomposition' ? 'Первые шаги' : 'Поддержка для старта'}</strong>{aiResponse.fallback && <span>офлайн-подсказка</span>}</div><p>{aiResponse.text}</p>{aiResponse.scenario === 'decomposition' && <button className="secondary-button" onClick={() => onApplyDecomposition(activity.id, aiResponse.text)}>Добавить шаги в чек-лист</button>}</div>}
        <div className="checklist-items">{activity.checklist_items.map((item) => <div className="checklist-item" key={item.id}><label><input type="checkbox" checked={item.completed} onChange={(event) => onToggleChecklist(activity.id, item.id, event.target.checked)} /><span className={item.completed ? 'checklist-done' : ''}>{item.title}</span></label><button className="icon-button" title="Удалить шаг" aria-label={`Удалить шаг ${item.title}`} onClick={() => onDeleteChecklist(activity.id, item.id)}><X size={13} /></button></div>)}</div>
        <form className="checklist-add" onSubmit={submitChecklist}><input aria-label="Новый шаг чек-листа" maxLength={200} placeholder="Добавить шаг" value={checklistTitle} onChange={(event) => setChecklistTitle(event.target.value)} /><button className="icon-button" title="Добавить шаг" aria-label="Добавить шаг"><Plus size={16} /></button></form>
      </div>}
    </article>
  )
}

function FinancePage({ transactions, activities, net, onCreate, onDelete, isSaving }: {
  transactions: Transaction[]
  activities: Activity[]
  net: number
  onCreate: (draft: TransactionDraft) => void
  onDelete: (transaction: Transaction) => void
  isSaving: boolean
}) {
  const [showForm, setShowForm] = useState(false)
  const [amount, setAmount] = useState('')
  const [kind, setKind] = useState<TransactionKind>('EXPENSE')
  const [category, setCategory] = useState('Дом')
  const [linkedActivity, setLinkedActivity] = useState('')
  const [note, setNote] = useState('')
  const expenses = transactions.filter((transaction) => transaction.kind === 'EXPENSE').reduce((sum, transaction) => sum + Number(transaction.amount), 0)
  const income = transactions.filter((transaction) => transaction.kind === 'INCOME').reduce((sum, transaction) => sum + Number(transaction.amount), 0)

  function submit(event: FormEvent) {
    event.preventDefault()
    onCreate({ amount, kind, category: category.trim(), linked_activity_id: linkedActivity ? Number(linkedActivity) : null, note: note.trim() })
    setAmount('')
    setNote('')
    setShowForm(false)
  }

  return (
    <>
      <div className="money-summary">
        <div className="money-total"><span>Баланс записей</span><strong>{currency.format(net)}</strong><small>По всем внесённым операциям</small></div>
        <div className="money-stat"><span className="money-stat-icon income-icon"><ArrowDownLeft size={17} /></span><div><small>Доходы</small><strong>{currency.format(income)}</strong></div></div>
        <div className="money-stat"><span className="money-stat-icon expense-icon"><ArrowUpRight size={17} /></span><div><small>Расходы</small><strong>{currency.format(expenses)}</strong></div></div>
        <button className="primary-button" onClick={() => setShowForm(!showForm)}>{showForm ? <X size={17} /> : <Plus size={17} />}<span>{showForm ? 'Закрыть' : 'Новая операция'}</span></button>
      </div>
      {showForm && <form className="entry-form" onSubmit={submit}>
        <div className="form-heading"><div><span className="eyebrow">ФИНАНСОВАЯ ЗАПИСЬ</span><h2>Добавить операцию</h2></div></div>
        <div className="kind-switch" role="group" aria-label="Тип операции"><button type="button" className={kind === 'EXPENSE' ? 'kind-active expense-active' : ''} onClick={() => setKind('EXPENSE')}><ArrowUpRight size={16} />Расход</button><button type="button" className={kind === 'INCOME' ? 'kind-active income-active' : ''} onClick={() => setKind('INCOME')}><ArrowDownLeft size={16} />Доход</button></div>
        <div className="form-grid">
          <label>Сумма, ₽<input required type="number" min="0.01" step="0.01" inputMode="decimal" placeholder="0" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
          <label>Категория<input required maxLength={100} value={category} onChange={(event) => setCategory(event.target.value)} /></label>
          <label>Связанная задача<select value={linkedActivity} onChange={(event) => setLinkedActivity(event.target.value)}><option value="">Без привязки</option>{activities.map((activity) => <option key={activity.id} value={activity.id}>{activity.title}</option>)}</select></label>
        </div>
        <label>Комментарий<input maxLength={2000} placeholder="Например, чек за материалы" value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="form-actions"><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>Отмена</button><button className="primary-button" disabled={isSaving}>{isSaving ? 'Сохраняю…' : 'Сохранить операцию'}</button></div>
      </form>}
      <div className="list-toolbar"><div><span className="eyebrow">ИСТОРИЯ</span><h2>Операции <span className="muted-count">{transactions.length}</span></h2></div></div>
      <div className="finance-list">
        {transactions.map((transaction) => {
          const linkedActivity = activities.find((activity) => activity.id === transaction.linked_activity_id)
          return <article className="transaction-row" key={transaction.id}>
            <span className={`transaction-icon ${transaction.kind === 'INCOME' ? 'income-icon' : 'expense-icon'}`}>{transaction.kind === 'INCOME' ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}</span>
            <div className="transaction-main"><h3>{transaction.category}</h3><span>{transaction.note || (linkedActivity ? `К задаче: ${linkedActivity.title}` : transaction.kind === 'INCOME' ? 'Поступление' : 'Расход')}</span></div>
            {transaction.linked_activity_id && !linkedActivity && <span className="unlinked-tag">задача удалена</span>}
            <time>{dateLabel(transaction.occurred_at)}</time>
            <strong className={`transaction-amount ${transaction.kind === 'INCOME' ? 'amount-income' : ''}`}>{transaction.kind === 'INCOME' ? '+' : '−'}{currency.format(Number(transaction.amount))}</strong>
            <button className="icon-button row-delete" title="Удалить операцию" aria-label={`Удалить операцию ${transaction.category}`} onClick={() => onDelete(transaction)}><Trash2 size={16} /></button>
          </article>
        })}
        {transactions.length === 0 && <EmptyState icon={<Coins size={22} />} title="Финансовая история начнётся здесь" text="Добавьте доход или расход и при желании свяжите его с задачей." />}
      </div>
    </>
  )
}

function ReflectionsPage({ reflections, onCreate, onDelete, isSaving }: {
  reflections: Reflection[]
  onCreate: (draft: ReflectionDraft) => void
  onDelete: (reflection: Reflection) => void
  isSaving: boolean
}) {
  const [showForm, setShowForm] = useState(false)
  const [section, setSection] = useState<ReflectionSection>('THOUGHT')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [filter, setFilter] = useState<ReflectionSection | 'ALL'>('ALL')
  const visible = reflections.filter((reflection) => filter === 'ALL' || reflection.section === filter)

  function submit(event: FormEvent) {
    event.preventDefault()
    onCreate({ section, title: title.trim(), content: content.trim() })
    setTitle('')
    setContent('')
    setShowForm(false)
  }

  return (
    <>
      <div className="reflection-intro"><span className="reflection-mark"><Brain size={22} /></span><div><strong>Место для ясности</strong><p>Записывайте наблюдения, чтобы лучше понимать себя и свои разговоры.</p></div><button className="primary-button" onClick={() => setShowForm(!showForm)}>{showForm ? <X size={17} /> : <Plus size={17} />}<span>{showForm ? 'Закрыть' : 'Новая заметка'}</span></button></div>
      {showForm && <form className="entry-form" onSubmit={submit}>
        <div className="form-heading"><div><span className="eyebrow">ЛИЧНАЯ ЗАПИСЬ</span><h2>Что хочется сохранить?</h2></div></div>
        <div className="section-picker" role="group" aria-label="Раздел заметки">{(['THOUGHT', 'PSYCHOLOGY', 'CONFLICT'] as const).map((value) => <button type="button" key={value} className={section === value ? 'section-active' : ''} onClick={() => setSection(value)}>{sectionName(value)}</button>)}</div>
        <label>Заголовок<input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Короткая мысль" /></label>
        <label>Заметка<textarea required maxLength={10000} rows={5} value={content} onChange={(event) => setContent(event.target.value)} placeholder="Опишите ситуацию, свои ощущения или выводы…" /></label>
        <div className="form-actions"><button className="secondary-button" type="button" onClick={() => setShowForm(false)}>Отмена</button><button className="primary-button" disabled={isSaving}>{isSaving ? 'Сохраняю…' : 'Сохранить заметку'}</button></div>
      </form>}
      <div className="list-toolbar"><div><span className="eyebrow">ВАШИ ЗАПИСИ</span><h2>Заметки <span className="muted-count">{visible.length}</span></h2></div><div className="segmented reflection-filters"><button className={filter === 'ALL' ? 'segment-active' : ''} onClick={() => setFilter('ALL')}>Все</button>{(['THOUGHT', 'PSYCHOLOGY', 'CONFLICT'] as const).map((value) => <button key={value} className={filter === value ? 'segment-active' : ''} onClick={() => setFilter(value)}>{sectionName(value)}</button>)}</div></div>
      <div className="reflection-list">
        {visible.map((reflection) => <article className="reflection-card" key={reflection.id}>
          <div className="reflection-card-top"><span className={`section-tag section-${reflection.section.toLowerCase()}`}>{sectionName(reflection.section)}</span><time>{dateLabel(reflection.created_at)}</time></div>
          <h3>{reflection.title}</h3><p>{reflection.content}</p>
          <button className="icon-button row-delete" title="Удалить заметку" aria-label={`Удалить заметку ${reflection.title}`} onClick={() => onDelete(reflection)}><Trash2 size={16} /></button>
        </article>)}
        {visible.length === 0 && <EmptyState icon={<Brain size={22} />} title="Свободное место для ваших мыслей" text="Сохраните заметку о конфликте, эмоции или любом важном наблюдении." />}
      </div>
    </>
  )
}

function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <div className="empty-state"><span>{icon}</span><strong>{title}</strong><p>{text}</p></div>
}

export default App
