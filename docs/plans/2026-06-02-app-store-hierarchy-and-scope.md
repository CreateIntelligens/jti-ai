# App↔Store Hierarchy and Scope Authorization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish an explicit app-to-store hierarchy for dynamic knowledge stores using Option B (storing `managed_app` in MongoDB), update the backend API and frontend dropdown filtering, and implement app-scope authorization in general chats.

**Architecture:**
- Create `resolve_app_for_key_index` in `app/services/app_key_map.py` to reverse-resolve key indices to their corresponding app names defined in `APP_KEY_MAP`.
- Modify `StoreRegistry` (in `app/routers/general/stores.py`) to support `managed_app` database field storage, retrieval, and filtering.
- Modify the store listing API `GET /api/stores` to filter managed and dynamic stores by the `app` query param.
- Update `_resolve_request_store` in `app/routers/general/chat.py` to enforce app-scoped authorization for user-role chats when `store_name` is omitted/null.
- Write a database migration script `scripts/migrate_stores_app.py` to retroactively set `managed_app` on existing dynamic stores.
- Update the frontend TypeScript types in `frontend/src/types/index.ts` to support the `'general'` AppTarget.
- Modify `api.fetchStores` in `frontend/src/services/api/general.ts` to pass the optional `app` query parameter.
- Update `UsersPanel.tsx` to dynamically fetch and display store names in a dropdown select based on the currently selected app in the user creation form.

**Tech Stack:** FastAPI, Pydantic, MongoDB, React, TypeScript.

---

### Task 1: Backend Schema & Migration Helper

**Files:**
- Modify: `app/services/app_key_map.py`
- Modify: `app/routers/general/stores.py`
- Create: `scripts/migrate_stores_app.py`
- Modify: `tests/services/test_app_key_map.py`
- Modify: `tests/general/test_home_api_compat.py`

**Step 1: Write test for resolve_app_for_key_index**
Add to `tests/services/test_app_key_map.py`:
```python
def test_resolve_app_for_key_index(monkeypatch):
    monkeypatch.setenv("APP_KEY_MAP", "jti:JTI傑太日煙,hciot:護聯HCIOT")
    monkeypatch.setattr(app_key_map.gemini_clients, "get_key_names", lambda: ["Key #1", "JTI傑太日煙", "護聯HCIOT"])
    
    assert app_key_map.resolve_app_for_key_index(1) == "jti"
    assert app_key_map.resolve_app_for_key_index(2) == "hciot"
    assert app_key_map.resolve_app_for_key_index(0) == "general"
    assert app_key_map.resolve_app_for_key_index(-1) == "general"
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/services/test_app_key_map.py::test_resolve_app_for_key_index`
Expected: AttributeError/ImportError for `resolve_app_for_key_index`.

**Step 3: Implement resolve_app_for_key_index**
Add to `app/services/app_key_map.py`:
```python
def resolve_app_for_key_index(key_index: int) -> str:
    """Resolve a Gemini key index back to an app name using APP_KEY_MAP.
    
    If no mapping exists, returns 'general'.
    """
    names = gemini_clients.get_key_names()
    if not (0 <= key_index < len(names)):
        return "general"
    
    key_name = names[key_index].strip().lower()
    mapping = load_app_key_map()
    for app, kname in mapping.items():
        if kname.strip().lower() == key_name:
            return app
    return "general"
```

**Step 4: Verify test passes**
Run: `pytest tests/services/test_app_key_map.py`
Expected: All tests pass.

