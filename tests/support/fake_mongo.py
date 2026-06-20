"""In-memory fake MongoDB collection/cursor for tests.

Mirrors the subset of the pymongo collection API the qa_kb stores and routers
use, so tests can exercise real store/router logic without a live Mongo. This
is the consolidated version of the fakes the general test modules need
($in / $regex matching, projections, bulk_write, find_one_and_update with
upsert, synthetic _id). Sibling tests under tests/hciot/ keep their own older
copies.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock


class FakeCursor(list):
    def sort(self, key, direction=None):
        # Support both Mongo call forms: sort("field", 1) and sort([("a",1),("b",1)]).
        keys = key if isinstance(key, list) else [(key, direction if direction is not None else 1)]
        items = list(self)
        for field, dir_ in reversed(keys):
            items.sort(key=lambda it: it.get(field, ""), reverse=dir_ < 0)
        return FakeCursor(items)


class FakeCollection:
    _id_seq = 0

    def __init__(self):
        self.docs: list[dict] = []

    def create_index(self, *args, **kwargs):
        pass

    @classmethod
    def _next_id(cls):
        cls._id_seq += 1
        return f"oid-{cls._id_seq}"

    @staticmethod
    def _matches(doc, query):
        for k, v in query.items():
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif isinstance(v, dict) and "$regex" in v:
                flags = re.IGNORECASE if "i" in v.get("$options", "") else 0
                if not re.search(v["$regex"], str(doc.get(k) or ""), flags):
                    return False
            elif doc.get(k) != v:
                return False
        return True

    @staticmethod
    def _project(doc, projection):
        if not projection:
            return dict(doc)
        include = [k for k, v in projection.items() if v]
        if include:
            return {k: doc.get(k) for k in include if k in doc}
        result = dict(doc)
        for k, v in projection.items():
            if v == 0:
                result.pop(k, None)
        return result

    def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    def find(self, query, projection=None):
        return FakeCursor(
            [self._project(d, projection) for d in self.docs if self._matches(d, query)]
        )

    def count_documents(self, query, limit=0):
        n = sum(1 for d in self.docs if self._matches(d, query))
        return min(n, limit) if limit else n

    def insert_one(self, doc):
        stored = dict(doc)
        stored.setdefault("_id", self._next_id())
        self.docs.append(stored)
        return MagicMock(inserted_id=stored["_id"])

    def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    def delete_many(self, query):
        kept = [d for d in self.docs if not self._matches(d, query)]
        removed = len(self.docs) - len(kept)
        self.docs[:] = kept
        return MagicMock(deleted_count=removed)

    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return MagicMock(matched_count=1)
        if upsert:
            self.docs.append({**update.get("$setOnInsert", {}), **update.get("$set", {})})
        return MagicMock(matched_count=0)

    def find_one_and_update(self, query, update, upsert=False, return_document=None, **kwargs):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return dict(doc)
        if upsert:
            new_doc = {**query, **update.get("$setOnInsert", {}), **update.get("$set", {})}
            new_doc.setdefault("_id", self._next_id())
            self.docs.append(new_doc)
            return dict(new_doc)
        return None

    def bulk_write(self, operations, ordered=False):
        matched = 0
        for op in operations:
            for doc in self.docs:
                if self._matches(doc, op._filter):
                    doc.update(op._doc.get("$set", {}))
                    matched += 1
                    break
        return MagicMock(matched_count=matched)
