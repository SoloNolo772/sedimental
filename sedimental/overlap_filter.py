"""
Overlap grain filter for Sedimental analysis tool.

Detects and removes partially occluded ("covered") grains from a labeled
segmentation mask using shape-based heuristics. Preserves the original
grain labels so measurements downstream can be traced back to the
original segmentation.

The technique is a Python port of the standalone
``OverlapGrainEliminator.py`` script and applies the same conservative
voting rules:

1. For each grain, compute solidity and a normalized concavity metric
   (deepest convexity defect divided by enclosing-circle diameter).
2. Find touching grain pairs by dilating each grain's mask and checking
   which other labels fall inside the dilation.
3. For each pair, run three independent tests (global concavity,
   relative concavity, solidity gap). A grain is marked "covered" only
   when it accumulates at least ``min_votes`` and strictly outscores
   its neighbor.

Requires OpenCV (``cv2``). It is available in the Sedimental container
as a transitive dependency of Cellpose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

try:
    import cv2  # type: ignore
    _CV2_AVAILABLE = True
except ImportError:  # pragma: no cover - cv2 is a container dependency
    _CV2_AVAILABLE = False

logger = logging.getLogger("sedimental.overlap_filter")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OverlapPairRecord:
    """Per-pair analysis record explaining a removal decision."""

    grain_a: int
    grain_b: int
    concavity_a: float
    concavity_b: float
    solidity_a: float
    solidity_b: float
    votes_a: int
    votes_b: int
    removed_grain: Optional[int]
    reason: str


@dataclass
class OverlapFilterResult:
    """Result of running :class:`OverlapGrainFilter` on a labeled mask."""

    #: Copy of the input mask with removed grain labels set to 0.
    filtered_mask: np.ndarray
    #: Sorted list of grain IDs that were removed.
    removed_ids: List[int]
    #: Per-pair analysis records (one entry per touching pair examined).
    pair_records: List[OverlapPairRecord] = field(default_factory=list)
    #: Total number of positive labels in the input mask.
    original_grain_count: int = 0

    @property
    def remaining_grain_count(self) -> int:
        return self.original_grain_count - len(self.removed_ids)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _largest_contour(mask: np.ndarray):
    """Return the largest external contour of a binary mask, or None."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


@dataclass
class _GrainMetrics:
    grain_id: int
    pixels: int
    area: float
    solidity: float
    diameter: float
    max_defect: float
    relative_concavity: float
    mask: np.ndarray


def _analyze_grain(mask_full: np.ndarray, grain_id: int) -> _GrainMetrics:
    """Compute shape metrics for a single grain."""
    mask = np.where(mask_full == grain_id, 255, 0).astype(np.uint8)
    pixel_count = int(np.count_nonzero(mask))

    contour = _largest_contour(mask)
    if contour is None:
        return _GrainMetrics(
            grain_id=grain_id,
            pixels=pixel_count,
            area=0.0,
            solidity=1.0,
            diameter=0.0,
            max_defect=0.0,
            relative_concavity=0.0,
            mask=mask,
        )

    area = float(cv2.contourArea(contour))
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    solidity = area / hull_area if hull_area > 0 else 1.0

    (_cx, _cy), radius = cv2.minEnclosingCircle(contour)
    diameter = float(radius) * 2.0

    max_defect = 0.0
    if len(contour) >= 4:
        hull_indices = cv2.convexHull(contour, returnPoints=False)
        if hull_indices is not None and len(hull_indices) >= 3:
            try:
                defects = cv2.convexityDefects(contour, hull_indices)
            except cv2.error:
                defects = None
            if defects is not None:
                # OpenCV stores depths as fixed-point at 1/256 px resolution.
                max_defect = float(defects[:, 0, 3].max()) / 256.0

    relative_concavity = (max_defect / diameter) if diameter > 0 else 0.0

    return _GrainMetrics(
        grain_id=grain_id,
        pixels=pixel_count,
        area=area,
        solidity=solidity,
        diameter=diameter,
        max_defect=max_defect,
        relative_concavity=relative_concavity,
        mask=mask,
    )


