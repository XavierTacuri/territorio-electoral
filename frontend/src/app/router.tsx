import { Suspense } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { ProtectedRoute } from '../auth/ProtectedRoute';
import { RoleGuard } from '../auth/RoleGuard';
import { canManageUsers, canViewDataHub } from '../auth/permissions';
import { LoadingSkeleton } from '../components/feedback/States';
import { AppShell } from '../layouts/AppShell';
import { ErrorPage } from '../pages/ErrorPages';
import { lazyWithReload as lazy } from './lazyWithReload';
const Login = lazy(() => import('../pages/LoginPage'));
const Dashboard = lazy(() => import('../pages/DashboardPage'));
const Campaigns = lazy(() => import('../features/campaigns/CampaignsPage'));
const CampaignForm = lazy(() => import('../features/campaigns/CampaignFormPage'));
const CampaignDetail = lazy(() => import('../features/campaigns/CampaignDetailPage'));
const Module = lazy(() => import('../pages/ModulePage'));
const Map = lazy(() => import('../pages/MapPage'));
const Activities = lazy(() => import('../features/operations/ActivitiesPage'));
const ActivityDetail = lazy(() => import('../features/operations/ActivityDetailPage'));
const Needs = lazy(() => import('../features/operations/NeedsPage'));
const Operations = lazy(() => import('../features/operations/OperationsPage'));
const Approvals = lazy(() => import('../features/operations/ApprovalsPage'));
const Agenda = lazy(() => import('../features/operations/AgendaPage'));
const Calendar = lazy(() => import('../features/calendar/CalendarPage'));
const NeedDetail = lazy(() => import('../features/operations/NeedDetailPage'));
const PublicIntelligence = lazy(
  () => import('../features/public-intelligence/PublicIntelligencePage'),
);
const PublicItemDetail = lazy(() => import('../features/public-intelligence/PublicItemDetailPage'));
const Surveys = lazy(() => import('../features/surveys/SurveysPage'));
const Questionnaires = lazy(() => import('../features/surveys/QuestionnairesPage'));
const StudyDetail = lazy(() => import('../features/survey-studies/StudyDetailPage'));
const StudyCompare = lazy(() => import('../features/survey-studies/StudyComparePage'));
const StudyImport = lazy(() => import('../features/survey-studies/StudyImportPage'));
const SurveyBuilder = lazy(() => import('../features/surveys/SurveyBuilderPage'));
const SurveyCapture = lazy(() => import('../features/surveys/SurveyCapturePage'));
const SurveyResults = lazy(() => import('../features/surveys/SurveyResultsPage'));
const Imports = lazy(() => import('../features/imports/ImportPage'));
const CneImportWizard = lazy(() => import('../features/official-data/CneImportWizard'));
const InecImport = lazy(() => import('../features/official-data/InecImportPage'));
const RollSnapshotImport = lazy(() => import('../features/official-data/RollSnapshotImportPage'));
const GeographyImport = lazy(() => import('../features/official-data/GeographyImportPage'));
const PollingPlaceImport = lazy(() => import('../features/official-data/PollingPlaceImportPage'));
const ElectoralBoardImport = lazy(
  () => import('../features/official-data/ElectoralBoardImportPage'),
);
const CurrentElection = lazy(() => import('../features/historical/CurrentElectionPage'));
const TerritorialIntelligence = lazy(
  () => import('../features/territory/TerritorialIntelligencePage'),
);
const TerritorialProfile = lazy(() => import('../features/territory/TerritorialProfilePage'));
const Reports = lazy(() => import('../features/reports/ReportCenterPage'));
const ReportRunDetail = lazy(() => import('../features/reports/ReportRunDetailPage'));
const DebateAssistant = lazy(() => import('../features/debate/DebateAssistantPage'));
const ElectionDay = lazy(() => import('../features/election-day/ElectionDayPage'));
const ElectionDayPollingPlace = lazy(
  () => import('../features/election-day/PollingPlaceDetailPage'),
);
const MyElectionDay = lazy(() => import('../features/election-day/MyElectionDayPage'));
const Alerts = lazy(() => import('../features/alerts/AlertsPage'));
const Electoral = lazy(() => import('../features/historical/ElectoralPage'));
const Demographics = lazy(() => import('../features/historical/DemographicsPage'));
const AdminUsers = lazy(() => import('../features/admin/UsersPage'));
const AdminRoles = lazy(() => import('../features/admin/RolesPage'));
const AdminSources = lazy(() => import('../features/admin/SourcesPage'));
const DataHub = lazy(() => import('../features/data-hub/DataHubPage'));
const AdminElectoralMilestones = lazy(() => import('../features/admin/ElectoralMilestonesPage'));
const DatasetDetail = lazy(() => import('../features/data-hub/DatasetDetailPage'));
const AdminTemplates = lazy(() => import('../features/admin/TemplatesPage'));
const AdminAudit = lazy(() => import('../features/admin/AuditPage'));
const Account = lazy(() => import('../features/account/AccountPage'));
const AiConfiguration = lazy(() => import('../features/admin/AiConfigurationPage'));
const AdminAssignments = lazy(() => import('../features/admin/AssignmentsPage'));
const TerritoryAi = lazy(() => import('../features/territory-ai/TerritoryAiPage'));
const FieldLayoutComponent = lazy(() =>
  import('../features/field/FieldLayout').then((m) => ({ default: m.FieldLayout })),
);
const FieldHome = lazy(() => import('../features/field/FieldHomePage'));
const FieldAgenda = lazy(() => import('../features/field/FieldAgendaPage'));
const FieldDrafts = lazy(() => import('../features/field/FieldDraftsPage'));
const FieldActivityForm = lazy(() => import('../features/field/FieldActivityFormPage'));
const FieldNeedForm = lazy(() => import('../features/field/FieldNeedFormPage'));
const FieldActivityDetail = lazy(() => import('../features/field/FieldActivityDetailPage'));
const ElectoralPanorama = lazy(() => import('../features/panorama/ElectoralPanoramaPage'));
const FeatureEntitlements = lazy(() => import('../features/admin/FeatureEntitlementsPage'));
const Organizations = lazy(() => import('../features/admin/OrganizationsPage'));
const OrganizationCreate = lazy(() => import('../features/organizations/OrganizationCreatePage'));
const OrganizationOnboarding = lazy(
  () => import('../features/organizations/OrganizationOnboardingPage'),
);
const OrganizationDetail = lazy(() => import('../features/organizations/OrganizationDetailPage'));
const lazyElement = (node: React.ReactNode) => (
  <Suspense fallback={<LoadingSkeleton />}>{node}</Suspense>
);
const campaign = '/app/campaigns/:campaignId';
const moduleRoute = (
  path: string,
  title: string,
  description: string,
  endpoint: (id: string) => string,
  createLabel?: string,
) => ({
  path,
  element: lazyElement(
    <Module
      title={title}
      description={description}
      endpoint={endpoint}
      createLabel={createLabel}
    />,
  ),
});
export const router = createBrowserRouter([
  { path: '/login', element: lazyElement(<Login />) },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: '/app',
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/app/campaigns" replace /> },
          { path: 'account', element: lazyElement(<Account />) },
          { path: 'campaigns', element: lazyElement(<Campaigns />) },
          { path: 'campaigns/new', element: lazyElement(<CampaignForm />) },
          { path: 'campaigns/:campaignId', element: lazyElement(<CampaignDetail />) },
          { path: 'campaigns/:campaignId/edit', element: lazyElement(<CampaignForm />) },
          { path: campaign.slice(5) + '/dashboard', element: lazyElement(<Dashboard />) },
          { path: campaign.slice(5) + '/panorama', element: lazyElement(<ElectoralPanorama />) },
          {
            path: campaign.slice(5) + '/current-election',
            element: lazyElement(<CurrentElection />),
          },
          {
            path: campaign.slice(5) + '/territories',
            element: lazyElement(<TerritorialIntelligence />),
          },
          {
            path: campaign.slice(5) + '/territories/:parishId',
            element: lazyElement(<TerritorialProfile />),
          },
          { path: campaign.slice(5) + '/activities', element: lazyElement(<Activities />) },
          {
            path: campaign.slice(5) + '/activities/:activityId',
            element: lazyElement(<ActivityDetail />),
          },
          { path: campaign.slice(5) + '/needs', element: lazyElement(<Needs />) },
          { path: campaign.slice(5) + '/needs/:needId', element: lazyElement(<NeedDetail />) },
          // Seguimientos/Commitments es dominio legacy retirado de la
          // experiencia productiva (retiro de producto): ya no se registra
          // como ruta navegable. La URL directa /commitments cae al catch-all
          // '*' de más abajo y muestra el 404 coherente de la app.
          { path: campaign.slice(5) + '/operations', element: lazyElement(<Operations />) },
          { path: campaign.slice(5) + '/approvals', element: lazyElement(<Approvals />) },
          { path: campaign.slice(5) + '/operations/agenda', element: lazyElement(<Agenda />) },
          { path: campaign.slice(5) + '/calendar', element: lazyElement(<Calendar />) },
          { path: campaign.slice(5) + '/operations/map', element: lazyElement(<Map />) },
          {
            path: campaign.slice(5) + '/public-intelligence',
            element: lazyElement(<PublicIntelligence />),
          },
          {
            path: campaign.slice(5) + '/public-intelligence/:itemId',
            element: lazyElement(<PublicItemDetail />),
          },
          { path: campaign.slice(5) + '/surveys', element: lazyElement(<Surveys />) },
          {
            path: campaign.slice(5) + '/questionnaires',
            element: lazyElement(<Questionnaires />),
          },
          {
            path: campaign.slice(5) + '/survey-studies/compare',
            element: lazyElement(<StudyCompare />),
          },
          {
            path: campaign.slice(5) + '/survey-studies/import',
            element: lazyElement(<StudyImport />),
          },
          {
            path: campaign.slice(5) + '/survey-studies/:studyId',
            element: lazyElement(<StudyDetail />),
          },
          {
            path: campaign.slice(5) + '/surveys/:surveyId',
            element: lazyElement(<SurveyBuilder />),
          },
          {
            path: campaign.slice(5) + '/surveys/:surveyId/build',
            element: lazyElement(<SurveyBuilder />),
          },
          {
            path: campaign.slice(5) + '/surveys/:surveyId/collect',
            element: lazyElement(<SurveyCapture />),
          },
          {
            path: campaign.slice(5) + '/surveys/:surveyId/results',
            element: lazyElement(<SurveyResults />),
          },
          { path: campaign.slice(5) + '/electoral', element: lazyElement(<Electoral />) },
          { path: campaign.slice(5) + '/demographics', element: lazyElement(<Demographics />) },
          { path: campaign.slice(5) + '/maps', element: lazyElement(<Map />) },
          { path: campaign.slice(5) + '/reports', element: lazyElement(<Reports />) },
          {
            path: campaign.slice(5) + '/reports/:runId',
            element: lazyElement(<ReportRunDetail />),
          },
          { path: campaign.slice(5) + '/debate', element: lazyElement(<DebateAssistant />) },
          { path: campaign.slice(5) + '/election-day', element: lazyElement(<ElectionDay />) },
          {
            path: campaign.slice(5) + '/election-day/polling-places/:polling_place_id',
            element: lazyElement(<ElectionDayPollingPlace />),
          },
          { path: campaign.slice(5) + '/election-day/my', element: lazyElement(<MyElectionDay />) },
          { path: campaign.slice(5) + '/alerts', element: lazyElement(<Alerts />) },
          { path: campaign.slice(5) + '/territory-ai', element: lazyElement(<TerritoryAi />) },
          {
            path: campaign.slice(5) + '/field',
            element: lazyElement(<FieldLayoutComponent />),
            children: [
              { index: true, element: lazyElement(<FieldHome />) },
              { path: 'agenda', element: lazyElement(<FieldAgenda />) },
              { path: 'drafts', element: lazyElement(<FieldDrafts />) },
              { path: 'activities/new', element: lazyElement(<FieldActivityForm />) },
              { path: 'needs/new', element: lazyElement(<FieldNeedForm />) },
              { path: 'activities/:activityId', element: lazyElement(<FieldActivityDetail />) },
            ],
          },
          moduleRoute(
            campaign.slice(5) + '/alerts/:alertId',
            'Detalle de alerta',
            'Evidencia e historial de acciones.',
            (id) => '/campaigns/' + id + '/alerts?page=1&page_size=20',
          ),
          {
            path: 'organization',
            element: lazyElement(<OrganizationDetail />),
          },
          {
            path: 'admin/organizations',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<Organizations />)}</RoleGuard>,
          },
          {
            path: 'admin/organizations/new',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<OrganizationCreate />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/organizations/onboarding',
            element: (
              <RoleGuard check={canManageUsers}>
                {lazyElement(<OrganizationOnboarding />)}
              </RoleGuard>
            ),
          },
          {
            path: 'admin/organizations/:organizationId',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<OrganizationDetail />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/users',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<AdminUsers />)}</RoleGuard>,
          },
          {
            path: 'admin/roles',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<AdminRoles />)}</RoleGuard>,
          },
          {
            path: 'admin/assignments',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<AdminAssignments />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/data-sources',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<AdminSources />)}</RoleGuard>,
          },
          {
            path: 'admin/data-hub',
            element: <RoleGuard check={canViewDataHub}>{lazyElement(<DataHub />)}</RoleGuard>,
          },
          {
            path: 'admin/data-hub/:datasetType',
            element: <RoleGuard check={canViewDataHub}>{lazyElement(<DatasetDetail />)}</RoleGuard>,
          },
          {
            path: 'admin/electoral-milestones',
            element: (
              <RoleGuard check={canManageUsers}>
                {lazyElement(<AdminElectoralMilestones />)}
              </RoleGuard>
            ),
          },
          {
            path: 'admin/data-imports',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<Imports />)}</RoleGuard>,
          },
          {
            path: 'admin/official-data/cne',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<CneImportWizard />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/official-data/inec',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<InecImport />)}</RoleGuard>,
          },
          {
            path: 'admin/official-data/cne/roll',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<RollSnapshotImport />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/official-data/geography',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<GeographyImport />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/official-data/election-day/polling-places',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<PollingPlaceImport />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/official-data/election-day/boards',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<ElectoralBoardImport />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/geometry-imports',
            element: <Navigate to="/app/admin/official-data/geography" replace />,
          },
          {
            path: 'admin/report-templates',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<AdminTemplates />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/security-audit',
            element: <RoleGuard check={canManageUsers}>{lazyElement(<AdminAudit />)}</RoleGuard>,
          },
          {
            path: 'admin/ai-configuration',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<AiConfiguration />)}</RoleGuard>
            ),
          },
          {
            path: 'admin/feature-entitlements',
            element: (
              <RoleGuard check={canManageUsers}>{lazyElement(<FeatureEntitlements />)}</RoleGuard>
            ),
          },
        ],
      },
    ],
  },
  {
    path: '/403',
    element: <ErrorPage code="403" message="No tienes permisos para acceder a esta página." />,
  },
  { path: '/error', element: <ErrorPage /> },
  { path: '*', element: <ErrorPage code="404" message="La página solicitada no existe." /> },
]);
