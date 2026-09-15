"""The type every repository and service constructor accepts.

Flask-SQLAlchemy's `db.session` is a `scoped_session`, a proxy that forwards every
`Session` method but doesn't subclass it — a plain `Session` type hint on constructors
that receive `db.session` is technically wrong even though it works at runtime. This
alias is the honest type for that call site.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, scoped_session

# `Any` here, not `Session`, because Flask-SQLAlchemy's `db.session` is a
# `scoped_session` of ITS OWN `Session` subclass, not sqlalchemy.orm.Session — pinning
# the generic parameter to the base class would reject the exact object every route
# passes in. The type still requires "a scoped session or a plain Session", which is
# the actual constraint every repository and service relies on.
DbSession = scoped_session[Any] | Session
