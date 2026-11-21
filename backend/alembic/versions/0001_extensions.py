"""Enable PostgreSQL extensions required for Phase 6.0.2.

Revision ID: 0001_extensions
Revises:
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001_extensions"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # gen_random_uuid() — available via pgcrypto on older PG; built-in on PG13+
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')


def downgrade() -> None:
    # Do not drop pgcrypto — may be shared by other objects on Supabase.
    pass
