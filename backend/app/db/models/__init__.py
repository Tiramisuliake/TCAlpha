"""ORM 模型集中导入入口（供 alembic autogenerate 扫描）。"""
from app.db.models.ai_alert import AiAlert  # noqa: F401
from app.db.models.backtest import BacktestJob, BacktestTrade  # noqa: F401
from app.db.models.notify import NotifyLog, NotifyRule  # noqa: F401
from app.db.models.order import SimOrder  # noqa: F401
from app.db.models.permission import Permission  # noqa: F401
from app.db.models.role import Role, RolePermission, UserRole  # noqa: F401
from app.db.models.strategy import StrategyConfig  # noqa: F401
from app.db.models.symbol import Symbol  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.models.watchlist import Watchlist  # noqa: F401
