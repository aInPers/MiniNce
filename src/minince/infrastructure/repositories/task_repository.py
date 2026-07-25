from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from minince.infrastructure.database.models import ConfigTask, TaskStep
from minince.infrastructure.repositories.base import BaseRepository


class TaskRepository(BaseRepository):
    def get_by_id(self, task_id: int) -> ConfigTask | None:
        stmt = select(ConfigTask).where(ConfigTask.id == task_id)
        return self.scalar_one(stmt)

    def get_by_task_number(self, task_number: str) -> ConfigTask | None:
        stmt = select(ConfigTask).where(ConfigTask.task_number == task_number)
        return self.scalar_one(stmt)

    def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> list[ConfigTask]:
        stmt = select(ConfigTask)
        if status:
            stmt = stmt.where(ConfigTask.status == status)
        stmt = stmt.order_by(ConfigTask.created_at.desc()).offset(skip).limit(limit)
        return self.scalars(stmt)

    def count_all(self, status: str | None = None) -> int:
        stmt = select(ConfigTask)
        if status:
            stmt = stmt.where(ConfigTask.status == status)
        return self.count(stmt)

    def create(
        self,
        task_number: str,
        task_type: str,
        device_id: int,
        risk_level: str = "LOW",
        original_request: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> ConfigTask:
        task = ConfigTask(
            task_number=task_number,
            task_type=task_type,
            device_id=device_id,
            status="DRAFT",
            risk_level=risk_level,
            original_request=original_request,
            created_by=created_by,
        )
        self.add(task)
        self.commit()
        self.refresh(task)
        return task

    def update(self, task_id: int, **kwargs: Any) -> ConfigTask | None:
        task = self.get_by_id(task_id)
        if task is None:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)

        task.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(task)
        return task

    def delete_by_id(self, task_id: int) -> bool:
        task = self.get_by_id(task_id)
        if task is None:
            return False

        self.delete(task)
        self.commit()
        return True

    def update_status(self, task_id: int, status: str) -> ConfigTask | None:
        task = self.get_by_id(task_id)
        if task is None:
            return None

        task.status = status
        if status == "RUNNING" and task.started_at is None:
            task.started_at = datetime.utcnow()
        if status in ("SUCCEEDED", "FAILED", "PARTIAL"):
            task.completed_at = datetime.utcnow()

        task.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(task)
        return task

    def try_acquire_task(
        self,
        task_id: int,
        expected_status: str,
        new_status: str,
        locked_by: str = "system",
    ) -> tuple[bool, str | None]:
        """原子抢占任务，防止并发执行。

        通过条件 UPDATE 实现乐观锁：仅当任务状态和版本号匹配时才更新。
        受影响行数为 1 表示抢占成功，为 0 表示任务已被其他执行器抢占。

        Args:
            task_id: 任务 ID
            expected_status: 期望的当前状态（如 DRAFT/FAILED）
            new_status: 抢占后的新状态（如 VALIDATING）
            locked_by: 抢占者标识

        Returns:
            (success, execution_token) 元组
        """
        token = str(uuid.uuid4())
        now = datetime.utcnow()

        # 先读取当前任务获取 version
        task = self.get_by_id(task_id)
        if task is None:
            return False, None

        # 条件更新：状态匹配 + 版本号匹配
        stmt = (
            update(ConfigTask)
            .where(
                ConfigTask.id == task_id,
                ConfigTask.status == expected_status,
                ConfigTask.version == task.version,
            )
            .values(
                status=new_status,
                version=task.version + 1,
                execution_token=token,
                locked_at=now,
                locked_by=locked_by,
                updated_at=now,
            )
        )
        result = self.db.execute(stmt)
        self.commit()

        if result.rowcount == 1:
            return True, token
        return False, None

    def verify_execution_token(self, task_id: int, token: str) -> bool:
        """验证执行令牌是否属于当前任务。"""
        task = self.get_by_id(task_id)
        if task is None:
            return False
        return task.execution_token == token

    def get_steps_by_task_id(self, task_id: int) -> list[TaskStep]:
        stmt = (
            select(TaskStep)
            .where(TaskStep.task_id == task_id)
            .order_by(TaskStep.created_at)
        )
        return self.scalars(stmt)

    def get_step_by_id(self, step_id: int) -> TaskStep | None:
        stmt = select(TaskStep).where(TaskStep.id == step_id)
        return self.scalar_one(stmt)

    def get_active_step_by_name(self, task_id: int, step_name: str) -> TaskStep | None:
        """获取任务中指定名称的最近活动步骤。

        用于步骤生命周期管理：若同名步骤已存在且未终结，则复用而非新建。
        """
        stmt = (
            select(TaskStep)
            .where(
                TaskStep.task_id == task_id,
                TaskStep.step_name == step_name,
                TaskStep.status.in_(["PENDING", "RUNNING"]),
            )
            .order_by(TaskStep.created_at.desc())
            .limit(1)
        )
        return self.scalar_one(stmt)

    def create_step(
        self,
        task_id: int,
        step_name: str,
        status: str = "PENDING",
        input_data: dict[str, Any] | None = None,
    ) -> TaskStep:
        step = TaskStep(
            task_id=task_id,
            step_name=step_name,
            status=status,
            input_data=input_data,
            started_at=datetime.utcnow() if status == "RUNNING" else None,
        )
        self.add(step)
        self.commit()
        self.refresh(step)
        return step

    def update_step(
        self,
        step_id: int,
        status: str | None = None,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> TaskStep | None:
        step = self.get_step_by_id(step_id)
        if step is None:
            return None

        if status:
            step.status = status
            if status == "RUNNING" and step.started_at is None:
                step.started_at = datetime.utcnow()
            if status in ("SUCCEEDED", "FAILED"):
                step.completed_at = datetime.utcnow()

        if input_data is not None:
            step.input_data = input_data
        if output_data is not None:
            step.output_data = output_data
        if error_message is not None:
            step.error_message = error_message

        step.updated_at = datetime.utcnow()
        self.commit()
        self.refresh(step)
        return step
