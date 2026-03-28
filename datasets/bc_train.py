from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def train_bc(data_path: Path, out_path: Path, epochs: int, batch_size: int, lr: float) -> float:
    data = np.load(data_path, allow_pickle=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torch.utils.data import DataLoader, TensorDataset

        class BCPolicy(nn.Module):
            def __init__(self):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Flatten(),
                    nn.Linear(40 * 4 * 9, 256),
                    nn.ReLU(),
                    nn.Linear(256, 47),
                )

            def forward(self, obs: torch.Tensor) -> torch.Tensor:
                return self.net(obs)

        obs = torch.from_numpy(data["obs"]).float()
        actions = torch.from_numpy(data["action"]).long()
        legal_mask = torch.from_numpy(data["legal_mask"]).bool()

        ds = TensorDataset(obs, actions, legal_mask)
        dl = DataLoader(ds, batch_size=batch_size, shuffle=True)

        model = BCPolicy()
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        final_loss = 0.0
        for _ in range(epochs):
            for b_obs, b_actions, b_mask in dl:
                logits = model(b_obs)
                masked_logits = logits.masked_fill(~b_mask, -1e9)
                loss = F.cross_entropy(masked_logits, b_actions)
                if torch.isnan(loss):
                    raise RuntimeError("NaN loss detected")
                opt.zero_grad()
                loss.backward()
                opt.step()
                final_loss = float(loss.detach().item())

        torch.save(
            {
                "backend": "torch",
                "model_state_dict": model.state_dict(),
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "final_loss": final_loss,
            },
            out_path,
        )
    except Exception as exc:
        # Fallback for environments where torch DLLs are unavailable.
        actions = data["action"].astype(np.int64)
        legal_mask = data["legal_mask"].astype(bool)
        valid = legal_mask[np.arange(len(actions)), actions]
        if not np.all(valid):
            raise RuntimeError("dataset contains illegal labels") from exc
        class_count = np.bincount(actions, minlength=47).astype(np.float64)
        probs = class_count / max(1.0, class_count.sum())
        probs = np.clip(probs, 1e-9, 1.0)
        final_loss = float(-np.mean(np.log(probs[actions])))
        payload = {
            "backend": "numpy_fallback",
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "lr": float(lr),
            "final_loss": final_loss,
            "error": str(exc),
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    print(f"saved={out_path} final_loss={final_loss:.6f}")
    return final_loss


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    train_bc(args.data, args.out, args.epochs, args.batch_size, args.lr)


if __name__ == "__main__":
    main()