**Step 5: Modify StoreRegistry to support managed_app**
In `app/routers/general/stores.py`:
- Update `StoreRegistry.create_store` signature and logic:
```python
    def create_store(
        self,
        display_name: str,
        key_index: int = 0,
        owner_key_hash: str | None = None,
        managed_app: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if managed_app is None:
            if owner_key_hash:
                app = "general"
            else:
                app = app_key_map.resolve_app_for_key_index(int(key_index))
        else:
            app = managed_app.strip().lower()

        doc = {
            "name": self._new_store_name(),
            "display_name": display_name.strip(),
            "key_index": None if owner_key_hash else int(key_index),
            "owner_key_hash": owner_key_hash,
            "managed_app": app,
            "created_at": now,
            "updated_at": now,
        }
        self.collection.insert_one(doc)
        return self._payload(doc)
```
- Update `StoreRegistry._payload`:
```python
    @staticmethod
    def _payload(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("name"),
            "display_name": doc.get("display_name") or doc.get("name"),
            "key_index": doc.get("key_index"),
            "created_at": doc.get("created_at"),
            "owner_key_hash": doc.get("owner_key_hash"),
            "managed_app": doc.get("managed_app", "general"),
        }
```
- Update `StoreRegistry.list_stores` to accept an optional `app` filter:
```python
    def list_stores(self, owner_key_hash: str | None = None, app: str | None = None) -> list[dict[str, Any]]:
        query = self._owner_filter(owner_key_hash)
        if app:
            query["managed_app"] = app.strip().lower()
        try:
            docs = self.collection.find(query, {"_id": 0}).sort("created_at", 1)
            return [self._payload(doc) for doc in docs]
        except Exception as exc:
            logger.warning("Failed to list dynamic stores: %s", exc)
            return []
```
- Update `_dynamic_store_payload`:
```python
def _dynamic_store_payload(store: dict[str, Any]) -> dict[str, Any]:
    store_name = store["name"]
    return {
        "name": store_name,
        "display_name": store.get("display_name") or store_name,
        "file_count": len(_list_general_store_files(store_name)),
        "created_at": store.get("created_at"),
        "managed_app": store.get("managed_app", "general"),
        "managed_language": None,
        "key_index": store.get("key_index"),
    }
```
- Update `resolve_store_config`:
```python
def resolve_store_config(store_name: str | None, owner_key_hash: str | None = None) -> ManagedStoreConfig | None:
    managed = resolve_managed_store(store_name)
    if managed is not None:
        return managed

    normalized = normalize_store_name(store_name)
    dynamic = get_store_registry().get_store(normalized, owner_key_hash)
    if not dynamic:
        return None
    return ManagedStoreConfig(
        name=dynamic["name"],
        display_name=dynamic.get("display_name") or dynamic["name"],
        managed_app=dynamic.get("managed_app", "general"),
        managed_language="",
        key_index=dynamic.get("key_index"),
    )
```

- Update `POST /api/stores` route:
```python
@router.post("/stores")
def create_store(request_data: CreateStoreRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Create a general homepage knowledge store bound to the selected Gemini key."""
    require_admin(auth)
    display_name = _validate_store_name(request_data.display_name)
    owner_hash = _owner_key_hash(request)
    key_index = _validate_key_index(request_data.key_index, owner_hash)
    
    app = app_key_map.resolve_app_for_key_index(key_index)
    
    store = get_store_registry().create_store(
        display_name=display_name,
        key_index=key_index,
        owner_key_hash=owner_hash,
        managed_app=app,
    )
    return _dynamic_store_payload(store)
```

- Update test fakes in `tests/general/test_home_api_compat.py`:
Modify `FakeStoreRegistry` methods:
```python
    def list_stores(self, owner_key_hash=None, app=None):
        stores = [
            store
            for store in self.stores.values()
            if self._matches_owner(store, owner_key_hash)
        ]
        if app:
            stores = [s for s in stores if s.get("managed_app") == app]
        return stores

    def create_store(self, display_name, key_index=0, owner_key_hash=None, managed_app=None):
        name = "store_hotai"
        store = {
            "name": name,
            "display_name": display_name,
            "key_index": key_index,
            "created_at": "2026-04-30T00:00:00Z",
            "owner_key_hash": owner_key_hash,
            "managed_app": managed_app or "general",
        }
        self.stores[name] = store
        return store
```
- In `test_home_can_create_key_owned_general_store`, update assertion:
```python
    assert store["managed_app"] == "general"
```

**Step 6: Run tests to verify the compatibility test suite still passes**
Run: `pytest tests/general/test_home_api_compat.py`
Expected: All tests pass.

**Step 7: Create the migration script scripts/migrate_stores_app.py**
Create the file with the following contents:
```python
#!/usr/bin/env python3
"""Migration script to populate managed_app for dynamic stores."""

import logging
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.mongo_client import get_mongo_db
from app.routers.general.stores import StoreRegistry
from app.services import app_key_map, gemini_clients

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_stores_app")

def main():
    # Initialize gemini clients registry to populate key names
    gemini_clients.init_registry()
    
    db = get_mongo_db("jti_app")
    collection = db[StoreRegistry.COLLECTION_NAME]
    
    logger.info("Starting migration of dynamic stores managed_app...")
    
    cursor = collection.find({"managed_app": {"$exists": False}})
    count = 0
    for doc in cursor:
        store_name = doc.get("name")
        key_index = doc.get("key_index")
        
        if key_index is None:
            app = "general"
        else:
            app = app_key_map.resolve_app_for_key_index(int(key_index))
            
        logger.info("Migrating store %s (key_index=%s) -> managed_app=%s", store_name, key_index, app)
        collection.update_one({"_id": doc["_id"]}, {"$set": {"managed_app": app}})
        count += 1
        
    logger.info("Migration completed. Updated %d stores.", count)

if __name__ == "__main__":
    main()
```
Run the migration script: `python scripts/migrate_stores_app.py` or inside docker if appropriate.

