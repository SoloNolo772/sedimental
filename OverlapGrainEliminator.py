import os
import csv
import cv2
import numpy as np
from PIL import Image


# ============================================================
# USER SETTINGS
# ============================================================

INPUT_FILE = r"C:\Users\solon\Downloads\Capture_1_mask.tiff"

OUTPUT_FOLDER = (
    r"C:\Nolan\UMW\Geology\URES_Project\Overlap_Removal_Output"
)

# ------------------------------------------------------------
# Contact settings
# ------------------------------------------------------------

# Two grains are considered touching if pixels from their
# labels occur within this distance.
CONTACT_DISTANCE = 2

# ------------------------------------------------------------
# Concavity settings
# ------------------------------------------------------------

# Minimum normalized convexity defect to consider significant.
# This is intentionally fairly conservative.
CONCAVITY_THRESHOLD = 0.08

# Number of pixels used when examining the neighborhood around
# a contact.
CONTACT_REGION_SIZE = 12

# ------------------------------------------------------------
# Decision settings
# ------------------------------------------------------------

# Minimum number of independent concavity indicators required
# before a grain can be automatically removed.
MIN_VOTES = 2

# ------------------------------------------------------------
# Output settings
# ------------------------------------------------------------

CREATE_DEBUG_IMAGE = True
CREATE_CSV_REPORT = True


# ============================================================
# CREATE OUTPUT FOLDER
# ============================================================

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ============================================================
# PRINT HEADER
# ============================================================

print()
print("=" * 70)
print("LABEL-PRESERVING OVERLAP GRAIN ELIMINATOR")
print("=" * 70)

print()
print("Input:")
print(INPUT_FILE)

print()
print("Output folder:")
print(OUTPUT_FOLDER)


# ============================================================
# CHECK INPUT
# ============================================================

if not os.path.isfile(INPUT_FILE):

    print()
    print("ERROR:")
    print("Input TIFF does not exist:")
    print(INPUT_FILE)

    input("\nPress Enter to exit...")
    raise SystemExit


# ============================================================
# READ TIFF WITH PILLOW
# ============================================================

print()
print("Reading TIFF...")

try:

    pil_image = Image.open(INPUT_FILE)
    image = np.array(pil_image)

except Exception as e:

    print()
    print("ERROR reading TIFF:")
    print(e)

    input("\nPress Enter to exit...")
    raise SystemExit


# ============================================================
# VERIFY IMAGE
# ============================================================

print()
print("Image information:")
print("  Format:", pil_image.format)
print("  Mode:", pil_image.mode)
print("  Size:", pil_image.size)
print("  Data type:", image.dtype)
print("  Minimum:", image.min())
print("  Maximum:", image.max())


if image.ndim != 2:

    print()
    print("ERROR:")
    print("The TIFF is not a single-channel image.")

    input("\nPress Enter to exit...")
    raise SystemExit


if image.dtype != np.int32:

    print()
    print("WARNING:")
    print("The image is not int32.")
    print("Current type:", image.dtype)


# ============================================================
# FIND GRAIN IDs
# ============================================================

grain_ids = np.unique(image)

grain_ids = grain_ids[grain_ids > 0]

print()
print("Number of grain labels:", len(grain_ids))

print("Grain IDs:")
print(grain_ids)


# ============================================================
# FUNCTION: GET CONTOUR FOR ONE GRAIN
# ============================================================

def get_grain_contour(mask):

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE
    )

    if len(contours) == 0:
        return None

    # Select largest contour
    contour = max(
        contours,
        key=cv2.contourArea
    )

    return contour


# ============================================================
# FUNCTION: GRAIN GEOMETRY
# ============================================================

def analyze_grain(grain_id):

    mask = np.where(
        image == grain_id,
        255,
        0
    ).astype(np.uint8)

    pixel_count = int(np.count_nonzero(mask))

    contour = get_grain_contour(mask)

    if contour is None:

        return {
            "id": grain_id,
            "pixels": pixel_count,
            "area": 0,
            "solidity": 1.0,
            "diameter": 0,
            "max_defect": 0,
            "relative_concavity": 0,
            "contour": None,
            "mask": mask
        }

    area = cv2.contourArea(contour)

    hull = cv2.convexHull(contour)

    hull_area = cv2.contourArea(hull)

    if hull_area > 0:
        solidity = area / hull_area
    else:
        solidity = 1.0

    # Minimum enclosing circle
    (_, _), radius = cv2.minEnclosingCircle(contour)

    diameter = radius * 2.0

    max_defect = 0.0

    # Convexity defects require at least 4 contour points.
    if len(contour) >= 4:

        hull_indices = cv2.convexHull(
            contour,
            returnPoints=False
        )

        if hull_indices is not None and len(hull_indices) >= 3:

            try:

                defects = cv2.convexityDefects(
                    contour,
                    hull_indices
                )

                if defects is not None:

                    for defect in defects:

                        # OpenCV returns:
                        # [start_index, end_index,
                        #  farthest_index, depth]
                        depth = float(
                            defect[0][3]
                        ) / 256.0

                        if depth > max_defect:
                            max_defect = depth

            except cv2.error:

                pass

    if diameter > 0:

        relative_concavity = (
            max_defect / diameter
        )

    else:

        relative_concavity = 0.0

    return {
        "id": grain_id,
        "pixels": pixel_count,
        "area": area,
        "solidity": solidity,
        "diameter": diameter,
        "max_defect": max_defect,
        "relative_concavity": relative_concavity,
        "contour": contour,
        "mask": mask
    }


