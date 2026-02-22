"""
vector_client.py — Actian VectorAI DB gRPC client
Service: vdss.VDSSService @ localhost:50051

Field mappings confirmed via grpcurl describe:
  UpsertVectorRequest  → collection_name, vector_id (VectorIdentifier), vector (Vector), payload (Payload)
  VectorIdentifier     → oneof id: u64_id (uint64) | uuid (string)  ← we use uuid
  Vector               → data (repeated float), dimension (uint32)
  Payload              → json (string)  ← we dump metadata dict to JSON string
  SearchRequest        → collection_name, query (Vector), top_k, with_payload (bool)
  SearchResponse       → status, results (repeated SearchResult)
  SearchResult         → id (VectorIdentifier), score (float), vector?, payload?

Generate stubs (run once):
  python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. vdss.proto
"""

import os, json, logging
import grpc
from typing import Optional
import uuid

log = logging.getLogger(__name__)

try:
    import vdss_pb2
    import vdss_pb2_grpc
    _HAS_STUBS = True
except ImportError:
    _HAS_STUBS = False
    log.warning("vdss proto stubs not found — run grpc_tools.protoc to generate vdss_pb2.py")


class VectorAIClient:
    def __init__(self, host="localhost", port=50051, collection="cleansight_sessions"):
        self.host       = host
        self.port       = port
        self.collection = collection
        self._channel   = None
        self._stub      = None
        self._connect()

    def _connect(self):
        if not _HAS_STUBS:
            return
        try:
            self._channel = grpc.insecure_channel(f"{self.host}:{self.port}")
            self._stub    = vdss_pb2_grpc.VDSSServiceStub(self._channel)
            grpc.channel_ready_future(self._channel).result(timeout=5)
            log.info(f"VectorAI connected at {self.host}:{self.port}")
        except Exception as e:
            log.error(f"VectorAI connection failed: {e}")
            self._stub = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def upsert(self, id: str, vector: list, metadata: dict) -> bool:
        """
        Insert or update one vector record.
          id       — session_id string (stored as uuid)
          vector   — flat list of floats
          metadata — dict (will be JSON-serialised into Payload.json)
        """
        if self._stub is None:
            log.warning(f"upsert skipped (no connection): {id}")
            return False
        try:
            request = vdss_pb2.UpsertVectorRequest(
                collection_name=self.collection,
                vector_id=vdss_pb2.VectorIdentifier(uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, id))),
                vector=vdss_pb2.Vector(
                    data=vector,
                    dimension=len(vector),
                ),
                payload=vdss_pb2.Payload(
                    json=json.dumps(metadata)   # Payload.json is a plain string
                ),
            )
            self._stub.UpsertVector(request, timeout=10)
            self._stub.Flush(vdss_pb2.FlushRequest(collection_name=self.collection), timeout=10)
            return True
        except grpc.RpcError as e:
            log.error(f"VectorAI upsert error: {e.code()} — {e.details()}")
            return False

    def query(self, vector: list, top_k: int = 3) -> list:
        """
        Return top_k most similar vectors (cosine similarity, descending).
        Each result: { id: str, score: float, metadata: dict }
        """
        if self._stub is None:
            log.warning("query skipped (no connection)")
            return []
        try:
            request = vdss_pb2.SearchRequest(
                collection_name=self.collection,
                query=vdss_pb2.Vector(
                    data=vector,
                    dimension=len(vector),
                ),
                top_k=top_k,
                with_vector=False,   # we don't need the raw vector back
                with_payload=True,   # we DO need the metadata
            )
            response = self._stub.Search(request, timeout=10)

            results = []
            for match in response.results:
                # VectorIdentifier uses oneof — we stored as uuid
                match_id = match.id.uuid

                # Payload.json is a JSON string — parse it back to dict
                meta = {}
                if match.HasField("payload") and match.payload.json:
                    try:
                        meta = json.loads(match.payload.json)
                    except json.JSONDecodeError:
                        pass

                results.append({
                    "id":       match_id,
                    "score":    round(match.score, 4),
                    "metadata": meta,
                })
            return results

        except grpc.RpcError as e:
            log.error(f"VectorAI query error: {e.code()} — {e.details()}")
            return []

    def delete(self, id: str) -> bool:
        """Remove a vector by its uuid string ID."""
        if self._stub is None:
            return False
        try:
            request = vdss_pb2.DeleteVectorRequest(
                collection_name=self.collection,
                vector_id=vdss_pb2.VectorIdentifier(uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, id))),
            )
            self._stub.DeleteVector(request, timeout=10)
            return True
        except grpc.RpcError as e:
            log.error(f"VectorAI delete error: {e.code()} — {e.details()}")
            return False

    def ensure_collection(self, dimension=202):
        """
        Create the collection if it doesn't already exist.
        Call this once at startup before any upsert/query.
        dimension must match your vector length (10x10x2 + 2 summary floats = 202).
        """
        if self._stub is None:
            return
        try:
            config = vdss_pb2.CollectionConfig(
                index_driver=vdss_pb2.IndexDriver.Value("FAISS"),
                index_algorithm=vdss_pb2.IndexAlgorithm.Value("HNSW"),
                storage_type=vdss_pb2.StorageType.Value("BTRIEVE_FILE"),
                dimension=dimension,
                distance_metric=vdss_pb2.DistanceMetric.Value("COSINE"),
            )
            request = vdss_pb2.CreateCollectionRequest(
                collection_name=self.collection,
                config=config,
            )
            resp = self._stub.CreateCollection(request, timeout=10)
            log.info(f"Collection '{self.collection}' ready (dim={dimension}): {resp.status.message}")
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.ALREADY_EXISTS:
                log.error(f"CreateCollection error: {e.code()} — {e.details()}")

    def close(self):
        if self._channel:
            self._channel.close()