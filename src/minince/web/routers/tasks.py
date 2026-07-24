from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.application.services.task_executor import TaskExecutor
from minince.application.services.task_service import TaskService
from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import DeviceNotFoundError, TaskExecutionError, TaskNotFoundError, ValidationError

router = APIRouter(prefix="/tasks", tags=["tasks"])

TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")

_jinja_env: Environment | None = None


def get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=True,
            cache_size=0,
        )
    return _jinja_env


def render_template(template_name: str, **kwargs) -> str:
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)


def _create_task_service(db: Session) -> TaskService:
    return TaskService(
        task_repo=TaskRepository(db),
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
    )


def _create_task_executor(db: Session) -> TaskExecutor:
    return TaskExecutor(
        task_repo=TaskRepository(db),
        device_repo=DeviceRepository(db),
        audit_repo=AuditLogRepository(db),
        encryption=EncryptionManager(),
    )


@router.get("", response_class=HTMLResponse, response_model=None)
async def task_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_task_service(db)
    tasks, total = service.list_tasks()
    html = render_template(
        "tasks.html",
        request=request,
        tasks=tasks,
        total=total,
        active_page="tasks",
    )
    return HTMLResponse(content=html)


@router.get("/new/vlan", response_class=HTMLResponse, response_model=None)
async def task_new_vlan(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    device_repo = DeviceRepository(db)
    devices = device_repo.get_all()
    html = render_template(
        "task_vlan_form.html",
        request=request,
        devices=devices,
        form_data={},
        active_page="tasks",
    )
    return HTMLResponse(content=html)


@router.post("/new/vlan", response_class=HTMLResponse, response_model=None)
async def task_create_vlan(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_task_service(db)
    try:
        task = service.create_vlan_task(
            device_id=int(form.get("device_id", "0")),
            operation=form.get("operation", "create"),
            vlan_id=int(form.get("vlan_id", "0")),
            name=form.get("name") or None,
            description=form.get("description") or None,
            created_by=form.get("created_by", "web"),
        )
        return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)
    except (DeviceNotFoundError, ValidationError) as e:
        device_repo = DeviceRepository(db)
        devices = device_repo.get_all()
        html = render_template(
            "task_vlan_form.html",
            request=request,
            devices=devices,
            form_data=form,
            error=str(e),
            active_page="tasks",
        )
        return HTMLResponse(content=html, status_code=400)


@router.get("/new/interface", response_class=HTMLResponse, response_model=None)
async def task_new_interface(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    device_repo = DeviceRepository(db)
    devices = device_repo.get_all()
    html = render_template(
        "task_interface_form.html",
        request=request,
        devices=devices,
        form_data={},
        active_page="tasks",
    )
    return HTMLResponse(content=html)


@router.post("/new/interface", response_class=HTMLResponse, response_model=None)
async def task_create_interface(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    form = await request.form()
    service = _create_task_service(db)
    try:
        trunk_vlans_str = form.get("trunk_allowed_vlans", "")
        trunk_vlans = None
        if trunk_vlans_str:
            trunk_vlans = [int(v.strip()) for v in trunk_vlans_str.split(",") if v.strip()]

        admin_up = None
        admin_up_str = form.get("admin_up")
        if admin_up_str == "on":
            admin_up = True
        elif admin_up_str == "off":
            admin_up = False

        access_vlan_val = form.get("access_vlan")
        access_vlan = int(access_vlan_val) if access_vlan_val else None

        task = service.create_interface_task(
            device_id=int(form.get("device_id", "0")),
            interface_name=form.get("interface_name", ""),
            description=form.get("description") or None,
            admin_up=admin_up,
            link_type=form.get("link_type") or None,
            access_vlan=access_vlan,
            trunk_allowed_vlans=trunk_vlans,
            created_by=form.get("created_by", "web"),
        )
        return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)
    except (DeviceNotFoundError, ValidationError) as e:
        device_repo = DeviceRepository(db)
        devices = device_repo.get_all()
        html = render_template(
            "task_interface_form.html",
            request=request,
            devices=devices,
            form_data=form,
            error=str(e),
            active_page="tasks",
        )
        return HTMLResponse(content=html, status_code=400)


@router.get("/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_detail(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = _create_task_service(db)
    try:
        task = service.get_task(task_id)
        steps = service.get_task_steps(task_id)
        html = render_template(
            "task_detail.html",
            request=request,
            task=task,
            steps=steps,
            active_page="tasks",
        )
        return HTMLResponse(content=html)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/preview", response_class=HTMLResponse, response_model=None)
async def task_preview(
    task_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    executor = _create_task_executor(db)
    try:
        plan = executor.preview_task(task_id)
        db_session = db
        from minince.infrastructure.repositories.task_repository import TaskRepository
        task_repo = TaskRepository(db_session)
        task = task_repo.get_by_id(task_id)
        steps = task_repo.get_steps_by_task_id(task_id)
        html = render_template(
            "task_detail.html",
            request=None,
            task=task,
            steps=steps,
            plan=plan.to_dict(),
            active_page="tasks",
        )
        return HTMLResponse(content=html)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/execute", response_class=HTMLResponse, response_model=None)
async def task_execute(
    task_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    executor = _create_task_executor(db)
    try:
        executor.execute_task(task_id)
        return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)
    except TaskNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TaskExecutionError as e:
        return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/delete", response_class=HTMLResponse, response_model=None)
async def task_delete(
    task_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    task_repo = TaskRepository(db)
    task_repo.delete_by_id(task_id)
    return RedirectResponse(url="/tasks", status_code=303)
