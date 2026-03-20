import numpy as np


def weighted_kl_divergence(
    ground_truth: np.ndarray, prediction: np.ndarray, eps: float = 1e-12
) -> float:
    """Entropy-weighted KL divergence over a grid of per-cell class probabilities.

    Parameters
    ----------
    ground_truth : array, shape (H, W, C)
        True probability distributions per cell.
    prediction : array, shape (H, W, C)
        Predicted probability distributions per cell.
    eps : float
        Small constant to avoid log(0).

    Returns
    -------
    float
        The entropy-weighted mean KL divergence across all cells.
    """
    p = np.asarray(ground_truth, dtype=np.float64)
    q = np.asarray(prediction, dtype=np.float64)

    # Per-cell entropy: -Σ pᵢ log(pᵢ)
    entropy = -np.sum(p * np.log(p + eps), axis=-1)

    # Per-cell KL divergence: Σ pᵢ log(pᵢ / qᵢ)
    kl = np.sum(p * np.log((p + eps) / (q + eps)), axis=-1)

    total_entropy = np.sum(entropy)
    if total_entropy == 0:
        return 0.0

    return float(np.sum(entropy * kl) / total_entropy)


def score_fun(ground_truth: np.ndarray, prediction: np.ndarray) -> float:
    """Compute the competition score (0–100).

    score = max(0, min(100, 100 * exp(-3 * weighted_kl)))

    Parameters
    ----------
    ground_truth : array, shape (H, W, C)
    prediction : array, shape (H, W, C)

    Returns
    -------
    float
        Score between 0 and 100.
    """
    wkl = weighted_kl_divergence(ground_truth, prediction)
    return float(max(0.0, min(100.0, 100.0 * np.exp(-3.0 * wkl))))