---

### Task 2: Filter Stores API & Auth Refinements

**Files:**
- Modify: `app/routers/general/stores.py`
- Modify: `tests/general/test_home_api_compat.py`

**Step 1: Write test for API app filtering**
Add to `tests/general/test_home_api_compat.py`:
```python
def test_list_stores_filtering_by_app(monkeypatch):
    from app.routers.general import stores as store_routes
    registry = FakeStoreRegistry()
    registry.create_store("和泰", key_index=1, managed_app="hciot")
    registry.create_store("傑太自建", key_index=2, managed_app="jti")
    
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    
    client = TestClient(app)
    
    # Filter by hciot
    res_hciot = client.get("/api/stores?app=hciot", headers={"Origin": "http://testserver"})
    assert res_hciot.status_code == 200
    hciot_stores = res_hciot.json()
    assert all(s["managed_app"] == "hciot" for s in hciot_stores)
    assert any(s["name"] == "store_hotai" for s in hciot_stores)
    assert not any(s["display_name"] == "傑太自建" for s in hciot_stores)
    
    # Filter by jti
    res_jti = client.get("/api/stores?app=jti", headers={"Origin": "http://testserver"})
    assert res_jti.status_code == 200
    jti_stores = res_jti.json()
    assert all(s["managed_app"] == "jti" for s in jti_stores)
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/general/test_home_api_compat.py::test_list_stores_filtering_by_app`
Expected: FAIL due to unsupported query param or failure to filter.

**Step 3: Modify list_stores endpoint**
In `app/routers/general/stores.py`:
```python
@router.get("/stores")
def list_stores(request: Request, app: Optional[str] = None, auth: dict = Depends(verify_auth)):
    """Return fixed app stores plus key-owned general homepage stores."""
    require_admin(auth)
    owner_hash = _owner_key_hash(request)
    
    managed = [_managed_store_payload(config) for config in MANAGED_STORES]
    dynamic = [_dynamic_store_payload(store) for store in get_store_registry().list_stores(owner_hash, app=app)]
    
    if app:
        normalized_app = app.strip().lower()
        managed = [m for m in managed if (m.get("managed_app") or "").strip().lower() == normalized_app]
        
    return managed + dynamic
```

**Step 4: Verify tests pass**
Run: `pytest tests/general/test_home_api_compat.py`
Expected: PASS.

---

### Task 3: Chat Scope Authorization

**Files:**
- Modify: `app/routers/general/chat.py`
- Modify: `tests/general/test_home_api_compat.py`

**Step 1: Write tests for app-scoped user authorization**
Add to `tests/general/test_home_api_compat.py`:
```python
def test_resolve_request_store_scope_authorization(monkeypatch):
    from app.routers.general import chat as general_chat
    from app.routers.general import stores as store_routes
    
    registry = FakeStoreRegistry()
    registry.stores["store_hciot_custom"] = {
        "name": "store_hciot_custom",
        "display_name": "HCIOT自建",
        "key_index": 1,
        "managed_app": "hciot"
    }
    registry.stores["store_jti_custom"] = {
        "name": "store_jti_custom",
        "display_name": "JTI自建",
        "key_index": 2,
        "managed_app": "jti"
    }
    monkeypatch.setattr(store_routes, "get_store_registry", lambda: registry, raising=False)
    
    # 1. User with store_name set can only chat with their assigned store
    auth_user_fixed = {"role": "user", "app": "hciot", "store_name": "store_hciot_custom"}
    req_jti = general_chat.ChatStartRequest(store_name="store_jti_custom")
    
    # It overrides the requested store with the fixed store name
    resolved = general_chat._resolve_request_store(req_jti, auth_user_fixed)
    assert resolved == "store_hciot_custom"
    
    # 2. User with null/empty store_name can chat with any store belonging to their app
    auth_user_app_only = {"role": "user", "app": "hciot", "store_name": None}
    req_hciot_custom = general_chat.ChatStartRequest(store_name="store_hciot_custom")
    assert general_chat._resolve_request_store(req_hciot_custom, auth_user_app_only) == "store_hciot_custom"
    
    # 3. User with null/empty store_name gets 403 when trying to access a store of another app
    with pytest.raises(HTTPException) as excinfo:
        general_chat._resolve_request_store(req_jti, auth_user_app_only)
    assert excinfo.value.status_code == 403
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/general/test_home_api_compat.py::test_resolve_request_store_scope_authorization`
Expected: FAIL since 403 isn't raised.

