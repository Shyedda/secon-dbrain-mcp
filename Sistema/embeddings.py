"""Pinned multilingual E5 inference; inference is strictly local."""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
from common import load_json, save_json, file_hash, digest

MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

class E5:
    def __init__(self, root, threads=4):
        self.root = Path(root)
        self.directory = self.root / ".dbrain/models/e5"
        self.lock = load_json(self.directory / "model-lock.json")
        if not self.lock:
            raise RuntimeError("Modelo ausente; execute .\\dbrain.ps1 setup-model")
        if file_hash(self.directory / 'tokenizer.json') != self.lock['files']['tokenizer.json']:
            raise RuntimeError('Hash divergente do tokenizador; restaure o modelo fixado')
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.session = None
        self.threads = threads
        self.identity = digest(self.lock["revision"] + self.lock["files"]["onnx/model.onnx"] + ":mean-l2-e5-v1")

    def tokens(self, text):
        return self.tokenizer.encode(text, add_special_tokens=False)

    def load(self):
        if self.session is not None:
            return
        if file_hash(self.directory / 'onnx/model.onnx') != self.lock['files']['onnx/model.onnx']:
            raise RuntimeError('Hash divergente do modelo; restaure o modelo fixado')
        import onnxruntime as ort
        ort.disable_telemetry_events()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.threads
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(self.directory / "onnx/model.onnx"), sess_options=opts, providers=["CPUExecutionProvider"])

    def encode(self, texts, query=False):
        self.load()
        prefixed = [("query: " if query else "passage: ") + t for t in texts]
        enc = [self.tokenizer.encode(t) for t in prefixed]
        if any(len(e.ids) > 512 for e in enc):
            raise ValueError("Entrada ultrapassa 512 tokens; truncamento silencioso não é permitido")
        width = max(len(e.ids) for e in enc)
        ids = np.full((len(enc), width), 1, dtype=np.int64)
        mask = np.zeros_like(ids)
        types = np.zeros_like(ids)
        for i, e in enumerate(enc):
            ids[i, :len(e.ids)] = e.ids
            mask[i, :len(e.ids)] = 1
        inputs = {"input_ids": ids, "attention_mask": mask, "token_type_ids": types}
        feed = {entry.name: inputs[entry.name] for entry in self.session.get_inputs()}
        output = self.session.run(None, feed)[0]
        if output.ndim == 3:
            output = (output * mask[..., None]).sum(axis=1) / mask.sum(axis=1)[:, None]
        if output.ndim != 2 or output.shape[1] != 384:
            raise ValueError(f"Formato inesperado do modelo: {output.shape}")
        output = output.astype(np.float32)
        output /= np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-12)
        return output

def setup_model(root):
    # Network is explicit and limited to this command. Never called by search.
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import hf_hub_download
    directory = Path(root) / ".dbrain/models/e5"
    directory.mkdir(parents=True, exist_ok=True)
    previous = load_json(directory / "model-lock.json")
    repo = "intfloat/multilingual-e5-small"
    revision = previous["revision"] if previous else MODEL_REVISION
    names = ["onnx/model.onnx", "tokenizer.json", "tokenizer_config.json", "config.json"]
    hashes = {}
    for name in names:
        target = directory / name
        if not target.exists():
            hf_hub_download(repo_id=repo, filename=name, revision=revision, local_dir=str(directory))
        hashes[name] = file_hash(target)
        if previous and previous["files"].get(name) != hashes[name]:
            raise RuntimeError(f"Hash divergente do modelo: {name}")
    save_json(directory / "model-lock.json", {"repo": repo, "revision": revision, "files": hashes, "dimensions": 384, "pooling": "attention-mask-mean+l2"})
    e5 = E5(root)
    check = e5.encode(["controle de acesso"], query=True)
    return {"revision": revision, "shape": list(check.shape), "norm": float(np.linalg.norm(check))}
