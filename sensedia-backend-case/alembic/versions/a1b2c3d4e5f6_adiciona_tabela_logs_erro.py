"""Adiciona tabela logs_erro

Revision ID: a1b2c3d4e5f6
Revises: 4488db10a0dd
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4488db10a0dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('logs_erro',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('correlation_id', sa.String(length=36), nullable=True),
        sa.Column('endpoint', sa.String(length=255), nullable=True),
        sa.Column('method', sa.String(length=10), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('module', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_logs_erro_id'), 'logs_erro', ['id'], unique=False)
    op.create_index(op.f('ix_logs_erro_timestamp'), 'logs_erro', ['timestamp'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_logs_erro_timestamp'), table_name='logs_erro')
    op.drop_index(op.f('ix_logs_erro_id'), table_name='logs_erro')
    op.drop_table('logs_erro')
