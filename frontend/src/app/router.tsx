import { lazy, Suspense } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { ProtectedRoute } from '../auth/ProtectedRoute';
import { RoleGuard } from '../auth/RoleGuard';
import { canManageUsers } from '../auth/permissions';
import { LoadingSkeleton } from '../components/feedback/States';
import { AppShell } from '../layouts/AppShell';
import { ErrorPage } from '../pages/ErrorPages';
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
const Commitments = lazy(() => import('../features/operations/CommitmentsPage'));
const Operations = lazy(() => import('../features/operations/OperationsPage'));
const Approvals = lazy(() => import('../features/operations/ApprovalsPage'));
const Agenda = lazy(() => import('../features/operations/AgendaPage'));
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
const CurrentElection = lazy(() => import('../features/historical/CurrentElectionPage'));
const TerritorialIntelligence = lazy(
  () => import('../features/territory/TerritorialIntelligencePage'),
);
const Reports = lazy(() => import('../features/reports/ReportsPage'));
const Alerts = lazy(() => import('../features/alerts/AlertsPage'));
const Electoral = lazy(() => import('../features/historical/ElectoralPage'));
const Demographics = lazy(() => import('../features/historical/DemographicsPage'));
const AdminUsers = lazy(() => import('../features/admin/UsersPage'));
const AdminRoles = lazy(() => import('../features/admin/RolesPage'));
const AdminSources = lazy(() => import('../features/admin/SourcesPage'));
const AdminTemplates = lazy(() => import('../features/admin/TemplatesPage'));
const AdminAudit = lazy(() => import('../features/admin/AuditPage'));
const AdminAssignments = lazy(() => import('../features/admin/AssignmentsPage'));
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
          { path: 'campaigns', element: lazyElement(<Campaigns />) },
          { path: 'campaigns/new', element: lazyElement(<CampaignForm />) },
          { path: 'campaigns/:campaignId', element: lazyElement(<CampaignDetail />) },
          { path: 'campaigns/:campaignId/edit', element: lazyElement(<CampaignForm />) },
          { path: campaign.slice(5) + '/dashboard', element: lazyElement(<Dashboard />) },
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
            element: lazyElement(<TerritorialIntelligence />),
          },
          { path: campaign.slice(5) + '/activities', element: lazyElement(<Activities />) },
          {
            path: campaign.slice(5) + '/activities/:activityId',
            element: lazyElement(<ActivityDetail />),
          },
          { path: campaign.slice(5) + '/needs', element: lazyElement(<Needs />) },
          { path: campaign.slice(5) + '/needs/:needId', element: lazyElement(<NeedDetail />) },
          { path: campaign.slice(5) + '/commitments', element: lazyElement(<Commitments />) },
          { path: campaign.slice(5) + '/operations', element: lazyElement(<Operations />) },
          { path: campaign.slice(5) + '/approvals', element: lazyElement(<Approvals />) },
          { path: campaign.slice(5) + '/operations/agenda', element: lazyElement(<Agenda />) },
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
          { path: campaign.slice(5) + '/alerts', element: lazyElement(<Alerts />) },
          moduleRoute(
            campaign.slice(5) + '/alerts/:alertId',
            'Detalle de alerta',
            'Evidencia e historial de acciones.',
            (id) => '/campaigns/' + id + '/alerts?page=1&page_size=20',
          ),
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