# ============================================================
# ANALYZE ALL GRAINS
# ============================================================

print()
print("Analyzing individual grains...")

grains = {}

for index, grain_id in enumerate(grain_ids):

    grain = analyze_grain(grain_id)

    grains[int(grain_id)] = grain

    print(
        f"  Grain {int(grain_id):3d}: "
        f"pixels={grain['pixels']:6d}, "
        f"solidity={grain['solidity']:.3f}, "
        f"concavity={grain['relative_concavity']:.3f}"
    )


# ============================================================
# FIND TOUCHING GRAIN PAIRS
# ============================================================

print()
print("Finding neighboring grains...")

neighbor_pairs = set()

height, width = image.shape

# We examine each grain's mask and dilate it slightly.
# If another grain occurs in the dilated region, they are
# potential contacts.

for grain_id in grain_ids:

    grain_id = int(grain_id)

    mask = grains[grain_id]["mask"]

    kernel_size = (
        CONTACT_DISTANCE * 2 + 1
    )

    kernel = np.ones(
        (kernel_size, kernel_size),
        dtype=np.uint8
    )

    expanded = cv2.dilate(
        mask,
        kernel,
        iterations=1
    )

    nearby_ids = np.unique(
        image[expanded > 0]
    )

    nearby_ids = nearby_ids[
        nearby_ids > 0
    ]

    for other_id in nearby_ids:

        other_id = int(other_id)

        if other_id == grain_id:
            continue

        pair = tuple(
            sorted(
                [grain_id, other_id]
            )
        )

        neighbor_pairs.add(pair)


print(
    "Neighboring grain pairs:",
    len(neighbor_pairs)
)


# ============================================================
# INITIALIZE REPORT
# ============================================================

report = []

removed_grains = set()


# ============================================================
# ANALYZE EACH NEIGHBOR PAIR
# ============================================================

print()
print("Analyzing grain contacts...")
print()


for grain_a_id, grain_b_id in sorted(
    neighbor_pairs
):

    grain_a = grains[grain_a_id]
    grain_b = grains[grain_b_id]

    votes_a = 0
    votes_b = 0

    reasons_a = []
    reasons_b = []

    # --------------------------------------------------------
    # TEST 1: GLOBAL CONCAVITY
    # --------------------------------------------------------

    conc_a = grain_a[
        "relative_concavity"
    ]

    conc_b = grain_b[
        "relative_concavity"
    ]

    if conc_a > CONCAVITY_THRESHOLD:

        votes_a += 1

        reasons_a.append(
            "strong global concavity"
        )

    if conc_b > CONCAVITY_THRESHOLD:

        votes_b += 1

        reasons_b.append(
            "strong global concavity"
        )


    # --------------------------------------------------------
    # TEST 2: RELATIVE CONCAVITY
    # --------------------------------------------------------

    if (
        conc_a >
        conc_b * 1.5
        and
        conc_a > CONCAVITY_THRESHOLD
    ):

        votes_a += 1

        reasons_a.append(
            "more concave than neighboring grain"
        )

    elif (
        conc_b >
        conc_a * 1.5
        and
        conc_b > CONCAVITY_THRESHOLD
    ):

        votes_b += 1

        reasons_b.append(
            "more concave than neighboring grain"
        )


    # --------------------------------------------------------
    # TEST 3: SOLIDITY
    # --------------------------------------------------------

    sol_a = grain_a["solidity"]
    sol_b = grain_b["solidity"]

    if sol_a < sol_b - 0.05:

        votes_a += 1

        reasons_a.append(
            "lower solidity"
        )

    elif sol_b < sol_a - 0.05:

        votes_b += 1

        reasons_b.append(
            "lower solidity"
        )


    # --------------------------------------------------------
    # DECISION
    # --------------------------------------------------------

    removed = None
    reason = ""

    if (
        votes_a >= MIN_VOTES
        and
        votes_a > votes_b
    ):

        removed = grain_a_id

        reason = "; ".join(
            reasons_a
        )

    elif (
        votes_b >= MIN_VOTES
        and
        votes_b > votes_a
    ):

        removed = grain_b_id

        reason = "; ".join(
            reasons_b
        )


    # --------------------------------------------------------
    # STORE RESULT
    # --------------------------------------------------------

    report.append({

        "grain_A": grain_a_id,

        "grain_B": grain_b_id,

        "concavity_A":
            conc_a,

        "concavity_B":
            conc_b,

        "solidity_A":
            sol_a,

        "solidity_B":
            sol_b,

        "votes_A":
            votes_a,

        "votes_B":
            votes_b,

        "removed_grain":
            removed,

        "reason":
            reason
    })


    if removed is not None:

        removed_grains.add(
            removed
        )

        print(
            f"Possible covered grain: "
            f"{removed}"
            f"  (contact: "
            f"{grain_a_id}-{grain_b_id})"
        )


