import { useEffect, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  AppstoreOutlined,
  BellOutlined,
  CloseOutlined,
  DatabaseOutlined,
  DollarOutlined,
  ExperimentOutlined,
  LineChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  restrictToHorizontalAxis,
  restrictToParentElement,
} from "@dnd-kit/modifiers";
import {
  SortableContext,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  WORKSPACE_ROUTES,
  findRouteByPath,
  useWorkspaceStore,
  type WorkspaceRouteKey,
  type WorkspaceTab,
} from "@/store/useWorkspaceStore";

const ICONS: Record<WorkspaceRouteKey, ReactNode> = {
  dashboard: <AppstoreOutlined />,
  chart: <LineChartOutlined />,
  strategy: <ThunderboltOutlined />,
  backtest: <ExperimentOutlined />,
  trade: <DollarOutlined />,
  data: <DatabaseOutlined />,
  ai: <RobotOutlined />,
  notify: <BellOutlined />,
};

interface TabItemProps {
  tab: WorkspaceTab;
  isActive: boolean;
  onActivate: (key: WorkspaceRouteKey) => void;
  onClose: (key: WorkspaceRouteKey, e: MouseEvent) => void;
}

function SortableTabItem({ tab, isActive, onActivate, onClose }: TabItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: tab.key });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 20 : undefined,
  };

  const baseCls =
    "relative flex items-center gap-2 h-9 px-3 text-sm cursor-pointer select-none rounded-t-md transition-colors";
  const activeCls =
    "bg-white text-blue-600 font-medium border border-slate-200 border-b-white -mb-px shadow-[0_-1px_0_0_rgba(15,23,42,0.04)]";
  const inactiveCls =
    "bg-transparent text-slate-500 hover:bg-white/70 hover:text-slate-800";

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => onActivate(tab.key)}
      className={`${baseCls} ${isActive ? activeCls : inactiveCls}`}
    >
      <span className="text-base flex items-center leading-none">{ICONS[tab.key]}</span>
      <span>{tab.title}</span>
      {tab.closable && (
        <button
          type="button"
          aria-label={`关闭 ${tab.title}`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => onClose(tab.key, e)}
          className="ml-1 w-4 h-4 rounded hover:bg-slate-200 flex items-center justify-center text-slate-400 hover:text-slate-700"
        >
          <CloseOutlined style={{ fontSize: 10 }} />
        </button>
      )}
    </div>
  );
}

interface WorkspaceTabsProps {
  className?: string;
}

export function WorkspaceTabs({ className }: WorkspaceTabsProps) {
  const tabs = useWorkspaceStore((s) => s.tabs);
  const activeKey = useWorkspaceStore((s) => s.activeKey);
  const openTab = useWorkspaceStore((s) => s.openTab);
  const closeTab = useWorkspaceStore((s) => s.closeTab);
  const reorder = useWorkspaceStore((s) => s.reorder);

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const key = findRouteByPath(location.pathname);
    if (key) openTab(key);
  }, [location.pathname, openTab]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function onActivate(key: WorkspaceRouteKey) {
    if (key === activeKey) return;
    navigate(WORKSPACE_ROUTES[key].path);
  }

  function onClose(key: WorkspaceRouteKey, e: MouseEvent) {
    e.stopPropagation();
    const wasActive = key === activeKey;
    const nextKey = closeTab(key);
    if (wasActive && nextKey !== key) {
      navigate(WORKSPACE_ROUTES[nextKey].path);
    }
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    reorder(active.id as WorkspaceRouteKey, over.id as WorkspaceRouteKey);
  }

  return (
    <div
      className={`flex items-end gap-1 h-11 px-4 bg-slate-50 border-b border-slate-200 overflow-x-auto ${className ?? ""}`}
    >
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        modifiers={[restrictToHorizontalAxis, restrictToParentElement]}
        onDragEnd={onDragEnd}
      >
        <SortableContext
          items={tabs.map((t) => t.key)}
          strategy={horizontalListSortingStrategy}
        >
          {tabs.map((t) => (
            <SortableTabItem
              key={t.key}
              tab={t}
              isActive={t.key === activeKey}
              onActivate={onActivate}
              onClose={onClose}
            />
          ))}
        </SortableContext>
      </DndContext>
    </div>
  );
}
