"""add device canvas position and type fields

Revision ID: a1b2c3d4e5f6
Revises: 7e0f82396e0d
Create Date: 2026-07-27 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7e0f82396e0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # device_type 使用 server_default 让现有行获得默认值 ROUTER
    op.add_column(
        'devices',
        sa.Column(
            'device_type',
            sa.String(length=50),
            nullable=False,
            server_default='ROUTER',
        ),
    )
    op.add_column('devices', sa.Column('canvas_x', sa.Integer(), nullable=True))
    op.add_column('devices', sa.Column('canvas_y', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'canvas_y')
    op.drop_column('devices', 'canvas_x')
    op.drop_column('devices', 'device_type')
