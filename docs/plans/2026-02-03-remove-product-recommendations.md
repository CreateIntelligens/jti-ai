# Remove Product Recommendations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the product recommendation feature entirely while keeping KB chat and the MBTI quiz flow intact.

**Architecture:** The MBTI quiz remains a 5-question flow handled by the backend router, ending with persona calculation only. All recommendation tools, data, and UI references are removed. General chat continues to use the knowledge base (File Search).

**Tech Stack:** FastAPI, Pydantic v2, google-genai SDK, React (frontend).

---

### Task 1: Add failing tests for removal behavior

**Files:**
- Create: `tests/test_remove_recommendations.py`

**Step 1: Write the failing tests**

```python
import unittest

from app.models.session import Session, SessionStep
from app.services.session_manager import session_manager
from app.tools.tool_executor import tool_executor


class SessionManagerTests(unittest.TestCase):
    def test_complete_scoring_sets_done(self):
        session = session_manager.create_session()
        session_manager.start_scoring(session.session_id)
        session_manager.complete_scoring(
            session.session_id,
            persona="INTJ",
            scores={}
        )
        updated = session_manager.get_session(session.session_id)
        self.assertEqual(updated.step, SessionStep.DONE)

    def test_session_dump_excludes_recommended_products(self):
        session = Session()
        data = session.model_dump()
        self.assertNotIn("recommended_products", data)


class ToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_recommend_products_tool_removed(self):
        result = await tool_executor.execute(
            "recommend_products",
            {"session_id": "invalid-session"}
        )
        self.assertEqual(
            result.get("error"),
            "Unknown tool: recommend_products"
        )
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_remove_recommendations -v`  
Expected: FAIL (step not DONE / recommended_products key exists / tool still exists)

---

### Task 2: Remove recommendation state from session model and manager

**Files:**
- Modify: `app/models/session.py`
- Modify: `app/services/session_manager.py`

**Step 1: Remove `recommended_products` field from Session**

**Step 2: Update `complete_scoring` to set `step = DONE`**

**Step 3: Remove `save_recommendations` method**

**Step 4: Run tests**

Run: `python -m unittest tests.test_remove_recommendations -v`  
Expected: still FAIL (recommend tool still present)

---

### Task 3: Remove recommendation tool and product data

**Files:**
- Modify: `app/tools/tool_executor.py`
- Modify: `app/tools/tool_definitions.py`
- Delete: `app/tools/products.py`
- Delete: `data/products.json`

**Step 1: Remove recommend tool from tool map and imports**

**Step 2: Delete recommend tool implementation**

**Step 3: Remove tool definition from `ALL_TOOLS`**

**Step 4: Run tests**

Run: `python -m unittest tests.test_remove_recommendations -v`  
Expected: PASS

---

### Task 4: Remove recommendation references in agent layer

**Files:**
- Modify: `app/services/main_agent.py`
- Modify: `app/services/agent_prompts.py`

**Step 1: Remove `recommend_products` tool declaration**

**Step 2: Remove recommendation mentions in comments/docstrings**

**Step 3: Run tests**

Run: `python -m unittest tests.test_remove_recommendations -v`  
Expected: PASS

---

### Task 5: Update frontend copy and status handling

**Files:**
- Modify: `frontend/src/pages/JtiTest.tsx`

**Step 1: Remove “推薦商品” wording from welcome text**

**Step 2: Remove `RECOMMEND` status handling**

---

### Task 6: Update documentation

**Files:**
- Modify: `README.md`

**Step 1: Remove “商品推薦” feature references**

**Step 2: Update MBTI flow to end at persona only**

---

### Task 7: Final verification & commit

**Step 1: Run tests**

Run: `python -m unittest tests.test_remove_recommendations -v`  
Expected: PASS

**Step 2: Commit**

```bash
git add tests/test_remove_recommendations.py app/models/session.py app/services/session_manager.py app/tools/tool_executor.py app/tools/tool_definitions.py app/services/main_agent.py app/services/agent_prompts.py frontend/src/pages/JtiTest.tsx README.md
git rm app/tools/products.py data/products.json
git commit -m "remove: drop product recommendations"
```
