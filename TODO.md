# Frontend ↔ Backend Integration Checklist

## Phase A — RecordsPage
- [x] A1: Fix RecordsPage.jsx search debounce bug (stale closure / unhandled cleanup)
- [x] A2: Verify backend + frontend build

## Phase B — Live Data Pages
- [x] B1: Wire DashboardPage.jsx — use `adminAnalyticsService`
- [x] B2: Wire AnalyticsPage.jsx — use `adminAnalyticsService`
- [x] B3: Wire HomePage.jsx — use `adminAnalyticsService`
- [x] B4: Wire StaffRecordsPage.jsx — use `staffService`
- [x] B5: Verify backend + frontend build

## Phase C — Auth / Admin
- [ ] C1: Fix RegisterPage.jsx — use `authService.register`
- [ ] C2: Backend — add `update_user`/`delete_user` in `services/admin.py`
- [ ] C3: Backend — add `PUT/DELETE /admin/users/{id}` in `api/routes/admin.py`
- [ ] C4: Enable UserManagementPage.jsx edit/delete
- [ ] C5: Verify backend + frontend build

## Phase D — Profile & Settings
- [ ] D1: Backend — add `UserSettings` model in `db/models.py`
- [ ] D2: Backend — new `api/routes/settings.py` (`/settings` + `/profile` GET/PUT)
- [ ] D3: Backend — add `POST /auth/change-password` in `api/routes/auth.py`
- [ ] D4: Backend — register settings router in `api/main.py`
- [ ] D5: Wire ProfilePage.jsx — use `profileService` + change-password
- [ ] D6: Wire SettingsPage.jsx — use `settingsService`
- [ ] D7: Verify backend + frontend build

## Phase E — Verify
- [ ] E1: Backend import/startup check
- [ ] E2: Frontend `npm run build`
- [ ] E3: Summary of all changes

