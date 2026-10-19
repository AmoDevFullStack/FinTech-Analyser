from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from app.models.base import Base

# `model_class=Base`, not a bare `SQLAlchemy()`. Every model in this project inherits from
# app/models/base.py's `Base`, so a bare extension carries its own, empty metadata: it knows
# about no tables at all. `db.create_all()` and `db.drop_all()` were therefore silent no-ops
# — the test database only had tables because `alembic upgrade` had built them at some
# earlier point, and the suite ran against whatever that had left behind.
#
# That was invisible until revision 0014 moved the tables into per-subsystem schemas: the
# models started asking for `identity.users` while the database still held `public.users`,
# and create_all built nothing to close the gap. Binding the extension to `Base` is what
# makes create_all/drop_all mean what every caller already assumed they meant.
db = SQLAlchemy(model_class=Base)
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)
