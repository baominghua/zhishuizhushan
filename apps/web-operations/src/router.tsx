import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";
import { lazy } from "react";

import { AppShell } from "./components/AppShell";
import { WorkspacePage } from "./pages/WorkspacePage";

const MapPage = lazy(async () => ({
  default: (await import("./pages/MapPage")).MapPage,
}));
const ImportsPage = lazy(async () => ({
  default: (await import("./pages/ImportsPage")).ImportsPage,
}));
const ForestBlocksPage = lazy(async () => ({
  default: (await import("./pages/ForestBlocksPage")).ForestBlocksPage,
}));
const ForestSubcompartmentsPage = lazy(async () => ({
  default: (await import("./pages/ForestSubcompartmentsPage")).ForestSubcompartmentsPage,
}));
const ForestRightsPage = lazy(async () => ({
  default: (await import("./pages/ForestRightsPage")).ForestRightsPage,
}));
const ResourceSurveysPage = lazy(async () => ({
  default: (await import("./pages/ResourceSurveysPage")).ResourceSurveysPage,
}));
const AttachmentsPage = lazy(async () => ({ default: (await import("./pages/AttachmentsPage")).AttachmentsPage }));
const PatrolPage = lazy(async () => ({
  default: (await import("./pages/PatrolPage")).PatrolPage,
}));
const HarvestPage = lazy(async () => ({
  default: (await import("./pages/HarvestPage")).HarvestPage,
}));
const LaborPage = lazy(async () => ({
  default: (await import("./pages/LaborPage")).LaborPage,
}));
const SafetyEventsPage = lazy(async () => ({
  default: (await import("./pages/SafetyEventsPage")).SafetyEventsPage,
}));
const MobileOperationsPage = lazy(async () => ({ default: (await import("./pages/MobileOperationsPage")).MobileOperationsPage }));
const MobileFieldPage = lazy(async () => ({ default: (await import("./pages/MobileFieldPage")).MobileFieldPage }));
const EquipmentPage = lazy(async () => ({ default: (await import("./pages/EquipmentPage")).EquipmentPage }));
const DroneMissionsPage = lazy(async () => ({ default: (await import("./pages/DroneMissionsPage")).DroneMissionsPage }));
const ImageryAssetsPage = lazy(async () => ({ default: (await import("./pages/ImageryAssetsPage")).ImageryAssetsPage }));
const AiReviewPage = lazy(async () => ({ default: (await import("./pages/AiReviewPage")).AiReviewPage }));
const AiModelsPage = lazy(async () => ({ default: (await import("./pages/AiModelsPage")).AiModelsPage }));
const AiInferencePage = lazy(async () => ({ default: (await import("./pages/AiInferencePage")).AiInferencePage }));
const OperationsCenterPage = lazy(async () => ({ default: (await import("./pages/OperationsCenterPage")).OperationsCenterPage }));
const BasemapSettingsPage = lazy(async () => ({ default: (await import("./pages/BasemapSettingsPage")).BasemapSettingsPage }));
const CarbonEstimatesPage = lazy(async () => ({ default: (await import("./pages/CarbonEstimatesPage")).CarbonEstimatesPage }));
const LeadershipCockpitPage = lazy(async () => ({ default: (await import("./pages/LeadershipCockpitPage")).LeadershipCockpitPage }));
const DisplayDashboardPage = lazy(async () => ({ default: (await import("./pages/DisplayDashboardPage")).DisplayDashboardPage }));

const rootRoute = createRootRoute({ component: AppShell });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/workspace" }); } });
const workspaceRoute = createRoute({ getParentRoute: () => rootRoute, path: "/workspace", component: WorkspacePage });
const mapRoute = createRoute({ getParentRoute: () => rootRoute, path: "/map", component: MapPage });
const forestBlocksRoute = createRoute({ getParentRoute: () => rootRoute, path: "/resources/forest-blocks", component: ForestBlocksPage });
const forestSubcompartmentsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/resources/forest-subcompartments", component: ForestSubcompartmentsPage });
const forestRightsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/resources/forest-rights", component: ForestRightsPage });
const resourceSurveysRoute = createRoute({ getParentRoute: () => rootRoute, path: "/resources/resource-surveys", component: ResourceSurveysPage });
const attachmentsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/attachments", component: AttachmentsPage });
const importsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/resources/imports", component: ImportsPage });
const patrolRoute = createRoute({ getParentRoute: () => rootRoute, path: "/operations/patrol", component: PatrolPage });
const harvestRoute = createRoute({ getParentRoute: () => rootRoute, path: "/operations/harvest", component: HarvestPage });
const laborRoute = createRoute({ getParentRoute: () => rootRoute, path: "/operations/labor", component: LaborPage });
const equipmentRoute = createRoute({ getParentRoute: () => rootRoute, path: "/iot/devices", component: EquipmentPage });
const droneMissionsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/drone/missions", component: DroneMissionsPage });
const imageryAssetsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/drone/imagery-assets", component: ImageryAssetsPage });
const aiReviewRoute = createRoute({ getParentRoute: () => rootRoute, path: "/ai/reviews", component: AiReviewPage });
const aiModelsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/ai/models", component: AiModelsPage });
const aiInferenceRoute = createRoute({ getParentRoute: () => rootRoute, path: "/ai/inference-runs", component: AiInferencePage });
const safetyEventsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/safety/events", component: SafetyEventsPage });
const mobileOperationsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/operations/mobile-sync", component: MobileOperationsPage });
const mobileFieldRoute = createRoute({ getParentRoute: () => rootRoute, path: "/field/mobile", component: MobileFieldPage });
const todosRoute = createRoute({ getParentRoute: () => rootRoute, path: "/operations/todos", component: () => <OperationsCenterPage mode="todos" /> });
const notificationsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/notifications", component: () => <OperationsCenterPage mode="notifications" /> });
const auditRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/audit", component: () => <OperationsCenterPage mode="audit" /> });
const basemapSettingsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/system/basemap-settings", component: BasemapSettingsPage });
const carbonEstimatesRoute = createRoute({ getParentRoute: () => rootRoute, path: "/carbon/estimates", component: CarbonEstimatesPage });
const leadershipCockpitRoute = createRoute({ getParentRoute: () => rootRoute, path: "/cockpit/leadership", component: LeadershipCockpitPage });
const displayDashboardRoute = createRoute({ getParentRoute: () => rootRoute, path: "/display", component: DisplayDashboardPage });

const routeTree = rootRoute.addChildren([indexRoute, workspaceRoute, leadershipCockpitRoute, displayDashboardRoute, todosRoute, notificationsRoute, auditRoute, basemapSettingsRoute, mapRoute, forestBlocksRoute, forestSubcompartmentsRoute, resourceSurveysRoute, attachmentsRoute, forestRightsRoute, importsRoute, patrolRoute, harvestRoute, laborRoute, equipmentRoute, droneMissionsRoute, imageryAssetsRoute, aiModelsRoute, aiInferenceRoute, aiReviewRoute, safetyEventsRoute, mobileOperationsRoute, mobileFieldRoute, carbonEstimatesRoute]);

export const router = createRouter({ routeTree, basepath: "/v2", defaultPreload: "intent" });

declare module "@tanstack/react-router" {
  interface Register { router: typeof router }
}