# ============================================================
# REMOVE DUPLICATES
# ============================================================

removed_grains = sorted(
    removed_grains
)


# ============================================================
# PRINT SUMMARY
# ============================================================

print()
print("=" * 70)
print("REMOVAL SUMMARY")
print("=" * 70)

print()

if len(removed_grains) == 0:

    print(
        "No grains met the removal criteria."
    )

else:

    print(
        "Grains marked for removal:"
    )

    for grain_id in removed_grains:

        print(
            "  Grain",
            grain_id
        )

print()
print(
    "Total grains removed:",
    len(removed_grains)
)


# ============================================================
# CREATE CLEANED LABEL IMAGE
# ============================================================

print()
print("Creating cleaned labeled TIFF...")


# Start with a copy of the original.
output = image.copy()


# Set entire removed grain to zero.
for grain_id in removed_grains:

    output[
        image == grain_id
    ] = 0


# ============================================================
# SAVE CLEANED TIFF
# ============================================================

base_name = os.path.splitext(
    os.path.basename(INPUT_FILE)
)[0]


output_file = os.path.join(
    OUTPUT_FOLDER,
    base_name +
    "_overlap_removed.tif"
)


print()
print("Saving:")
print(output_file)


try:

    output_image = Image.fromarray(
        output.astype(np.int32)
    )

    output_image.save(
        output_file,
        format="TIFF",
        compression=None
    )

    print("Saved successfully.")

except Exception as e:

    print()
    print("ERROR saving output:")
    print(e)

    input("\nPress Enter to exit...")
    raise SystemExit


# ============================================================
# CREATE DEBUG IMAGE
# ============================================================

if CREATE_DEBUG_IMAGE:

    print()
    print("Creating debug image...")

    debug = np.zeros_like(
        image,
        dtype=np.int32
    )

    for grain_id in removed_grains:

        debug[
            image == grain_id
        ] = grain_id

    debug_file = os.path.join(
        OUTPUT_FOLDER,
        base_name +
        "_removed_grains_debug.tif"
    )

    try:

        debug_image = Image.fromarray(
            debug
        )

        debug_image.save(
            debug_file,
            format="TIFF",
            compression=None
        )

        print(
            "Debug image saved:"
        )

        print(debug_file)

    except Exception as e:

        print()
        print(
            "WARNING: Could not save debug image."
        )

        print(e)


# ============================================================
# SAVE CSV REPORT
# ============================================================

if CREATE_CSV_REPORT:

    csv_file = os.path.join(
        OUTPUT_FOLDER,
        base_name +
        "_overlap_analysis.csv"
    )

    print()
    print("Saving analysis report:")
    print(csv_file)

    try:

        with open(
            csv_file,
            "w",
            newline=""
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "grain_A",
                    "grain_B",
                    "concavity_A",
                    "concavity_B",
                    "solidity_A",
                    "solidity_B",
                    "votes_A",
                    "votes_B",
                    "removed_grain",
                    "reason"
                ]
            )

            writer.writeheader()

            writer.writerows(
                report
            )

        print("CSV saved successfully.")

    except Exception as e:

        print()
        print(
            "WARNING: Could not save CSV."
        )

        print(e)


# ============================================================
# VERIFY OUTPUT
# ============================================================

print()
print("=" * 70)
print("OUTPUT VERIFICATION")
print("=" * 70)

print()

if os.path.exists(output_file):

    print("SUCCESS:")
    print("Cleaned TIFF exists:")
    print(output_file)

    print(
        "File size:",
        os.path.getsize(output_file),
        "bytes"
    )

else:

    print(
        "ERROR: Cleaned TIFF was not created."
    )


# ============================================================
# FINAL MESSAGE
# ============================================================

print()
print("=" * 70)
print("PROGRAM COMPLETE")
print("=" * 70)

print()
print(
    "Original grains:",
    len(grain_ids)
)

print(
    "Removed grains:",
    len(removed_grains)
)

print(
    "Remaining grains:",
    len(grain_ids) -
    len(removed_grains)
)

print()
print(
    "Output folder:"
)

print(OUTPUT_FOLDER)

input("\nPress Enter to close...")
