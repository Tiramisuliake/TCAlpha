# /api — 快速创建一个 API endpoint

只生成后端 API + service + schema 三件套（不动数据库、不动前端）。

## 流程

1. 问：endpoint 路径 + 方法 + 用途 + 入参出参
2. 写 `backend/app/schemas/<x>.py` 加 DTO（如已有就 append）
3. 写或修 `backend/app/services/<x>.py` 加业务函数
4. 写或修 `backend/app/api/<x>.py` 加路由
5. 如果是新 router：在 `backend/app/main.py` include
6. 写或修 `backend/tests/test_<x>.py` 加冒烟测试
7. 跑 `cd backend && uv run pytest tests/test_<x>.py`

## 模板

```python
# api
@router.get("/foo/{id}", response_model=FooOut)
async def get_foo(id: int, db: AsyncSession = Depends(get_db), uid: int = Depends(get_current_user_id)):
    return await foo_svc.get(db, uid, id)

# service
async def get(db: AsyncSession, uid: int, id: int) -> FooOut:
    obj = await db.get(Foo, id)
    if not obj or obj.user_id != uid:
        raise HTTPException(404, "not found")
    return FooOut.model_validate(obj)
```

## 不做

- 不改 ORM / 不写迁移（用 `/dev` 或手动）
- 不改前端（再开 `/dev`）