**Step 3: Modify _resolve_request_store in app/routers/general/chat.py**
Update `_resolve_request_store` in `app/routers/general/chat.py`:
```python
def _resolve_request_store(
    req: ChatStartRequest,
    auth: dict,
    owner_key_hash: str | None = None,
) -> str:
    if auth.get("role") == "user":
        user_store = auth.get("store_name")
        if user_store:
            requested = user_store
        else:
            requested = req.store_name
            user_app = auth.get("app")
            if not user_app:
                raise HTTPException(status_code=403, detail="User has no assigned app")
            config = resolve_store_config(requested, owner_key_hash)
            if config is None:
                raise HTTPException(status_code=404, detail="Knowledge store not found")
            if (config.managed_app or "").strip().lower() != user_app.strip().lower():
                raise HTTPException(status_code=403, detail="Access denied to this store")
            return config.name
    else:
        requested = req.store_name

    config = resolve_store_config(requested, owner_key_hash)
    if config is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    return config.name
```

**Step 4: Verify all python tests pass**
Run: `pytest`
Expected: PASS.

---

### Task 4: Frontend KB Dropdown Selector

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api/general.ts`
- Modify: `frontend/src/components/UsersPanel.tsx`

**Step 1: Update frontend AppTarget type**
In `frontend/src/types/index.ts`:
Change line 11:
```typescript
export type AppTarget = 'jti' | 'hciot' | 'general';
```

**Step 2: Modify api.fetchStores in frontend/src/services/api/general.ts**
Update `fetchStores` signature to support optional `app` query param:
```typescript
export async function fetchStores(app?: string): Promise<Store[]> {
  const url = app ? `${API_BASE}/stores?app=${encodeURIComponent(app)}` : `${API_BASE}/stores`;
  const response = await fetchWithUserGeminiKey(url);
  return handleResponse<Store[]>(response);
}
```

**Step 3: Update UsersPanel.tsx to fetch stores and display them in a select dropdown**
In `frontend/src/components/UsersPanel.tsx`:
- Import `Store` type if needed or use `api.Store`.
- Declare state for `stores`:
```typescript
  const [stores, setStores] = useState<api.Store[]>([]);
```
- Define `loadStores`:
```typescript
  const loadStores = useCallback(async () => {
    try {
      const data = await api.fetchStores();
      setStores(data);
    } catch (err: unknown) {
      console.error('無法獲取知識庫列表', err);
    }
  }, []);
```
- Fetch stores inside the `useEffect` trigger:
```typescript
  useEffect(() => {
    if (isOpen) {
      void loadUsers();
      void loadStores();
      resetForm();
    }
  }, [isOpen, loadUsers, loadStores, resetForm]);
```
- In the creation form, replace the `storeName` input field with a `select` dropdown:
```tsx
                  <div className="field">
                    <label>綁定知識庫名稱 (Store Name)</label>
                    <select
                      className="select-reset input-base"
                      value={storeName}
                      onChange={(e) => setStoreName(e.target.value)}
                      disabled={loading}
                    >
                      <option value="">不選（此 App 下所有知識庫）</option>
                      {stores
                        .filter((s) => (s.managed_app || 'general') === app)
                        .map((s) => (
                          <option key={s.name} value={s.name}>
                            {s.display_name || s.name}
                          </option>
                        ))}
                    </select>
                  </div>
```
- Reset `storeName` when `app` select field changes to prevent invalid mappings:
```tsx
                  <div className="field">
                    <label>綁定應用程式 (App)</label>
                    <select
                      className="select-reset input-base"
                      value={app}
                      onChange={(e) => {
                        const newApp = e.target.value;
                        setApp(newApp);
                        setStoreName('');
                      }}
                      disabled={loading}
                    >
                      <option value="hciot">hciot</option>
                      <option value="jti">jti</option>
                    </select>
                  </div>
```

**Step 4: Run build to ensure compilation passes**
Run: `pnpm build` in the `frontend/` directory.
Expected: Build passes with no TypeScript or build errors.

---

### Task 5: Verification & End-to-End Test

**Step 1: Run complete tests**
Run: `pytest`
Run: `pnpm test` (or equivalent vitest front-end suite)
Expected: All backend and frontend tests pass.
