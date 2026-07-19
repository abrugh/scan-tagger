import logging
from pathlib import Path

import pikepdf
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

logger = logging.getLogger(__name__)


class Reorienter:
    """Detects rotated scans via Tesseract OSD and corrects them in place.

    The scanner defaults to portrait, so landscape documents come out rotated
    90/270 degrees. We rasterize the first page, ask Tesseract's orientation &
    script detection which way it's turned, and — if confident — rotate the
    file back upright. Orientation is detected once from page one and applied
    to every page (a single scan job shares one orientation).
    """

    def __init__(self, config):
        self.config = config

    def _detect_rotation(self, image: Image.Image) -> tuple[int, float]:
        """Return (clockwise degrees to correct, confidence). 0 means upright."""
        try:
            osd = pytesseract.image_to_osd(
                image, output_type=pytesseract.Output.DICT
            )
        except Exception as exc:
            # OSD raises on pages with too few characters (e.g. photos) — treat
            # as "unknown, leave alone".
            logger.debug("OSD could not determine orientation: %s", exc)
            return 0, 0.0

        return int(osd.get("rotate", 0)), float(osd.get("orientation_conf", 0.0))

    def correct(self, file_path: Path) -> bool:
        """Detect and fix orientation in place. Returns True if the file changed."""
        if not self.config.reorient_enabled:
            return False

        suffix = file_path.suffix.lower()

        try:
            if suffix == ".pdf":
                pages = convert_from_path(
                    str(file_path), first_page=1, last_page=1, dpi=200, grayscale=True
                )
                if not pages:
                    return False
                probe = pages[0]
            else:
                probe = Image.open(file_path)
        except Exception as exc:
            logger.warning("Could not render %s for OSD: %s", file_path.name, exc)
            return False

        rotate, conf = self._detect_rotation(probe)

        if rotate == 0:
            return False
        if conf < self.config.min_orientation_confidence:
            logger.info(
                "%s looks rotated %d° but confidence %.2f < %.2f — leaving as-is",
                file_path.name, rotate, conf, self.config.min_orientation_confidence,
            )
            return False

        logger.info(
            "Reorienting %s by %d° (confidence %.2f)", file_path.name, rotate, conf
        )

        if suffix == ".pdf":
            return self._rotate_pdf(file_path, rotate)
        return self._rotate_image(file_path, rotate)

    def _rotate_pdf(self, file_path: Path, rotate: int) -> bool:
        """Losslessly set each page's /Rotate — no re-rendering, no quality loss."""
        try:
            with pikepdf.open(file_path, allow_overwriting_input=True) as pdf:
                for page in pdf.pages:
                    current = int(page.get("/Rotate", 0))
                    page.Rotate = (current + rotate) % 360
                pdf.save(file_path)
            return True
        except Exception as exc:
            logger.warning("Failed to rotate PDF %s: %s", file_path.name, exc)
            return False

    def _rotate_image(self, file_path: Path, rotate: int) -> bool:
        """Rotate raster images by rotating pixels (Tesseract 'rotate' is clockwise)."""
        try:
            with Image.open(file_path) as img:
                fmt = img.format
                # PIL rotates counter-clockwise; negate to match OSD's clockwise value.
                rotated = img.rotate(-rotate, expand=True)
                rotated.save(file_path, format=fmt)
            return True
        except Exception as exc:
            logger.warning("Failed to rotate image %s: %s", file_path.name, exc)
            return False