def _find_touching_pairs(
    mask_full: np.ndarray,
    grains: Dict[int, _GrainMetrics],
    contact_distance: int,
) -> Set[Tuple[int, int]]:
    """Return the set of touching grain pairs using dilation-based contact."""
    kernel_size = contact_distance * 2 + 1
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)

    pairs: Set[Tuple[int, int]] = set()
    for grain_id, grain in grains.items():
        expanded = cv2.dilate(grain.mask, kernel, iterations=1)
        nearby = np.unique(mask_full[expanded > 0])
        for other_id in nearby:
            other = int(other_id)
            if other <= 0 or other == grain_id:
                continue
            a, b = (grain_id, other) if grain_id < other else (other, grain_id)
            pairs.add((a, b))
    return pairs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class OverlapGrainFilter:
    """Detect and remove overlapping (partially-covered) grains.

    Parameters mirror the constants in the standalone
    ``OverlapGrainEliminator.py`` script and default to the same values,
    so behaviour matches the original technique out of the box.

    Args:
        contact_distance: Dilation radius (in pixels) used to decide
            whether two grains are touching. A larger value tolerates
            gaps between segmented grains.
        concavity_threshold: Minimum normalized concavity
            (``max_defect / enclosing_diameter``) required for the
            global-concavity vote.
        relative_concavity_ratio: In the relative-concavity test, a
            grain must be this many times more concave than its
            neighbor to earn a vote.
        solidity_gap: Minimum solidity difference between neighbors
            before the less-solid grain earns a solidity vote.
        min_votes: Number of independent indicators required before a
            grain can be removed. The grain must also strictly outscore
            its neighbor in the pair.
    """

    #: Default matching the standalone script (``CONTACT_DISTANCE = 2``).
    DEFAULT_CONTACT_DISTANCE = 2
    #: Default matching the standalone script (``CONCAVITY_THRESHOLD = 0.08``).
    DEFAULT_CONCAVITY_THRESHOLD = 0.08
    #: Default matching the ``* 1.5`` factor in the standalone script.
    DEFAULT_RELATIVE_CONCAVITY_RATIO = 1.5
    #: Default matching the ``0.05`` solidity gap in the standalone script.
    DEFAULT_SOLIDITY_GAP = 0.05
    #: Default matching the standalone script (``MIN_VOTES = 2``).
    DEFAULT_MIN_VOTES = 2

    def __init__(
        self,
        contact_distance: int = DEFAULT_CONTACT_DISTANCE,
        concavity_threshold: float = DEFAULT_CONCAVITY_THRESHOLD,
        relative_concavity_ratio: float = DEFAULT_RELATIVE_CONCAVITY_RATIO,
        solidity_gap: float = DEFAULT_SOLIDITY_GAP,
        min_votes: int = DEFAULT_MIN_VOTES,
    ):
        if not _CV2_AVAILABLE:
            raise RuntimeError(
                "OverlapGrainFilter requires the 'cv2' (OpenCV) package. "
                "It ships with the Sedimental container as a Cellpose "
                "dependency; install 'opencv-python-headless' locally if "
                "you need to run the filter outside the container."
            )

        if contact_distance < 0:
            raise ValueError(f"contact_distance must be >= 0, got {contact_distance}")
        if concavity_threshold < 0:
            raise ValueError(
                f"concavity_threshold must be >= 0, got {concavity_threshold}"
            )
        if relative_concavity_ratio <= 0:
            raise ValueError(
                f"relative_concavity_ratio must be > 0, got {relative_concavity_ratio}"
            )
        if solidity_gap < 0:
            raise ValueError(f"solidity_gap must be >= 0, got {solidity_gap}")
        if min_votes < 1:
            raise ValueError(f"min_votes must be >= 1, got {min_votes}")

        self.contact_distance = contact_distance
        self.concavity_threshold = concavity_threshold
        self.relative_concavity_ratio = relative_concavity_ratio
        self.solidity_gap = solidity_gap
        self.min_votes = min_votes

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def filter(
        self,
        mask: np.ndarray,
        filename: str = "<mask>",
    ) -> OverlapFilterResult:
        """Analyze a labeled mask and return a cleaned copy.

        Args:
            mask: Labeled integer mask (H, W). 0 = background, each
                positive integer identifies one grain.
            filename: Source name used in log messages.

        Returns:
            :class:`OverlapFilterResult` with the cleaned mask, the list
            of removed grain IDs, and per-pair records.
        """
        if mask.ndim != 2:
            raise ValueError(
                f"Overlap filter requires a 2-D labeled mask, got shape {mask.shape}"
            )

        # Force int32 for compatibility with the cv2 helpers we call.
        mask_int = mask.astype(np.int32, copy=False)

        grain_ids = np.unique(mask_int)
        grain_ids = grain_ids[grain_ids > 0]
        original_count = int(len(grain_ids))

        logger.info(
            "Overlap filter analyzing '%s': %d grain(s)",
            filename,
            original_count,
        )

        # Empty / single-grain masks have no pairs to consider.
        if original_count < 2:
            return OverlapFilterResult(
                filtered_mask=mask_int.copy(),
                removed_ids=[],
                pair_records=[],
                original_grain_count=original_count,
            )

        # 1. Per-grain metrics
        grains: Dict[int, _GrainMetrics] = {}
        for gid in grain_ids:
            gid_int = int(gid)
            grains[gid_int] = _analyze_grain(mask_int, gid_int)

        # 2. Touching pairs
        pairs = _find_touching_pairs(mask_int, grains, self.contact_distance)
        logger.debug(
            "Overlap filter '%s': %d touching pair(s)", filename, len(pairs)
        )

        # 3. Pairwise voting
        pair_records: List[OverlapPairRecord] = []
        removed: Set[int] = set()
        for grain_a_id, grain_b_id in sorted(pairs):
            record = self._analyze_pair(grains[grain_a_id], grains[grain_b_id])
            pair_records.append(record)
            if record.removed_grain is not None:
                removed.add(record.removed_grain)

        # 4. Build cleaned mask
        filtered = mask_int.copy()
        for gid in removed:
            filtered[mask_int == gid] = 0

        removed_sorted = sorted(removed)
        logger.info(
            "Overlap filter '%s': removed %d/%d grain(s) (%d remaining)",
            filename,
            len(removed_sorted),
            original_count,
            original_count - len(removed_sorted),
        )

        return OverlapFilterResult(
            filtered_mask=filtered,
            removed_ids=removed_sorted,
            pair_records=pair_records,
            original_grain_count=original_count,
        )

    # ------------------------------------------------------------------
    # Internal per-pair vote logic
    # ------------------------------------------------------------------

    def _analyze_pair(
        self,
        grain_a: _GrainMetrics,
        grain_b: _GrainMetrics,
    ) -> OverlapPairRecord:
        """Run the 3-vote analysis on a touching pair."""
        votes_a = 0
        votes_b = 0
        reasons_a: List[str] = []
        reasons_b: List[str] = []

        conc_a = grain_a.relative_concavity
        conc_b = grain_b.relative_concavity

        # Test 1: global concavity above threshold (symmetric).
        if conc_a > self.concavity_threshold:
            votes_a += 1
            reasons_a.append("strong global concavity")
        if conc_b > self.concavity_threshold:
            votes_b += 1
            reasons_b.append("strong global concavity")

        # Test 2: relative concavity vs neighbor (asymmetric).
        if (
            conc_a > conc_b * self.relative_concavity_ratio
            and conc_a > self.concavity_threshold
        ):
            votes_a += 1
            reasons_a.append("more concave than neighboring grain")
        elif (
            conc_b > conc_a * self.relative_concavity_ratio
            and conc_b > self.concavity_threshold
        ):
            votes_b += 1
            reasons_b.append("more concave than neighboring grain")

        # Test 3: solidity gap (asymmetric).
        sol_a = grain_a.solidity
        sol_b = grain_b.solidity
        if sol_a < sol_b - self.solidity_gap:
            votes_a += 1
            reasons_a.append("lower solidity")
        elif sol_b < sol_a - self.solidity_gap:
            votes_b += 1
            reasons_b.append("lower solidity")

        # Decision
        removed: Optional[int] = None
        reason = ""
        if votes_a >= self.min_votes and votes_a > votes_b:
            removed = grain_a.grain_id
            reason = "; ".join(reasons_a)
        elif votes_b >= self.min_votes and votes_b > votes_a:
            removed = grain_b.grain_id
            reason = "; ".join(reasons_b)

        return OverlapPairRecord(
            grain_a=grain_a.grain_id,
            grain_b=grain_b.grain_id,
            concavity_a=conc_a,
            concavity_b=conc_b,
            solidity_a=sol_a,
            solidity_b=sol_b,
            votes_a=votes_a,
            votes_b=votes_b,
            removed_grain=removed,
            reason=reason,
        )
